"""The 15-minute response window for a new event item (DECISION_CELL_SPEC section 3, timeout rule).

When an item arrives, the trusted service opens a window. If no permitted person has answered it within
15 minutes, a HOLD is recorded: the last human-approved result (if any) stays, the elapsed time is
recorded, and an alert becomes due to the recorded project owner and to the backup contact only if the owner
named one. This module publishes nothing, changes no forecast, runs nothing and **delivers no alert**: it
records who is owed one. Sending it, and calling ``sweep_response_windows`` on a timer, are the service's job.

State is the anchored audit chain itself (no separate table that could drift from it). Each (tenant, project,
study, item) has at most one ``opened``, one ``held`` and one ``answered`` event, with ids derived from
that key, so a window cannot be reopened to restart its clock.

A HOLD defers the item; it does not review it. It must carry a re-check time (the gate enforces this). Only
while the latest decision is a HOLD can another decision be recorded (``redecided``, numbered from 2). If a
re-check time arrives first, one ``lapsed`` event records a new alert due to the owner and any named backup.
At the re-check time exactly, it has lapsed. Until a decision other than HOLD is recorded, the item is
``unreviewed_event_pending``.

Which choices answer a window: IGNORE, HOLD and the run options, and only when the gate allows them.
A refused attempt never stops the clock, so someone without permission cannot silence the alert. COMPARE
(looking) and ESCALATE (asking someone else) decide nothing about the item, so they do not stop it either.

Trust boundary. ``audit``, ``tenant_id``, ``now`` and ``approved_result_hash_for`` come from the service's
own configuration and clock, never from a request. There is no trusted time source here, and a caller that
can append to the audit chain directly is outside this protection (see ``project_store``).
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from agora.audit_anchor import AnchoredAuditChain, AnchorWriteError, verify_anchored
from agora.audit_chain import AuditReplayError
from agora.decision_cell.evidence import StatementEvidence, require_unchanged, request_labelled_option
from agora.decision_cell.options import DecisionCellError, GateResult, Option, OptionRequest, StudyState
from agora.decision_cell.project_store import (
    _canonical, _hash, _identifier, _writer, load_project_record, request_project_option,
)
from agora.policy import POLICY_VERSION
from agora.principal import Principal

RESPONSE_WINDOW = timedelta(minutes=15)   # owner decision, 25 Nov 2026 (spec 9.3)
ANSWERING_OPTIONS = frozenset({
    Option.IGNORE, Option.HOLD, Option.CONTINUE, Option.FORK_FROM_EVENT, Option.FORK_FROM_EARLIER,
    Option.RERUN_FROM_START, Option.CHANGE_INPUTS,
})

_PREFIX = "dc-window-"
_OPENED, _HELD, _ANSWERED = "opened", "held", "answered"
_REDECIDED, _LAPSED = "redecided", "lapsed"
_NUMBERED = (_REDECIDED, _LAPSED)   # event ids that also carry a decision number
UNREVIEWED_EVENT_PENDING = "unreviewed event pending"   # spec section 3, HOLD
_SYSTEM = "system:decision-cell"
_SHA256 = re.compile(r"[0-9a-f]{64}")

HELD_LAST_APPROVED = "held_last_approved"
HELD_NO_APPROVED = "held_no_approved_result"
HELD_LOOKUP_FAILED = "held_approved_result_unavailable"
_IN_TIME = "answered_in_window"
_AFTER_HOLD = "answered_after_hold"
_BEFORE_RECHECK = "decided_before_recheck"
_AFTER_RECHECK = "decided_after_recheck_lapsed"
_RECHECK_LAPSED = "recheck_time_passed_without_decision"


class ResponseWindowError(DecisionCellError):
    """A refused or untrustworthy window operation. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ResponseWindow:
    tenant_id: str
    project_id: str
    study_id: str
    item_id: str
    opened_at: datetime
    # Set once the window has expired unanswered; it stays set after a late answer.
    # The ``answered_*`` fields describe the first answer; the ``latest_*`` fields the one now in force.
    hold_reason: str | None = None
    # The result that stays in force. None means nothing may be published for this item.
    approved_result_hash: str | None = None
    alert_due_subject_ids: tuple[str, ...] = ()
    held_after_ms: int | None = None
    answered_by_subject_id: str | None = None
    answered_option: str | None = None
    answered_after_ms: int | None = None
    decision_count: int = 0
    latest_option: str | None = None
    latest_subject_id: str | None = None
    # Set only while the latest decision is a HOLD.
    recheck_at: datetime | None = None
    # Who is owed an alert because that re-check time passed; empty until a lapse is recorded.
    recheck_alert_due_subject_ids: tuple[str, ...] = ()
    recheck_lapse_count: int = 0

    @property
    def deadline(self) -> datetime:
        return self.opened_at + RESPONSE_WINDOW

    @property
    def status(self) -> str:
        if self.latest_option == Option.HOLD.value:
            return "RECHECK_DUE" if self.recheck_alert_due_subject_ids else "DEFERRED"
        if self.answered_by_subject_id is not None:
            return "ANSWERED_AFTER_HOLD" if self.hold_reason else "ANSWERED"
        return "HELD" if self.hold_reason else "OPEN"

    @property
    def unreviewed_event_pending(self) -> bool:
        """True until a decision other than HOLD is recorded. It does not say a chosen run has happened."""
        return self.latest_option in (None, Option.HOLD.value)


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ResponseWindowError("CLOCK_INVALID", "now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc)


def _key_hash(tenant_id: str, project_id: str, study_id: str, item_id: str) -> str:
    return _hash(_canonical([tenant_id, project_id, study_id, item_id]))


def _event_id(kind: str, key_hash: str) -> str:
    return f"{_PREFIX}{kind}-{key_hash}"


def _check_ids(*values: Any) -> None:
    if not all(_identifier(v) for v in values):
        raise ResponseWindowError("ID_INVALID", "ids must be exact non-empty strings")


def _scope(tenant_id: str, project_id: str, study_id: str, item_id: str) -> list[str]:
    return [f"tenant:{tenant_id}", f"project:{project_id}", f"study:{study_id}", f"item:{item_id}"]


def _tagged(event: dict[str, Any], tag: str) -> list[str]:
    return [v[len(tag) + 1:] for v in event["resource_ids"] if v.startswith(tag + ":")]


def _read_windows(writer: AnchoredAuditChain) -> dict[str, ResponseWindow]:
    """Every window in a cleanly anchored chain, keyed by key hash. Refuses anything inconsistent."""
    try:
        with writer.anchors.lock():
            state = verify_anchored(writer.chain, writer.anchors)
            if not state["valid"]:
                raise ResponseWindowError("AUDIT_UNANCHORED", state["status"])
            rows = writer.chain.db.execute(
                "SELECT event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? ORDER BY seq",
                (len(_PREFIX), _PREFIX)).fetchall()
        found: dict[str, dict[str, dict[str, Any]]] = {}
        for event_id, raw in rows:
            event = json.loads(raw)
            ids = [_tagged(event, tag) for tag in ("tenant", "project", "study", "item")]
            if any(len(v) != 1 for v in ids):
                raise ResponseWindowError("STORE_INCONSISTENT", "a window event has no exact scope")
            key = _key_hash(*(v[0] for v in ids))
            kind = event_id[len(_PREFIX):].split("-", 1)[0]
            slot, suffix = kind, kind
            if kind in _NUMBERED:
                number = event.get("sequence")
                if type(number) is not int or number < (2 if kind == _REDECIDED else 1):
                    raise ResponseWindowError("STORE_INCONSISTENT", "a window event has no valid number")
                slot, suffix = (kind, number), f"{kind}-{number}"
            if (kind not in (_OPENED, _HELD, _ANSWERED, *_NUMBERED) or event_id != _event_id(suffix, key)
                    or event.get("event_type") != f"decision_cell_window_{kind}"):
                raise ResponseWindowError("STORE_INCONSISTENT", "a window event does not match its scope")
            found.setdefault(key, {})[slot] = event
        windows: dict[str, ResponseWindow] = {}
        for key, events in found.items():
            if _OPENED not in events:
                raise ResponseWindowError("STORE_INCONSISTENT", "a window has no opening event")
            opened = events[_OPENED]
            held, answered = events.get(_HELD), events.get(_ANSWERED)
            decisions, due, lapses = _decision_history(events)
            latest = decisions[-1] if decisions else None
            lapsed = events.get((_LAPSED, len(decisions)))
            windows[key] = ResponseWindow(
                *(_tagged(opened, tag)[0] for tag in ("tenant", "project", "study", "item")),
                opened_at=_utc(datetime.fromisoformat(opened["recorded_at"])),
                hold_reason=held["reason"] if held else None,
                approved_result_hash=held.get("approved_result_hash") if held else None,
                alert_due_subject_ids=tuple(_tagged(held, "alert")) if held else (),
                held_after_ms=held["duration_ms"] if held else None,
                answered_by_subject_id=answered["subject_id"] if answered else None,
                answered_option=answered["operation"] if answered else None,
                answered_after_ms=answered["duration_ms"] if answered else None,
                decision_count=len(decisions),
                latest_option=latest["operation"] if latest else None,
                latest_subject_id=latest["subject_id"] if latest else None,
                recheck_at=due,
                recheck_alert_due_subject_ids=tuple(_tagged(lapsed, "alert")) if lapsed else (),
                recheck_lapse_count=lapses,
            )
        return windows
    except ResponseWindowError:
        raise
    except Exception as exc:
        raise ResponseWindowError("STORE_ERROR", "response windows could not be read") from exc


def _decision_history(events: dict[Any, dict[str, Any]]) -> tuple[list[dict[str, Any]], datetime | None, int]:
    """The decisions in order, the latest one's re-check time and the lapse count, or a refusal."""
    def bad(detail: str) -> ResponseWindowError:
        return ResponseWindowError("STORE_INCONSISTENT", detail)

    decisions = [events[_ANSWERED]] if _ANSWERED in events else []
    while decisions and (_REDECIDED, len(decisions) + 1) in events:
        decisions.append(events[(_REDECIDED, len(decisions) + 1)])
    numbered = [slot for slot in events if isinstance(slot, tuple)]
    if sum(slot[0] == _REDECIDED for slot in numbered) != max(len(decisions) - 1, 0):
        raise bad("decision numbers are not contiguous")
    due: datetime | None = None
    for position, decision in enumerate(decisions, 1):
        is_hold = decision.get("operation") == Option.HOLD.value
        times = _tagged(decision, "recheck")
        if len(times) != (1 if is_hold else 0):
            raise bad("only a HOLD has a re-check time, and it has exactly one")
        if position < len(decisions) and not is_hold:
            raise bad("only a HOLD can be followed by another decision")
        due = _utc(datetime.fromisoformat(times[0])) if is_hold else None
    lapses = [slot[1] for slot in numbered if slot[0] == _LAPSED]
    for position in lapses:
        if position > len(decisions) or decisions[position - 1].get("operation") != Option.HOLD.value:
            raise bad("a lapse does not follow a HOLD")
    return decisions, due, len(lapses)


def load_response_window(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                         audit: AnchoredAuditChain) -> ResponseWindow | None:
    """A trusted service-side read; it performs no caller permission check."""
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, item_id)
    return _read_windows(writer).get(_key_hash(tenant_id, project_id, study_id, item_id))


def _append(writer: AnchoredAuditChain, event: dict[str, Any],
            in_transaction: Callable[[sqlite3.Connection], None] | None = None) -> None:
    try:
        writer.append(event, in_transaction=in_transaction)
    except (DecisionCellError, AuditReplayError):  # includes ResponseWindowError and changed evidence
        raise
    except AnchorWriteError as exc:
        raise ResponseWindowError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; reconcile first") from exc
    except Exception as exc:
        raise ResponseWindowError("AUDIT_FAILED", "the window event could not be recorded") from exc


def _exists(db: sqlite3.Connection, event_id: str) -> bool:
    return db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (event_id,)).fetchone() is not None


def _event(kind: str, key: str, scope: list[str], now: datetime, **fields: Any) -> dict[str, Any]:
    return {
        "event_id": _event_id(kind, key), "event_type": f"decision_cell_window_{kind}",
        "policy_version": POLICY_VERSION, "recorded_at": now.isoformat(), "resource_ids": scope, **fields,
    }


def open_response_window(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                         audit: AnchoredAuditChain, now: datetime | None = None) -> ResponseWindow:
    """Start the clock for a newly received item. Needs a stored project record (someone to alert)."""
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, item_id)
    moment = _utc(now)
    stored = load_project_record(tenant_id=tenant_id, project_id=project_id, audit=writer)
    if stored is None:
        raise ResponseWindowError("NO_PROJECT_RECORD", "no designated owner is recorded for this project")
    key = _key_hash(tenant_id, project_id, study_id, item_id)
    try:
        _append(writer, _event(_OPENED, key, _scope(tenant_id, project_id, study_id, item_id), moment,
                               subject_id=_SYSTEM, operation="open_response_window",
                               record_hash=stored.record_hash))
    except AuditReplayError as exc:
        raise ResponseWindowError("WINDOW_EXISTS", "this item already has a window; its clock is unchanged") from exc
    return ResponseWindow(tenant_id, project_id, study_id, item_id, moment)


def _hold_if_due(writer: AnchoredAuditChain, window: ResponseWindow, moment: datetime,
                 approved_result_hash_for: Callable[[str], str | None]) -> ResponseWindow:
    elapsed = moment - window.opened_at
    if window.status != "OPEN" or elapsed < RESPONSE_WINDOW:
        return window
    recipients, record_hash = _alert_recipients(writer, window)
    # A broken result lookup must not suppress the hold or the alert; it only means nothing is publishable.
    try:
        approved = approved_result_hash_for(window.study_id)
    except Exception:
        approved, reason = None, HELD_LOOKUP_FAILED
    else:
        if approved is None:
            reason = HELD_NO_APPROVED
        elif isinstance(approved, str) and _SHA256.fullmatch(approved):
            reason = HELD_LAST_APPROVED
        else:
            approved, reason = None, HELD_LOOKUP_FAILED
    key = _key_hash(window.tenant_id, window.project_id, window.study_id, window.item_id)
    scope = _scope(window.tenant_id, window.project_id, window.study_id, window.item_id)
    fields: dict[str, Any] = {
        "subject_id": _SYSTEM, "operation": "hold_unanswered_item", "decision": "deny", "reason": reason,
        "duration_ms": elapsed // timedelta(milliseconds=1), "record_hash": record_hash,
    }
    if approved is not None:
        fields["approved_result_hash"] = approved

    def still_unanswered(db: sqlite3.Connection) -> None:
        if _exists(db, _event_id(_ANSWERED, key)):
            raise ResponseWindowError("WINDOW_CHANGED", "the item was answered while the hold was being recorded")

    try:
        _append(writer, _event(_HELD, key, scope + [f"alert:{r}" for r in recipients], moment, **fields),
                still_unanswered)
    except AuditReplayError:
        pass  # another sweeper recorded this hold first; return what it recorded
    return _read_windows(writer)[key]


def _alert_recipients(writer: AnchoredAuditChain, window: ResponseWindow) -> tuple[list[str], str]:
    """The recorded owner plus a named backup, from the project record current now, and that record's hash."""
    stored = load_project_record(tenant_id=window.tenant_id, project_id=window.project_id, audit=writer)
    if stored is None:
        raise ResponseWindowError("STORE_INCONSISTENT", "an open window has no project record")
    recipients = [stored.record.owner_subject_id]
    backup = stored.record.backup_contact_subject_id
    if backup is not None:
        recipients.append(backup)
    return recipients, stored.record_hash


def _lapse_if_due(writer: AnchoredAuditChain, window: ResponseWindow, moment: datetime) -> ResponseWindow:
    if window.status != "DEFERRED" or window.recheck_at is None or moment < window.recheck_at:
        return window
    recipients, record_hash = _alert_recipients(writer, window)
    key = _key_hash(window.tenant_id, window.project_id, window.study_id, window.item_id)
    scope = _scope(window.tenant_id, window.project_id, window.study_id, window.item_id)
    number = window.decision_count

    def still_deferred(db: sqlite3.Connection) -> None:
        if _exists(db, _event_id(f"{_REDECIDED}-{number + 1}", key)):
            raise ResponseWindowError("WINDOW_CHANGED", "a decision arrived while the lapse was being recorded")

    event = _event(_LAPSED, key, scope + [f"alert:{r}" for r in recipients], moment, subject_id=_SYSTEM,
                   operation="recheck_lapsed", decision="deny", reason=_RECHECK_LAPSED, sequence=number,
                   duration_ms=(moment - window.opened_at) // timedelta(milliseconds=1), record_hash=record_hash)
    event["event_id"] = _event_id(f"{_LAPSED}-{number}", key)
    try:
        _append(writer, event, still_deferred)
    except AuditReplayError:
        pass  # another sweeper recorded this lapse first; return what it recorded
    return _read_windows(writer)[key]


def sweep_response_windows(
    *, tenant_id: str, project_id: str, audit: AnchoredAuditChain,
    approved_result_hash_for: Callable[[str], str | None], now: datetime | None = None,
) -> tuple[ResponseWindow, ...]:
    """Hold every expired, unanswered window of one project, record every passed re-check time, and return
    the windows this call found due (status ``HELD`` or ``RECHECK_DUE``).

    Windows are found in the audit chain, so none depends on a caller remembering it. A window answered or
    decided again while the sweep runs is left alone.
    """
    writer = _writer(audit)
    _check_ids(tenant_id, project_id)
    moment = _utc(now)
    held: list[ResponseWindow] = []
    for window in _read_windows(writer).values():
        if (window.tenant_id, window.project_id) != (tenant_id, project_id):
            continue
        if window.status == "OPEN" and moment >= window.deadline:
            act = lambda w: _hold_if_due(writer, w, moment, approved_result_hash_for)
        elif window.status == "DEFERRED" and window.recheck_at is not None and moment >= window.recheck_at:
            act = lambda w: _lapse_if_due(writer, w, moment)
        else:
            continue
        try:
            held.append(act(window))
        except ResponseWindowError as exc:
            if exc.code != "WINDOW_CHANGED":
                raise
    return tuple(held)


def respond_to_item(
    principal: Principal | None, request: OptionRequest, *, tenant_id: str, project_id: str,
    study: StudyState, audit: AnchoredAuditChain,
    approved_result_hash_for: Callable[[str], str | None], now: datetime | None = None,
    statements: tuple[StatementEvidence, ...] | None = None, **context: Any,
) -> tuple[GateResult, ResponseWindow]:
    """Judge a person's choice through the gate and, if allowed, record it as a decision on the item.

    An expired window is held, and a passed re-check time recorded, before the choice is judged, so a late
    decision cannot erase either alert. A choice is recorded when it is the first answer or replaces a HOLD;
    after any other decision nothing more is recorded. Raising means nothing may proceed. The result is still
    not an authorization token.

    ``statements`` is the item's evidence from the trusted service. When given, the choice is judged against
    the labels in force (``request_labelled_option``) and is not recorded if they change before it is.
    """
    writer = _writer(audit)
    moment = _utc(now)
    if not isinstance(request, OptionRequest) or not isinstance(study, StudyState):
        raise ResponseWindowError("REQUEST_INVALID", "an OptionRequest and a StudyState are required")
    window = load_response_window(tenant_id=tenant_id, project_id=project_id, study_id=study.study_id,
                                  item_id=request.event_id, audit=writer)
    if window is None:
        raise ResponseWindowError("NO_WINDOW", "no response window is open for this item")
    if moment < window.opened_at:
        raise ResponseWindowError("CLOCK_INVALID", "now is before the window opened")
    window = _hold_if_due(writer, window, moment, approved_result_hash_for)
    window = _lapse_if_due(writer, window, moment)
    view = None
    if statements is None:
        result = request_project_option(principal, request, tenant_id=tenant_id, project_id=project_id,
                                        audit=writer, study=study, now=moment, **context)
    else:
        labelled = request_labelled_option(
            principal, request, statements=statements, tenant_id=tenant_id, project_id=project_id,
            audit=writer, study=study, now=moment, **context)
        result, view = labelled.gate, labelled.evidence
    if (not result.executable or request.option not in ANSWERING_OPTIONS
            or window.latest_option not in (None, Option.HOLD.value)):
        return result, window
    key = _key_hash(tenant_id, project_id, study.study_id, request.event_id)
    scope = _scope(tenant_id, project_id, study.study_id, request.event_id)
    if request.option is Option.HOLD:  # the gate has already required a valid, future time
        scope = scope + [f"recheck:{_utc(request.recheck_at).isoformat()}"]
    first = window.decision_count == 0
    if first:
        kind, suffix, extra = _ANSWERED, _ANSWERED, {}
        alert_id = _event_id(_HELD, key)
        late = window.hold_reason is not None
        reason = _AFTER_HOLD if late else _IN_TIME
    else:
        number = window.decision_count + 1
        kind, suffix, extra = _REDECIDED, f"{_REDECIDED}-{number}", {"sequence": number}
        alert_id = _event_id(f"{_LAPSED}-{window.decision_count}", key)
        late = bool(window.recheck_alert_due_subject_ids)
        reason = _AFTER_RECHECK if late else _BEFORE_RECHECK

    def alert_state_unchanged(db: sqlite3.Connection) -> None:
        if view is not None and request.option is not Option.HOLD:
            require_unchanged(db, view)
        if _exists(db, alert_id) is not late:
            raise ResponseWindowError("WINDOW_CHANGED", "the hold state changed; submit the choice again")

    event = _event(
        kind, key, scope, moment, subject_id=result.subject_id, operation=result.option, decision="allow",
        reason=reason, duration_ms=(moment - window.opened_at) // timedelta(milliseconds=1),
        action_fingerprint=result.action_fingerprint, **extra)
    event["event_id"] = _event_id(suffix, key)
    try:
        _append(writer, event, alert_state_unchanged)
    except AuditReplayError as exc:
        raise ResponseWindowError("WINDOW_CHANGED", "the item was answered concurrently") from exc
    return result, _read_windows(writer)[key]


def unreviewed_items(*, tenant_id: str, project_id: str, study_id: str,
                     audit: AnchoredAuditChain) -> tuple[ResponseWindow, ...]:
    """The study's items still ``unreviewed event pending``, ordered by item id.

    While this is not empty, whoever shows or publishes the study's forecast must stamp it with
    ``UNREVIEWED_EVENT_PENDING``. Nothing here applies the stamp, and an item that never had a window opened
    is unknown to it. A trusted service-side read; it performs no caller permission check.
    """
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id)
    return tuple(sorted(
        (w for w in _read_windows(writer).values()
         if (w.tenant_id, w.project_id, w.study_id) == (tenant_id, project_id, study_id)
         and w.unreviewed_event_pending),
        key=lambda w: w.item_id))


__all__ = [
    "ANSWERING_OPTIONS", "HELD_LAST_APPROVED", "HELD_LOOKUP_FAILED", "HELD_NO_APPROVED", "RESPONSE_WINDOW",
    "ResponseWindow", "ResponseWindowError", "UNREVIEWED_EVENT_PENDING", "load_response_window",
    "open_response_window", "respond_to_item", "sweep_response_windows", "unreviewed_items",
]

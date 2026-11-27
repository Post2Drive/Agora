"""Retractions and corrections of event items (DECISION_CELL_SPEC 2A).

A retraction or correction is a new item linked to the original. This module records that link in the
anchored audit chain, and answers two questions: which of the items a result rests on are retracted
(``retraction_stamps``), and which run choices the gate had allowed on an item (``allowed_run_attempts``).

Rules chosen here:

* Recording a link needs the same person as a CONFIRMED label: the recorded project owner, or a delegate
  named in the stored project record, holding the high-assurance approver role. The link is permanent, so it
  is not a member action. Refused attempts are audited.
* Both items need a recorded statement list, and the correcting item's first list must have been recorded
  after the original's. That makes it the newer item and rules out cycles.
* One correcting item links to one original. An original may have several.
* A link is never withdrawn. Retracting a retraction does not clear the stamp on the first original.
* A link forbids no option. It changes the item's evidence view (``evidence``), so a later deciding choice
  must be made on a view that includes it, and an earlier second approval does not cover that choice.

Limits. Nothing checks that the new item really retracts or corrects anything; that is the approver's claim.
The chain keeps a hash of the reason, not the text. A result is stamped only if whoever shows it calls
``retraction_stamps`` with every item it rests on: nothing here knows that set, and no report, result store
or screen calls it. ``allowed_run_attempts`` lists gate passes recorded with this item's labels. A pass is
not proof that anything ran. It does not list attempts made before the item had a statement list, or on
another item that took this one as a CHANGE_INPUTS input (the chain keeps only hashes of inputs).
``tenant_id`` and ``audit`` come from the service's configuration. Reads perform no caller permission check.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from agora.audit_anchor import AnchoredAuditChain, AnchorWriteError, verify_anchored
from agora.audit_chain import AuditReplayError
from agora.decision_cell.options import (
    RUN_OPTIONS,
    DecisionCellError,
    Option,
    statement_set_event_id,
)
from agora.decision_cell.project_store import (
    _canonical,
    _hash,
    _identifier,
    _writer,
    load_project_record,
)
from agora.decision_cell.project_store import (
    _event_id as _record_event_id,
)
from agora.policy import POLICY_VERSION
from agora.principal import Principal, decide_principal

BASED_ON_RETRACTED_ITEM = "based on retracted item"
_PREFIX = "dc-item-correction-"
_EVENT_TYPE = "decision_cell_item_correction"
_RUN_OPERATIONS = frozenset(o.value for o in RUN_OPTIONS | {Option.CHANGE_INPUTS})


class CorrectionKind(str, Enum):
    RETRACTION = "retraction"
    CORRECTION = "correction"


class CorrectionError(DecisionCellError):
    """A refused or untrustworthy retraction or correction operation. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ItemCorrection:
    tenant_id: str
    project_id: str
    study_id: str
    item_id: str                    # the original
    correcting_item_id: str         # the new item
    kind: CorrectionKind
    recorded_by_subject_id: str
    sequence: int                   # 1, 2, ... for this original
    audit_sequence: int             # position in the audit chain


@dataclass(frozen=True)
class RunAttempt:
    """A run choice the gate allowed on an item. Not proof that it ran."""
    event_id: str
    option: str
    subject_id: str
    action_fingerprint: str
    # True if the gate pass was recorded before the item's first retraction or correction.
    made_before_any_link: bool


def _event_id(tenant_id: str, project_id: str, study_id: str, item_id: str, sequence: int) -> str:
    return f"{_PREFIX}{_hash(_canonical([tenant_id, project_id, study_id, item_id]))}-{sequence}"


def _scope(tenant_id: str, project_id: str, study_id: str) -> list[str]:
    return [f"tenant:{tenant_id}", f"project:{project_id}", f"study:{study_id}"]


def _check_ids(*values: object) -> None:
    if not all(_identifier(v) for v in values):
        raise CorrectionError("ID_INVALID", "ids must be exact non-empty strings")


def _rows(writer: AnchoredAuditChain, sql: str, parameters: tuple) -> list:
    """Rows read from a cleanly anchored chain."""
    try:
        with writer.anchors.lock():
            state = verify_anchored(writer.chain, writer.anchors)
            if not state["valid"]:
                raise CorrectionError("AUDIT_UNANCHORED", state["status"])
            return writer.chain.db.execute(sql, parameters).fetchall()
    except CorrectionError:
        raise
    except Exception as exc:
        raise CorrectionError("STORE_ERROR", "the audit chain could not be read") from exc


def load_item_corrections(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                          audit: AnchoredAuditChain) -> tuple[ItemCorrection, ...]:
    """The retractions and corrections of this original, in the order recorded. A trusted service-side read."""
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, item_id)
    prefix = _event_id(tenant_id, project_id, study_id, item_id, 1)[:-1]
    rows = _rows(writer, "SELECT seq, event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? "
                         "ORDER BY seq", (len(prefix), prefix))
    expected = _scope(tenant_id, project_id, study_id) + [f"item:{item_id}"]
    links = []
    for sequence, (audit_sequence, event_id, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
            resources = event["resource_ids"]
            tag = "correcting_item:"
            if (event_id != f"{prefix}{sequence}" or event["sequence"] != sequence
                    or event["event_type"] != _EVENT_TYPE or event["decision"] != "allow"
                    or resources[:-1] != expected or not resources[-1].startswith(tag)):
                raise ValueError("a link does not match its id")
            links.append(ItemCorrection(
                tenant_id, project_id, study_id, item_id, resources[-1][len(tag):],
                CorrectionKind(event["reason"]), event["subject_id"], sequence, audit_sequence))
        except Exception as exc:
            raise CorrectionError("STORE_INCONSISTENT", "the correction history is not usable") from exc
    return tuple(links)


def require_no_newer_correction(db: sqlite3.Connection, tenant_id: str, project_id: str, study_id: str,
                                item_id: str, known: int) -> None:
    """Inside an append transaction: refuse if the item gained a retraction or correction since the read."""
    newer = _event_id(tenant_id, project_id, study_id, item_id, known + 1)
    if db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (newer,)).fetchone():
        raise CorrectionError("CORRECTIONS_CHANGED", "the item was retracted or corrected; read it again")


def record_item_correction(
    principal: Principal | None, *, tenant_id: str, project_id: str, study_id: str, item_id: str,
    correcting_item_id: str, kind: CorrectionKind, reason_text: str, expected_count: int,
    audit: AnchoredAuditChain, now: datetime | None = None,
) -> ItemCorrection:
    """Link a new item to the original as its retraction or correction.

    ``expected_count`` is the number of links the original already has. Raises ``CorrectionError``; nothing
    was linked unless the code is ``AUDIT_ANCHOR_WRITE_FAILED``.
    """
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, item_id, correcting_item_id)
    if not isinstance(kind, CorrectionKind):
        raise CorrectionError("KIND_INVALID", "say whether this is a retraction or a correction")
    current = load_item_corrections(
        tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id, audit=writer)
    subject = principal.subject_id if isinstance(principal, Principal) else "unknown"
    resources = _scope(tenant_id, project_id, study_id) + [
        f"item:{item_id}", f"correcting_item:{correcting_item_id}"]

    def refuse(code: str, detail: str = "") -> CorrectionError:
        try:
            writer.append({
                "event_id": f"dc-correction-denied-{uuid.uuid4().hex}",
                "event_type": f"{_EVENT_TYPE}_denied", "subject_id": subject,
                "operation": "record_item_correction", "decision": "deny",
                "policy_version": POLICY_VERSION, "reason": code, "resource_ids": resources,
            })
        except Exception as exc:
            raise CorrectionError("AUDIT_FAILED", f"refused ({code}) and not recorded") from exc
        return CorrectionError(code, detail)

    stored = load_project_record(tenant_id=tenant_id, project_id=project_id, audit=writer)
    if stored is None:
        raise refuse("NO_PROJECT_RECORD")
    decision, role = decide_principal(
        principal, "decision_approval",
        {"project_id": project_id, "tenant_id": tenant_id, "source_sensitivity": "internal"},
        now=now, required_role="approver")
    if role is None:
        raise refuse("NOT_PERMITTED", decision["reason"])
    if subject != stored.record.owner_subject_id and subject not in stored.record.delegate_subject_ids:
        raise refuse("NOT_DESIGNATED_APPROVER")
    try:
        reason_hash = _hash(_canonical(reason_text)) if reason_text.strip() else None
    except (AttributeError, UnicodeEncodeError):
        reason_hash = None
    if reason_hash is None:
        raise refuse("REASON_MISSING")
    if type(expected_count) is not int or expected_count != len(current):
        raise refuse("COUNT_CONFLICT", "the item's links changed since they were read")
    if correcting_item_id == item_id:
        raise refuse("SAME_ITEM", "the retraction or correction must be a new item")

    first_listed = []
    for listed_item in (item_id, correcting_item_id):
        rows = _rows(writer, "SELECT seq FROM audit_events WHERE event_id=?",
                     (statement_set_event_id(tenant_id, project_id, study_id, listed_item, 1),))
        if not rows:
            raise refuse("ITEM_NOT_REGISTERED", "both items need a recorded statement list")
        first_listed.append(rows[0][0])
    if first_listed[1] <= first_listed[0]:
        raise refuse("NOT_A_NEWER_ITEM", "the correcting item must have been recorded after the original")

    sequence = len(current) + 1
    event_id = _event_id(tenant_id, project_id, study_id, item_id, sequence)

    def still_allowed(db: sqlite3.Connection) -> None:
        newer = _record_event_id(tenant_id, project_id, stored.version + 1)
        if db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (newer,)).fetchone():
            raise CorrectionError("RECORD_CHANGED", "the project record changed; submit again")
        # Checked inside the write transaction, so two writers cannot both link the same new item.
        others = db.execute(
            "SELECT event_json FROM audit_events WHERE substr(event_id, 1, ?)=? AND event_id<>?",
            (len(_PREFIX), _PREFIX, event_id)).fetchall()
        for (raw,) in others:
            other = json.loads(raw)["resource_ids"]
            if other[:3] == resources[:3] and other[-1] == resources[-1]:
                raise CorrectionError("ALREADY_LINKED", "this item already retracts or corrects an item")

    try:
        writer.append({
            "event_id": event_id, "event_type": _EVENT_TYPE, "subject_id": subject,
            "operation": "record_item_correction", "decision": "allow", "policy_version": POLICY_VERSION,
            "sequence": sequence, "reason": kind.value, "record_hash": stored.record_hash,
            "reason_text_hash": reason_hash, "resource_ids": resources,
        }, in_transaction=still_allowed)
    except CorrectionError as exc:
        if exc.code == "ALREADY_LINKED":
            raise refuse(exc.code, "this item already retracts or corrects an item") from exc
        raise
    except AuditReplayError as exc:
        raise CorrectionError("COUNT_CONFLICT", "another link was recorded first") from exc
    except AnchorWriteError as exc:
        raise CorrectionError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; reconcile first") from exc
    except Exception as exc:
        raise CorrectionError("AUDIT_FAILED", "the link could not be recorded") from exc
    return load_item_corrections(
        tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id,
        audit=writer)[sequence - 1]


def retraction_stamps(*, tenant_id: str, project_id: str, study_id: str, item_ids: tuple[str, ...],
                      audit: AnchoredAuditChain) -> tuple[tuple[str, str], ...]:
    """``(item id, "based on retracted item")`` for each given item that has a retraction, ordered by id.

    Give every item the result rests on; whoever shows the result must show these. An empty answer means only
    that no retraction is recorded for the items given.
    """
    if not isinstance(item_ids, tuple) or not item_ids:
        raise CorrectionError("ITEMS_REQUIRED", "give a non-empty tuple of the items the result rests on")
    _check_ids(*item_ids)
    return tuple(
        (item_id, BASED_ON_RETRACTED_ITEM) for item_id in sorted(set(item_ids))
        if any(link.kind is CorrectionKind.RETRACTION for link in load_item_corrections(
            tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id, audit=audit)))


def allowed_run_attempts(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                         audit: AnchoredAuditChain) -> tuple[RunAttempt, ...]:
    """Run choices the gate allowed on this item with its labels, in order. See the module limits."""
    links = load_item_corrections(
        tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id, audit=audit)
    first_link = links[0].audit_sequence if links else None
    prefix = "decision-cell-"
    rows = _rows(_writer(audit), "SELECT seq, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? "
                                 "ORDER BY seq", (len(prefix), prefix))
    wanted = _scope(tenant_id, project_id, study_id) + [f"item:{item_id}"]
    found = []
    for sequence, raw in rows:
        try:
            event = json.loads(raw)
            if (event["event_type"] == "decision_cell_option" and event["decision"] == "allow"
                    and event["operation"] in _RUN_OPERATIONS
                    and event.get("resource_ids", [])[:4] == wanted):
                found.append(RunAttempt(
                    event["event_id"], event["operation"], event["subject_id"], event["action_fingerprint"],
                    first_link is None or sequence < first_link))
        except Exception as exc:
            raise CorrectionError("STORE_INCONSISTENT", "a gate entry is not usable") from exc
    return tuple(found)


__all__ = ["BASED_ON_RETRACTED_ITEM", "CorrectionError", "CorrectionKind", "ItemCorrection", "RunAttempt",
           "allowed_run_attempts", "load_item_corrections", "record_item_correction",
           "require_no_newer_correction", "retraction_stamps"]

"""Fail-closed gate for the human options (DECISION_CELL_SPEC sections 3 and 3A).

The gate answers one question: may THIS person run THIS option, for THIS request,
now? It runs nothing, calls no model, reads no feed and changes no study.

Trust boundary. ``ProjectRecord``, ``StudyState``, ``Escalation``, grants, input
sensitivity, the cost estimate, the snapshot probe and the evidence hash come from the trusted
service layer, never from request input; the gate cannot authenticate them. Only
``OptionRequest`` is the person's request. Identity comes from an adapter-issued
Principal. A ``GateResult`` is not an authorization token: an executor must call
the gate again immediately before acting, and a fork must still go through
``Simulation.fork_from``, which re-verifies the snapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from agora import protection as _protection
from agora.policy import POLICY_VERSION, SENSITIVITY_RANK
from agora.principal import Principal, decide_principal


# The furthest ahead one HOLD may defer an item. The spec names no limit; without one, a single HOLD could
# silence an item for good.
MAX_RECHECK = timedelta(days=7)
_SHA256 = re.compile(r"[0-9a-f]{64}")


class DecisionCellError(PermissionError):
    """Raised when a decision-cell attempt cannot be recorded."""


class Option(str, Enum):
    IGNORE = "IGNORE"
    HOLD = "HOLD"
    CONTINUE = "CONTINUE"
    FORK_FROM_EVENT = "FORK_FROM_EVENT"
    FORK_FROM_EARLIER = "FORK_FROM_EARLIER"
    RERUN_FROM_START = "RERUN_FROM_START"
    CHANGE_INPUTS = "CHANGE_INPUTS"
    COMPARE = "COMPARE"
    ESCALATE = "ESCALATE"


MEMBER_OPTIONS = frozenset({Option.IGNORE, Option.HOLD, Option.COMPARE, Option.ESCALATE})
RUN_OPTIONS = frozenset({Option.CONTINUE, Option.FORK_FROM_EVENT, Option.FORK_FROM_EARLIER,
                         Option.RERUN_FROM_START})
# Options that decide something about the event on its evidence. HOLD defers, COMPARE looks and ESCALATE
# asks, so a view that has since changed does not block those.
EVIDENCE_DECIDING_OPTIONS = frozenset({Option.IGNORE, Option.CHANGE_INPUTS}) | RUN_OPTIONS
# Branches executed per option: the spec prices a fork as two branches (with and without the event).
_BRANCHES = {Option.CONTINUE: 1, Option.FORK_FROM_EVENT: 2, Option.FORK_FROM_EARLIER: 2,
             Option.RERUN_FROM_START: 1}


class EscalationStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    tenant_id: str
    owner_subject_id: str
    # Empty by default. Only people the owner recorded for THIS project (spec 2A, 9.3).
    delegate_subject_ids: frozenset[str] = frozenset()
    second_approver_subject_id: str | None = None
    requires_second_approval: bool = False
    # Alerted (never authorised) when a response window expires. Only if the owner names one (spec 3).
    backup_contact_subject_id: str | None = None


@dataclass(frozen=True)
class StudyState:
    study_id: str
    current_round: int
    kill_switch: bool = False


@dataclass(frozen=True)
class InputRef:
    input_id: str
    sensitivity: str
    data_owner_subject_id: str | None = None


@dataclass(frozen=True)
class InputGrant:
    """A data owner's grant for one input, in one project and study, to one person."""
    project_id: str
    study_id: str
    input_id: str
    grantee_subject_id: str
    granted_by_subject_id: str


@dataclass(frozen=True)
class OptionRequest:
    option: Option
    event_id: str
    reason: str
    budget_units: int                       # agent-rounds the person is willing to spend
    event_round: int | None = None
    from_round: int | None = None           # FORK_FROM_EARLIER only
    underlying: Option | None = None        # CHANGE_INPUTS only: the run option it modifies
    inputs: tuple[InputRef, ...] = ()       # CHANGE_INPUTS only: the full chosen evidence set
    confirmed_cost_units: int | None = None  # must equal the cost exactly when over budget
    recheck_at: datetime | None = None      # HOLD only, and required there: when to look again
    viewed_evidence_hash: str | None = None  # the item's evidence view the person was shown


@dataclass(frozen=True)
class Escalation:
    status: EscalationStatus = EscalationStatus.NONE
    answered_by_subject_id: str | None = None
    # The action fingerprint the second approver answered; an approval covers only that action.
    action_fingerprint: str | None = None


@dataclass(frozen=True)
class GateResult:
    option: str
    executable: bool
    failures: tuple[str, ...]           # every failing reason, for the greyed-out display
    subject_id: str
    cost_units: int
    over_budget: bool
    action_fingerprint: str


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _aware_utc(value: Any) -> datetime | None:
    """``value`` in UTC, or None if it is not a usable timezone-aware datetime."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=repr)
    return hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()


def _action_fingerprint(request: OptionRequest, record: ProjectRecord, study: StudyState,
                        cost: int, evidence_hash: str | None = None) -> str:
    """What would actually run. Excludes who asks, their reason, budget and confirmation."""
    action = {
        "project_id": record.project_id, "tenant_id": record.tenant_id, "study_id": study.study_id,
        "current_round": study.current_round, "event_id": request.event_id,
        "option": request.option, "underlying": request.underlying,
        "event_round": request.event_round, "from_round": request.from_round,
        # key=repr: a malformed request must still be refused and audited, not crash the sort.
        "inputs": sorted(([i.input_id, i.sensitivity, i.data_owner_subject_id]
                          for i in request.inputs), key=repr),
        "cost_units": cost,
    }
    if request.recheck_at is not None:  # added only when set, so other actions keep their fingerprint
        due = _aware_utc(request.recheck_at)
        action["recheck_at"] = due.isoformat() if due else repr(request.recheck_at)
    if evidence_hash is not None:  # so a second approval lapses when the labels or their evidence change
        action["evidence_hash"] = evidence_hash
    return _sha(action)


def statement_set_event_id(tenant_id: Any, project_id: Any, study_id: Any, item_id: Any, version: int) -> str:
    """The audit event id of one version of an item's statement list (see ``statements``)."""
    return "dc-item-statements-" + _sha([tenant_id, project_id, study_id, item_id, version])


def _has_statement_list(db: Any, record: ProjectRecord, study: StudyState, item_id: Any) -> bool:
    event_id = statement_set_event_id(record.tenant_id, record.project_id, study.study_id, item_id, 1)
    return db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (event_id,)).fetchone() is not None


def evaluate_option(
    principal: Principal | None,
    request: OptionRequest,
    *,
    record: ProjectRecord,
    study: StudyState,
    branch_cost_units: int | None = None,
    snapshot_verifies: Callable[[str, int], bool] | None = None,
    escalation: Escalation = Escalation(),
    grants: tuple[InputGrant, ...] = (),
    now: datetime | None = None,
    evidence_hash: str | None = None,
    labels_required: bool = False,
) -> GateResult:
    """Evaluate every check and return all failures. Pure apart from calling the snapshot probe."""
    if not isinstance(request, OptionRequest) or not isinstance(request.option, Option):
        raise DecisionCellError("request must be an OptionRequest with a known Option")
    failures: list[str] = []

    def fail(code: str) -> None:
        if code not in failures:
            failures.append(code)

    if not all(_text(v) for v in (record.project_id, record.tenant_id, record.owner_subject_id)):
        fail("project_record_incomplete")
    if not _text(study.study_id) or not _count(study.current_round):
        fail("study_state_invalid")
    if not _text(request.event_id):
        fail("event_missing")
    elif request.event_id != request.event_id.strip() or not request.event_id.isprintable():
        fail("event_id_not_exact")  # a padded id would name no item's recorded statements
    if not _text(request.reason):
        fail("reason_missing")

    # -- evidence view --------------------------------------------------------
    viewed = request.viewed_evidence_hash
    if labels_required and evidence_hash is None and request.option in EVIDENCE_DECIDING_OPTIONS:
        fail("item_labels_required")
    if evidence_hash is None:
        if viewed is not None:
            fail("evidence_not_supplied")  # the person's view cannot be checked, so it is not ignored
    elif not (isinstance(evidence_hash, str) and _SHA256.fullmatch(evidence_hash)):
        fail("evidence_hash_invalid")
    elif request.option in EVIDENCE_DECIDING_OPTIONS:
        if viewed is None:
            fail("evidence_view_required")
        elif viewed != evidence_hash:
            fail("evidence_changed_since_viewed")

    # -- re-check time --------------------------------------------------------
    if request.option is Option.HOLD:
        if request.recheck_at is None:
            fail("recheck_time_required")
        else:
            due = _aware_utc(request.recheck_at)
            current = _aware_utc(datetime.now(timezone.utc) if now is None else now)
            if due is None or current is None:
                fail("recheck_time_invalid")
            elif due <= current:
                fail("recheck_time_not_in_future")
            elif due - current > MAX_RECHECK:
                fail("recheck_time_too_far")
    elif request.recheck_at is not None:
        fail("recheck_not_allowed")

    # -- permission ----------------------------------------------------------
    resource = {"project_id": record.project_id, "tenant_id": record.tenant_id,
                "source_sensitivity": "internal"}
    member, member_role = decide_principal(principal, "decision_cell_member", resource, now=now)
    if member_role is None:
        fail(f"not_project_member:{member['reason']}")
    subject = principal.subject_id if isinstance(principal, Principal) else "unknown"

    # CHANGE_INPUTS takes the permission, snapshot and budget rules of the run it modifies.
    run: Option | None = request.option if request.option in RUN_OPTIONS else None
    if request.option is Option.CHANGE_INPUTS:
        if request.underlying in RUN_OPTIONS:
            run = request.underlying
        else:
            fail("underlying_run_required")
        if not request.inputs:
            fail("inputs_required")
    else:
        if request.underlying is not None:
            fail("underlying_not_allowed")
        if request.inputs:
            fail("inputs_not_allowed")  # otherwise a run could carry evidence past the grant check

    needs_approver = request.option not in MEMBER_OPTIONS
    if needs_approver:
        approval, role = decide_principal(principal, "decision_approval", resource, now=now,
                                          required_role="approver")
        if role is None:
            fail(f"approver_required:{approval['reason']}")
        delegates = record.delegate_subject_ids
        # A string would match by substring, so anything but a set counts as no delegates.
        if not isinstance(delegates, frozenset):
            delegates = frozenset()
        if subject != record.owner_subject_id and subject not in delegates:
            fail("not_designated_approver")

    # -- escalation ----------------------------------------------------------
    if not isinstance(escalation.status, EscalationStatus):
        fail("escalation_state_invalid")
    elif escalation.status is EscalationStatus.PENDING:
        fail("escalation_pending")  # blocks every option, including a second ESCALATE
    elif escalation.status is EscalationStatus.REJECTED and needs_approver:
        fail("escalation_rejected")
    if request.option is Option.ESCALATE and not _text(record.second_approver_subject_id):
        fail("second_approver_not_named")

    # -- kill switch ---------------------------------------------------------
    if needs_approver and study.kill_switch is not False:
        fail("kill_switch_on")

    # -- sensitive inputs ----------------------------------------------------
    if request.option is Option.CHANGE_INPUTS:
        ids = [i.input_id for i in request.inputs]
        if len(ids) != len(set(ids)):
            fail("duplicate_input")
        for item in request.inputs:
            if not _text(item.input_id) or item.sensitivity not in SENSITIVITY_RANK:
                fail("input_sensitivity_unknown")
                continue
            if SENSITIVITY_RANK[item.sensitivity] < SENSITIVITY_RANK["personal"]:
                continue
            owner = item.data_owner_subject_id
            if not _text(owner) or InputGrant(
                    record.project_id, study.study_id, item.input_id, subject, owner) not in grants:
                fail(f"data_owner_grant_missing:{item.input_id}")

    # -- snapshot ------------------------------------------------------------
    cost = 0
    over_budget = False
    if run is not None:
        snapshot_round: int | None = None
        needs_snapshot = run is not Option.RERUN_FROM_START
        if run is Option.CONTINUE:
            snapshot_round = study.current_round
        elif run is Option.FORK_FROM_EVENT:
            snapshot_round = request.event_round
        elif run is Option.FORK_FROM_EARLIER:
            snapshot_round = request.from_round
            if not (_count(request.from_round) and _count(request.event_round)
                    and request.from_round < request.event_round):
                fail("from_round_not_before_event")
        if run is not Option.FORK_FROM_EARLIER and request.from_round is not None:
            fail("from_round_not_allowed")
        if needs_snapshot:
            if not _count(snapshot_round) or not _count(study.current_round) \
                    or snapshot_round > study.current_round:
                fail("snapshot_round_invalid")
            else:
                try:
                    verified = snapshot_verifies is not None \
                        and snapshot_verifies(study.study_id, snapshot_round) is True
                except Exception:
                    verified = False
                if not verified:
                    fail("snapshot_unavailable")  # never silently replaced by a rerun

        # -- budget ----------------------------------------------------------
        if not _count(branch_cost_units) or branch_cost_units == 0:
            fail("cost_estimate_missing")
        else:
            cost = branch_cost_units * _BRANCHES[run]
        if not _count(request.budget_units):
            fail("budget_invalid")
        elif cost > request.budget_units:
            over_budget = True
            if not (type(request.confirmed_cost_units) is int and request.confirmed_cost_units == cost):
                fail("budget_confirmation_required")

    fingerprint = _action_fingerprint(request, record, study, cost, evidence_hash)

    # -- second approval of this exact action ---------------------------------
    if needs_approver:
        approved = escalation.status is EscalationStatus.APPROVED
        if approved:
            second = record.second_approver_subject_id
            if not _text(second) or escalation.answered_by_subject_id != second or second == subject:
                fail("second_approval_not_independent")
            if escalation.action_fingerprint != fingerprint:
                fail("second_approval_for_different_action")
        elif record.requires_second_approval is not False:
            fail("second_approval_required")

    return GateResult(option=request.option.value, executable=not failures, failures=tuple(failures),
                      subject_id=subject, cost_units=cost, over_budget=over_budget,
                      action_fingerprint=fingerprint)


def request_option(principal: Principal | None, request: OptionRequest, *, audit: Any,
                   record_hash: str | None = None, audit_flags: tuple[str, ...] = (),
                   in_transaction: Callable[[Any], None] | None = None, **context: Any) -> GateResult:
    """Evaluate a person's choice and audit the attempt, allowed or blocked.

    If the attempt cannot be recorded this raises, so nothing may proceed. The
    chain keeps only safe fields: failure codes, the cost in units, and hashes of
    the action and the reason text. The reason text itself is the caller's to keep.

    ``audit_flags`` are service-built ids recorded with the attempt. ``in_transaction`` runs inside the
    append, so it needs an anchored writer; a ``DecisionCellError`` it raises keeps its type and nothing is
    recorded.
    """
    if audit is None:
        raise DecisionCellError("an audit writer is required")
    if "labels_required" in context:
        raise DecisionCellError("whether labels are required is read from the audit chain, not supplied")
    # An item with a recorded statement list may be decided only on its labels.
    db = getattr(getattr(audit, "chain", audit), "db", None)
    record, study = context.get("record"), context.get("study")
    unlabelled = (db is not None and context.get("evidence_hash") is None
                  and isinstance(request, OptionRequest) and request.option in EVIDENCE_DECIDING_OPTIONS
                  and isinstance(record, ProjectRecord) and isinstance(study, StudyState))
    labels_required = False
    if unlabelled:
        try:
            labels_required = _has_statement_list(db, record, study, request.event_id)
        except Exception as exc:
            raise DecisionCellError("the item's statement list could not be checked") from exc
    result = evaluate_option(principal, request, labels_required=labels_required, **context)
    event = {
        "event_id": f"decision-cell-{uuid.uuid4().hex}",
        "event_type": "decision_cell_option",
        "subject_id": result.subject_id,
        "operation": result.option,
        "decision": "allow" if result.executable else "deny",
        "policy_version": POLICY_VERSION,
        "reason": ",".join(code.split(":", 1)[0] for code in result.failures) or "gate_passed",
        "count": result.cost_units,
        "action_fingerprint": result.action_fingerprint,
        "reason_text_hash": _sha(request.reason),
        "request_hash": _sha({
            "action": result.action_fingerprint, "budget_units": request.budget_units,
            "confirmed_cost_units": request.confirmed_cost_units,
        }),
    }
    if record_hash is not None:
        event["record_hash"] = record_hash  # which stored project-record version was judged
    if context.get("evidence_hash") is not None:
        event["evidence_hash"] = context["evidence_hash"]
    if audit_flags:
        event["resource_ids"] = list(audit_flags)
    try:
        writer = audit
        if _protection.ANCHOR_REQUIRED or in_transaction is not None:
            from agora.audit_anchor import require_anchored
            writer = require_anchored(audit)
        commit_check = in_transaction
        if unlabelled and result.executable and hasattr(writer, "anchors"):
            def commit_check(tx: Any) -> None:
                # A list recorded after the check above must not be passed by.
                if _has_statement_list(tx, record, study, request.event_id):
                    raise DecisionCellError("the item gained a statement list; submit the choice with its labels")
                if in_transaction is not None:
                    in_transaction(tx)
        if commit_check is None:
            writer.append(event)
        else:
            writer.append(event, in_transaction=commit_check)
    except DecisionCellError:
        raise
    except Exception as exc:
        raise DecisionCellError("the decision-cell attempt could not be recorded") from exc
    return result

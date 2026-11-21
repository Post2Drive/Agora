"""Human approval lifecycle for immutable decision-record versions."""
from __future__ import annotations

from datetime import date, datetime, timezone
from collections.abc import Mapping
from typing import Any

from .permissions import authorize_decision_approval
from .schema import DecisionRecord, DecisionRecordError, load_decision_record
from .store import DecisionRecordStore


class ApprovalTransitionError(ValueError):
    """Raised when a decision lifecycle transition is stale or invalid."""


def _time(value: datetime | str | None) -> datetime:
    if value is None:
        result = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ApprovalTransitionError("transition time must be RFC3339") from None
    else:
        raise ApprovalTransitionError("transition time must be a datetime or RFC3339 string")
    if result.tzinfo is None:
        raise ApprovalTransitionError("transition time must include a timezone")
    return result.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _current(store: DecisionRecordStore, decision_id: str, expected_version: int) -> DecisionRecord:
    try:
        current = store.get(decision_id, expected_version)
    except DecisionRecordError as exc:
        raise ApprovalTransitionError(str(exc)) from exc
    versions = store.versions(decision_id)
    if not versions or versions[-1].version != expected_version:
        raise ApprovalTransitionError("stale decision version; reload the latest version")
    return current


def _next(
    current: DecisionRecord,
    *,
    status: str,
    actor: str,
    method: str,
    occurred_at: str,
    approver: str | None = None,
) -> DecisionRecord:
    payload = current.as_dict()
    payload.update({
        "version": current.version + 1,
        "status": status,
        "updated_at": occurred_at,
        "approval_method": method,
        "supersedes": current.fingerprint,
    })
    payload.pop("fingerprint", None)
    if approver is None:
        payload.pop("approver", None)
    else:
        payload["approver"] = approver
    try:
        return load_decision_record(payload)
    except DecisionRecordError as exc:
        raise ApprovalTransitionError(str(exc)) from exc


def _event(record: DecisionRecord, transition: str, actor: str, method: str,
           occurred_at: str, **details: Any) -> dict[str, Any]:
    return {
        "transition": transition,
        "actor": actor,
        "method": method,
        "occurred_at": occurred_at,
        "decision_fingerprint": record.fingerprint,
        **details,
    }


def propose(
    store: DecisionRecordStore,
    decision_id: str,
    expected_version: int,
    *,
    actor: str,
    method: str = "manual",
    now: datetime | str | None = None,
) -> DecisionRecord:
    """Move a draft to proposed; only its named proposer may submit it."""
    current = _current(store, decision_id, expected_version)
    if current.status != "draft":
        raise ApprovalTransitionError("only a draft decision can be proposed")
    if actor != current.proposer or actor == current.reviewer:
        raise ApprovalTransitionError("proposal actor must be the proposer, distinct from reviewer")
    moment = _time(now)
    if date.fromisoformat(current.review_date) < moment.date():
        raise ApprovalTransitionError("decision review date has expired")
    stamp = _stamp(moment)
    updated = _next(current, status="proposed", actor=actor, method=method, occurred_at=stamp)
    store.append_transition(updated, _event(updated, "proposed", actor, method, stamp))
    return updated


def approve(
    store: DecisionRecordStore,
    decision_id: str,
    expected_version: int,
    *,
    actor: str,
    role: str,
    subject: Mapping[str, Any],
    expected_fingerprint: str,
    expected_scope: Mapping[str, Any],
    expected_evidence_refs: list[dict[str, Any]],
    method: str = "manual",
    resource: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
) -> DecisionRecord:
    """Approve only the exact current proposal after policy and separation checks."""
    current = _current(store, decision_id, expected_version)
    if current.status != "proposed":
        raise ApprovalTransitionError("only a proposed decision can be approved")
    if expected_fingerprint != current.fingerprint:
        raise ApprovalTransitionError("stale decision fingerprint")
    if dict(expected_scope) != current.project_scope:
        raise ApprovalTransitionError("decision scope does not match the reviewed scope")
    if expected_evidence_refs != current.evidence_refs:
        raise ApprovalTransitionError("decision evidence does not match the reviewed evidence")
    if current.proposer == current.reviewer:
        raise ApprovalTransitionError("proposer and reviewer must be different people")
    if actor in {current.proposer, current.reviewer}:
        raise ApprovalTransitionError("approver must differ from proposer and reviewer")
    if not isinstance(subject, Mapping) or subject.get("subject_id") != actor:
        raise ApprovalTransitionError("policy subject must identify the approval actor")

    moment = _time(now)
    if date.fromisoformat(current.review_date) < moment.date():
        raise ApprovalTransitionError("decision approval window has expired")
    policy_resource = dict(resource or {})
    policy_resource.update(current.project_scope)
    policy_resource["resource_ids"] = [decision_id]
    policy_resource.setdefault("source_sensitivity", "internal")
    # This call is mandatory: the central PDP grants decision_approval to
    # approver only and also checks scope and sensitivity.
    policy_decision = authorize_decision_approval(subject, role, policy_resource)

    stamp = _stamp(moment)
    updated = _next(
        current, status="approved", actor=actor, method=method,
        occurred_at=stamp, approver=actor,
    )
    store.append_transition(
        updated,
        _event(updated, "approved", actor, method, stamp),
        policy_decision=policy_decision,
    )
    return updated


def reject(
    store: DecisionRecordStore,
    decision_id: str,
    expected_version: int,
    *,
    actor: str,
    method: str = "manual",
    now: datetime | str | None = None,
) -> DecisionRecord:
    """Allow the assigned reviewer to reject a proposal."""
    current = _current(store, decision_id, expected_version)
    if current.status != "proposed":
        raise ApprovalTransitionError("only a proposed decision can be rejected")
    if actor != current.reviewer or actor == current.proposer:
        raise ApprovalTransitionError("rejection actor must be the assigned reviewer")
    stamp = _stamp(_time(now))
    updated = _next(current, status="rejected", actor=actor, method=method, occurred_at=stamp)
    store.append_transition(updated, _event(updated, "rejected", actor, method, stamp))
    return updated


def expire(
    store: DecisionRecordStore,
    decision_id: str,
    expected_version: int,
    *,
    now: datetime | str,
) -> DecisionRecord:
    """Close an unapproved proposal after its review date has elapsed."""
    current = _current(store, decision_id, expected_version)
    if current.status != "proposed":
        raise ApprovalTransitionError("only a proposed decision can expire")
    moment = _time(now)
    if date.fromisoformat(current.review_date) >= moment.date():
        raise ApprovalTransitionError("decision review date has not elapsed")
    stamp = _stamp(moment)
    actor, method = "system:expiry", "system_expiry"
    updated = _next(current, status="rejected", actor=actor, method=method, occurred_at=stamp)
    store.append_transition(
        updated, _event(updated, "expired", actor, method, stamp, reason="review_date_elapsed")
    )
    return updated


def supersede(
    store: DecisionRecordStore,
    decision_id: str,
    expected_version: int,
    *,
    actor: str,
    replacement_fingerprint: str,
    method: str = "manual",
    now: datetime | str | None = None,
) -> DecisionRecord:
    """Mark a proposed/approved/rejected version superseded without rewriting it."""
    current = _current(store, decision_id, expected_version)
    if current.status not in {"proposed", "approved", "rejected"}:
        raise ApprovalTransitionError("only a proposed, approved, or rejected decision can be superseded")
    permitted = {current.proposer, current.reviewer, current.approver}
    if actor not in permitted:
        raise ApprovalTransitionError("supersession actor must be a decision participant")
    if not isinstance(replacement_fingerprint, str) or not replacement_fingerprint.startswith("sha256:"):
        raise ApprovalTransitionError("replacement fingerprint must be an exact sha256 fingerprint")
    stamp = _stamp(_time(now))
    updated = _next(current, status="superseded", actor=actor, method=method, occurred_at=stamp)
    store.append_transition(
        updated,
        _event(updated, "superseded", actor, method, stamp,
               replacement_fingerprint=replacement_fingerprint),
    )
    return updated


__all__ = [
    "ApprovalTransitionError", "approve", "expire", "propose", "reject", "supersede",
]

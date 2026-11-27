"""Approval of an action proposal by a different person, recorded in the anchored audit chain.

A proposal (``actions.propose_action``) has a digest that the chain already holds. Here an approver
decides that digest once, as someone other than the proposer, and the decision is appended to the
chain under a fixed event ID, so a second decision for the same digest is refused. ``verify_approved_action``
is the check to run before any later step acts: it re-reads the objects and sources, and finds the
proposal and one approving decision in the chain.

An approval lasts at most ``APPROVAL_LIFETIME_SECONDS``. It ends in at most one of two ways: an
approver withdraws it, or ``admit_approved_action`` uses it once for a simulation. Both are appended
under the same fixed event ID, so the chain cannot hold both, or either twice. Nothing here executes
an action.

The chain keeps no free text, so the decider's reason is recorded as a hash only.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from .. import protection as _protection
from ..audit_anchor import AnchorWriteError, require_anchored, verify_anchored
from ..audit_chain import AuditReplayError
from ..security.receipt_gate import CheckedApproval, ReceiptGate
from ..security.signed_receipt import ReceiptError
from ..policy_enforcement import PolicyCallable
from .actions import (
    PROPOSAL_FORMAT, _SENSITIVITY_RANK, _exact_text, proposal_digest, recheck_action_proposal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_DECIDE = "ontology_action_decide"
_PROPOSED_TYPE = "ontology_action_proposed"
_DECISION_PREFIX = "ontology-action-decision-"
# The audit chain keeps only fixed, non-free-text fields, so the outcome is the event type and the
# decider's reason is kept as a hash.
_OUTCOMES = {"approve": "ontology_action_approved", "reject": "ontology_action_rejected"}
_APPROVED_TYPE = _OUTCOMES["approve"]
_WORDS = {"approve": "approved", "reject": "rejected"}
_ADMIT = "ontology_action_admit"
# One event ID for both endings: the chain refuses a repeated ID, so they exclude each other.
_FINAL_PREFIX = "ontology-action-final-"
_ENDINGS = {
    "ontology_action_withdrawn": "this approval was withdrawn",
    "ontology_action_admitted": "this approval was already used",
}
_ENDED = "this approval has already ended"
# Fixed here. A caller may ask for a shorter lifetime, never a longer one.
APPROVAL_LIFETIME_SECONDS = 24 * 60 * 60
_CLOCK_SKEW = timedelta(seconds=30)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lifetime(max_age_seconds: Any) -> timedelta:
    if max_age_seconds is None:
        return timedelta(seconds=APPROVAL_LIFETIME_SECONDS)
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= APPROVAL_LIFETIME_SECONDS:
        raise OntologyError(
            f"max_age_seconds must be a whole number from 1 to {APPROVAL_LIFETIME_SECONDS}")
    return timedelta(seconds=max_age_seconds)


def _fields(store: OntologyObjectStore, document: Any, expected_digest: Any) -> dict[str, Any]:
    """Shape checks and the digest comparison, with no I/O. Returns the fields the decision names."""
    if not isinstance(document, Mapping):
        raise OntologyError("proposal must be a mapping")
    if not isinstance(expected_digest, str) or not _DIGEST.fullmatch(expected_digest):
        raise OntologyError("expected digest must be sha256: followed by 64 lowercase hex digits")
    try:
        matches = proposal_digest(document) == expected_digest
    except (TypeError, ValueError) as exc:
        raise OntologyError("proposal is not canonical JSON content") from exc
    if not matches:
        raise OntologyError("proposal does not match the expected digest")
    try:
        action = document["action_type"]
        fields = {
            "format": document["format"], "project_id": document["project_id"],
            "pack": document["pack_fingerprint"], "action": action["action_type_id"],
            "version": action["version"], "sensitivity": document["sensitivity"],
            "proposed_by": document["proposed_by"], "policy_version": document["policy_version"],
        }
    except (KeyError, TypeError) as exc:
        raise OntologyError("proposal is missing required content") from exc
    if fields["format"] != PROPOSAL_FORMAT or fields["project_id"] != store.project_id:
        raise OntologyError("proposal is not an action proposal for this project")
    if any(not isinstance(fields[k], str) or not fields[k].strip()
           for k in ("pack", "action", "version", "proposed_by", "policy_version")):
        raise OntologyError("proposal is missing required content")
    if fields["sensitivity"] not in _SENSITIVITY_RANK:
        raise OntologyError("proposal has an unknown classification")
    return fields


def _anchored(audit: Any) -> Any:
    try:
        return require_anchored(audit)
    except PermissionError as exc:
        raise OntologyError("approvals need an anchored audit writer") from exc


def _events(writer: Any, digest: str, event_types: Any) -> list[dict[str, Any]]:
    """Chain events of the given types whose last resource ID is this digest, read from a verified chain."""
    event_types = {event_types} if isinstance(event_types, str) else set(event_types)
    try:
        with writer.anchors.lock():
            if not verify_anchored(writer.chain, writer.anchors)["valid"]:
                raise OntologyError("audit chain is not cleanly anchored")
            rows = writer.chain.db.execute(
                "SELECT event_json FROM audit_events WHERE instr(event_json, ?) > 0 ORDER BY seq",
                (digest,)).fetchall()
        found = []
        for (raw,) in rows:
            event = json.loads(raw)
            resources = event.get("resource_ids")
            if (event.get("event_type") in event_types and isinstance(resources, list)
                    and resources and resources[-1] == digest):
                found.append(event)
        return found
    except OntologyError:
        raise
    except Exception as exc:
        raise OntologyError("action proposal events could not be read from the audit chain") from exc


def _proposed_by_this_chain(writer: Any, fields: dict[str, Any], digest: str) -> None:
    """The chain must hold a proposal event with this digest from the person the document names."""
    if not any(e.get("decision") == "allow" and e.get("subject_id") == fields["proposed_by"]
               and e.get("policy_version") == fields["policy_version"]
               for e in _events(writer, digest, _PROPOSED_TYPE)):
        raise OntologyError("this proposal was not recorded in the audit chain by the person it names")


def _principal(decision: Any) -> str:
    subject = decision.get("subject_id") if isinstance(decision, Mapping) else None
    if not isinstance(subject, str) or not subject.strip() or subject == "unknown":
        raise OntologyError("approval requires a principal-bound identity")
    return subject


def _approval(writer: Any, fields: dict[str, Any], digest: str) -> tuple[str, dict[str, Any]]:
    """The one well-formed approving decision for this digest, and who made it."""
    _proposed_by_this_chain(writer, fields, digest)
    decided = _events(writer, digest, _OUTCOMES.values())
    if not decided:
        raise OntologyError("this proposal has not been decided")
    if len(decided) != 1:
        raise OntologyError("this proposal has more than one decision")
    event = decided[0]
    if (event.get("event_id") != _DECISION_PREFIX + digest.split(":", 1)[1]
            or event.get("operation") != _DECIDE or event.get("decision") != "allow"):
        raise OntologyError("the decision event is not well formed")
    if event.get("event_type") != _APPROVED_TYPE:
        raise OntologyError("this proposal was not approved")
    approver = event.get("subject_id")
    if not isinstance(approver, str) or not approver.strip() or approver == fields["proposed_by"]:
        raise OntologyError("the approval is not from someone other than the proposer")
    return approver, event


def _final_id(digest: str) -> str:
    return _FINAL_PREFIX + digest.split(":", 1)[1]


def _not_ended(writer: Any, digest: str) -> None:
    """Refuse a withdrawn or used approval. Anything under the final event ID ends it."""
    ended = _events(writer, digest, _ENDINGS)
    if ended:
        raise OntologyError(_ENDINGS[ended[0]["event_type"]])
    if writer.find_event(_final_id(digest)) is not None:
        raise OntologyError(_ENDED)


def _approved_at(event: Mapping[str, Any]) -> datetime:
    """When the chain writer recorded the decision."""
    try:
        recorded = datetime.fromisoformat(event["recorded_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise OntologyError("the approval has no readable time") from exc
    if recorded.tzinfo is None:
        raise OntologyError("the approval has no readable time")
    return recorded


def _expiry(approved_at: datetime, lifetime: timedelta, now: datetime) -> datetime:
    if now < approved_at - _CLOCK_SKEW:
        raise OntologyError("the approval is dated after the current time")
    try:
        expires_at = approved_at + lifetime
    except OverflowError as exc:
        raise OntologyError("the approval has no readable time") from exc
    if now >= expires_at:
        raise OntologyError("this approval has expired")
    return expires_at


def _end_event(
    writer: Any, event_type: str, operation: str, decision: Any, subject: str,
    resource_ids: list[str], digest: str, *, in_transaction: Any = None, **extra: str,
) -> None:
    try:
        writer.append({
            "event_id": _final_id(digest),
            "event_type": event_type,
            "operation": operation,
            "decision": "allow",
            "subject_id": subject,
            "policy_version": str(decision.get("policy_version", "unknown")),
            "resource_ids": resource_ids,
            "reason": "policy_allow",
            **extra,
        }, in_transaction=in_transaction)
    except AuditReplayError as exc:
        raise OntologyError(_ENDED) from exc
    except AnchorWriteError as exc:
        raise OntologyError(
            "the event was appended but not anchored; the approval is spent, do not act") from exc


def decide_action_proposal(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    outcome: str, reason: str, *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Approve or reject one proposal, once, as someone other than its proposer.

    ``outcome`` is ``approve`` or ``reject``. Refused if the digest was not recorded as proposed by
    the person the document names, if the deciding identity is the proposer, or if the digest
    already has a decision. Executes nothing and does not re-read the objects.
    """
    if outcome not in _OUTCOMES:
        raise OntologyError("outcome must be approve or reject")
    reason = _exact_text(reason, "reason")
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before the chain is read, so a denied caller learns nothing about what was proposed.
    decision = store._authorize(
        _DECIDE, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = _principal(decision)
    if subject == fields["proposed_by"]:
        raise OntologyError("a proposal must be decided by someone other than its proposer")
    _proposed_by_this_chain(writer, fields, expected_digest)
    event_id = _DECISION_PREFIX + expected_digest.split(":", 1)[1]
    if writer.find_event(event_id) is not None:
        raise OntologyError("this proposal already has a decision")
    try:
        writer.append({
            "event_id": event_id,
            "event_type": _OUTCOMES[outcome],
            "operation": _DECIDE,
            "decision": "allow",
            "subject_id": subject,
            "policy_version": str(decision.get("policy_version", "unknown")),
            "resource_ids": resource_ids,
            "reason_hash": "sha256:" + hashlib.sha256(reason.encode("utf-8")).hexdigest(),
            "reason": "policy_allow",
        })
    except AuditReplayError as exc:
        raise OntologyError("this proposal already has a decision") from exc
    return {"digest": expected_digest, "outcome": _WORDS[outcome], "decided_by": subject,
            "proposed_by": fields["proposed_by"]}


def verify_approved_action(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
    max_age_seconds: int | None = None,
) -> dict[str, str]:
    """Raise unless this exact proposal is still valid and holds one live approval from someone else.

    Needs read authority (the objects and sources are re-read, so a proposal whose pack, objects or
    sources changed is refused), then checks the chain: the proposal was recorded by the person it
    names, its single decision is an approval by a different identity, and that approval has not
    been withdrawn, used or expired. This check consumes nothing; before acting, use
    ``admit_approved_action``.
    """
    lifetime = _lifetime(max_age_seconds)
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    recheck_action_proposal(store, document, expected_digest, policy=policy, audit=writer,
                            purpose=purpose, retention=retention)
    approver, event = _approval(writer, fields, expected_digest)
    _not_ended(writer, expected_digest)
    expires_at = _expiry(_approved_at(event), lifetime, _now())
    return {"digest": expected_digest, "approved_by": approver, "proposed_by": fields["proposed_by"],
            "expires_at": expires_at.isoformat()}


def withdraw_approval(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    reason: str, *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Withdraw an approval that has not been used. Permanent.

    Needs decision authority and an identity other than the proposer; it need not be the original
    approver. The objects are not re-read, so a stale approval can still be withdrawn. Refused if
    the approval was already used: a withdrawal does not undo an admission.
    """
    reason = _exact_text(reason, "reason")
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    decision = store._authorize(
        _DECIDE, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = _principal(decision)
    if subject == fields["proposed_by"]:
        raise OntologyError("an approval must be withdrawn by someone other than the proposer")
    _approval(writer, fields, expected_digest)
    _not_ended(writer, expected_digest)
    _end_event(writer, "ontology_action_withdrawn", _DECIDE, decision, subject, resource_ids,
               expected_digest,
               reason_hash="sha256:" + hashlib.sha256(reason.encode("utf-8")).hexdigest())
    return {"digest": expected_digest, "withdrawn_by": subject}


@dataclass(frozen=True)
class SignedApproval:
    """A second root of trust for one admission: a signed statement and the receipt gate that checks it.

    ``gate`` is an ``agora.security.receipt_gate.ReceiptGate`` opened from the worker's configuration.
    """

    gate: Any
    envelope: Mapping[str, Any]


def _refused(exc: ReceiptError) -> OntologyError:
    return OntologyError(f"the signed approval statement was refused ({exc.code})")


def _check_signed_approval(
    signed: Any, fields: Mapping[str, Any], digest: str, approver: str, store: OntologyObjectStore,
) -> CheckedApproval:
    """Verify the statement against what this chain says, never against its own claims."""
    if not isinstance(signed, SignedApproval):
        raise OntologyError("admission requires a signed approval statement")
    if not isinstance(signed.gate, ReceiptGate):
        raise OntologyError("the signed approval statement needs a ReceiptGate")
    request = {"project": store.project_id, "proposal_digest": digest,
               "proposed_by": fields["proposed_by"], "approved_by": approver}
    try:
        return signed.gate.check_approval(signed.envelope, request=request)
    except ReceiptError as exc:
        raise _refused(exc) from exc


def admit_approved_action(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
    max_age_seconds: int | None = None, signed_approval: SignedApproval | None = None,
) -> dict[str, str]:
    """Use a live approval, once, to admit the action for simulation. Executes nothing.

    Needs admission authority and read authority, and an identity other than the approver. The
    caller must not start the simulation unless this returns. Under the protected defaults a
    ``SignedApproval`` is required: a statement signed with a key from the gate's accepted key list,
    naming this tenant, release, project, digest, proposer and the approver this chain recorded. The
    statement lasts at most five minutes and must not expire after the approval. While the chain's
    write lock is held, the approval's and the statement's expiry are checked again, and the store
    being written must still have the gate's key list as its newest, fresh one. The admission event
    records the statement's hash. The objects are re-read before that lock, not inside it.
    """
    lifetime = _lifetime(max_age_seconds)
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before anything is read, at the proposal's own classification.
    decision = store._authorize(
        _ADMIT, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = _principal(decision)
    live = verify_approved_action(
        store, document, expected_digest, policy=policy, audit=writer, purpose=purpose,
        retention=retention, max_age_seconds=max_age_seconds)
    if subject == live["approved_by"]:
        raise OntologyError("an action must be admitted by someone other than its approver")
    checked = None
    if _protection.SIGNED_APPROVAL_REQUIRED or signed_approval is not None:
        checked = _check_signed_approval(
            signed_approval, fields, expected_digest, live["approved_by"], store)
        if checked.expires_at > datetime.fromisoformat(live["expires_at"]):
            raise OntologyError("the signed approval statement outlives the approval")
    expires_at = datetime.fromisoformat(live["expires_at"])
    approved_at = expires_at - lifetime

    def still_live(db: Any) -> None:
        _expiry(approved_at, lifetime, _now())
        if checked is None:
            return
        if _now() >= checked.expires_at:
            raise OntologyError("the signed approval statement expired before admission")
        try:
            checked.recheck(db)
        except ReceiptError as exc:
            raise _refused(exc) from exc

    proof = {} if checked is None else {"approval_statement_hash": checked.statement_hash}
    _end_event(writer, "ontology_action_admitted", _ADMIT, decision, subject, resource_ids,
               expected_digest, in_transaction=still_live, **proof)
    return {**live, "admitted_by": subject, **proof}


__all__ = [
    "APPROVAL_LIFETIME_SECONDS", "SignedApproval", "admit_approved_action", "decide_action_proposal",
    "verify_approved_action", "withdraw_approval",
]

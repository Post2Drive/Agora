"""The one outcome of a simulation that an admitted action allowed, recorded in the anchored chain.

``approvals.admit_approved_action`` uses an approval once. This module records what the caller says
happened next: ``succeeded`` or ``failed``, with the digest of the caller's result, once per
proposal. It runs nothing, so it does not show that a simulation ran, that the digest is of a real
result, or that nothing else was done with the admission.

The admission is read again from the chain. The dictionary ``admit_approved_action`` returned is
not an input.

``read_simulation_outcome`` reads a recorded outcome back, and refuses unless the chain holds one
approval, then one admission, then one outcome from the admitter, each well formed.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from ..audit_anchor import AnchorWriteError
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from .approvals import (
    _ADMIT, _APPROVED_TYPE, _DIGEST, _ENDINGS, _OUTCOMES, _anchored, _approval, _events, _fields, _final_id,
    _principal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_OUTCOME = "ontology_action_outcome"
_OUTCOME_PREFIX = "ontology-action-outcome-"
_ADMITTED_TYPE = "ontology_action_admitted"
_STATUSES = {"succeeded": "ontology_action_simulation_succeeded",
             "failed": "ontology_action_simulation_failed"}
_STATUS_OF_TYPE = {event_type: status for status, event_type in _STATUSES.items()}
_READ = "ontology_read"
_ALREADY = "this admission already has an outcome"


def _admission(writer: Any, fields: dict[str, Any], digest: str,
               resource_ids: list[str]) -> str:
    """Who admitted this proposal, from its approval and its one well-formed admission event."""
    approver, _ = _approval(writer, fields, digest)
    endings = _events(writer, digest, _ENDINGS)
    if len(endings) != 1 or endings[0].get("event_type") != _ADMITTED_TYPE:
        raise OntologyError("this proposal has not been admitted for simulation")
    event = endings[0]
    if (event.get("event_id") != _final_id(digest) or event.get("operation") != _ADMIT
            or event.get("decision") != "allow" or event.get("resource_ids") != resource_ids):
        raise OntologyError("the admission event is not well formed")
    admitter = event.get("subject_id")
    if not isinstance(admitter, str) or not admitter.strip() or admitter == approver:
        raise OntologyError("the admission is not from someone other than the approver")
    return admitter


def record_simulation_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    status: str, result_digest: str, *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Record, once, how the simulation allowed by an admission ended. Runs nothing.

    ``status`` is ``succeeded`` or ``failed``; ``result_digest`` is the ``sha256:`` digest of the
    result or failure report, which the caller keeps. Needs outcome authority, and the identity
    that admitted the action. The objects are not re-read and the approval need not still be
    unexpired: both were checked at admission, and a later change must not hide what happened.
    """
    if not isinstance(status, str) or status not in _STATUSES:
        raise OntologyError("status must be succeeded or failed")
    if not isinstance(result_digest, str) or not _DIGEST.fullmatch(result_digest):
        raise OntologyError("result digest must be sha256: followed by 64 lowercase hex digits")
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before the chain is read, at the proposal's own classification.
    decision = store._authorize(
        _OUTCOME, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = _principal(decision)
    if subject != _admission(writer, fields, expected_digest, resource_ids):
        raise OntologyError("only the identity that admitted the action can record its outcome")
    event_id = _OUTCOME_PREFIX + expected_digest.split(":", 1)[1]
    if writer.find_event(event_id) is not None:
        raise OntologyError(_ALREADY)
    try:
        writer.append({
            "event_id": event_id,
            "event_type": _STATUSES[status],
            "operation": _OUTCOME,
            "decision": "allow",
            "subject_id": subject,
            "policy_version": str(decision.get("policy_version", "unknown")),
            "resource_ids": resource_ids,
            "result_hash": result_digest,
            "reason": "policy_allow",
        })
    except AuditReplayError as exc:
        raise OntologyError(_ALREADY) from exc
    except AnchorWriteError as exc:
        raise OntologyError(
            "the outcome was appended but not anchored; reconcile the audit chain") from exc
    return {"digest": expected_digest, "status": status, "result_digest": result_digest,
            "recorded_by": subject}


def _recorded_outcome(writer: Any, digest: str, resource_ids: list[str],
                      admitter: str) -> dict[str, Any]:
    """The one well-formed outcome event for this digest, written after its admission."""
    event_id = _OUTCOME_PREFIX + digest.split(":", 1)[1]
    found = _events(writer, digest, _STATUS_OF_TYPE)
    if not found:
        if writer.find_event(event_id) is not None:
            raise OntologyError("the outcome event is not well formed")
        raise OntologyError("this proposal has no recorded outcome")
    if len(found) != 1:
        raise OntologyError("this proposal has more than one outcome")
    event = found[0]
    result_hash = event.get("result_hash")
    if (event.get("event_id") != event_id or event.get("operation") != _OUTCOME
            or event.get("decision") != "allow" or event.get("resource_ids") != resource_ids
            or not isinstance(result_hash, str) or not _DIGEST.fullmatch(result_hash)):
        raise OntologyError("the outcome event is not well formed")
    if event.get("subject_id") != admitter:
        raise OntologyError("the outcome is not from the identity that admitted the action")
    # One read of all three kinds, so they are compared in the chain's own order. The caller has
    # already required exactly one decision and one ending.
    order = [e.get("event_type") for e in _events(
        writer, digest, [*_OUTCOMES.values(), *_ENDINGS, *_STATUS_OF_TYPE])]
    if order != [_APPROVED_TYPE, _ADMITTED_TYPE, event["event_type"]]:
        raise OntologyError("the approval, admission and outcome are not in that order")
    return event


def read_simulation_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None, result: bytes | None = None,
) -> dict[str, Any]:
    """Return the recorded outcome of an admitted action, or raise. Runs nothing.

    Needs ``ontology_read`` authority at the proposal's classification, decided before the chain is
    searched for the proposal. The chain must be cleanly anchored and hold the proposal from the
    person it names, one approval by someone else, then one admission by someone other than the
    approver, then one outcome by that admitter. The objects, sources and approval age are not
    checked again. Pass the kept result or failure report as ``result`` to require that its
    SHA-256 is the recorded digest; ``result_checked`` says whether that was done.

    The outcome is still the admitter's report: ``source`` is always ``reported_by_admitter``.
    """
    if result is not None and not isinstance(result, bytes):
        raise OntologyError("result must be the exact bytes of the kept result or report")
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    store._authorize(
        _READ, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    admitter = _admission(writer, fields, expected_digest, resource_ids)
    approver, _ = _approval(writer, fields, expected_digest)
    event = _recorded_outcome(writer, expected_digest, resource_ids, admitter)
    recorded = event["result_hash"]
    if result is not None and "sha256:" + hashlib.sha256(result).hexdigest() != recorded:
        raise OntologyError("the result does not match the recorded digest")
    return {"digest": expected_digest, "status": _STATUS_OF_TYPE[event["event_type"]],
            "result_digest": recorded, "result_checked": result is not None,
            "proposed_by": fields["proposed_by"], "approved_by": approver,
            "admitted_by": admitter, "recorded_by": event["subject_id"],
            "recorded_at": event.get("recorded_at"), "source": "reported_by_admitter"}


__all__ = ["read_simulation_outcome", "record_simulation_outcome"]

"""The one outcome of a simulation that an admitted action allowed, recorded in the anchored chain.

``approvals.admit_approved_action`` uses an approval once. This module records what the caller says
happened next: ``succeeded`` or ``failed``, with the digest of the caller's result, once per
proposal. It runs nothing, so it does not show that a simulation ran, that the digest is of a real
result, or that nothing else was done with the admission.

The admission is read again from the chain. The dictionary ``admit_approved_action`` returned is
not an input. ``read_simulation_outcome`` returns a recorded outcome only after checking the chain
events behind it and their order.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..audit_anchor import AnchorWriteError
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from .approvals import (
    _ADMIT, _DIGEST, _ENDINGS, _OUTCOMES, _PROPOSED_TYPE, _anchored, _approval, _events, _fields,
    _final_id, _principal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_OUTCOME = "ontology_action_outcome"
_OUTCOME_PREFIX = "ontology-action-outcome-"
_ADMITTED_TYPE = "ontology_action_admitted"
_STATUSES = {"succeeded": "ontology_action_simulation_succeeded",
             "failed": "ontology_action_simulation_failed"}
_ALREADY = "this admission already has an outcome"
_BAD_OUTCOME = "the outcome event is not well formed"


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


def _outcome_id(digest: str) -> str:
    return _OUTCOME_PREFIX + digest.split(":", 1)[1]


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
    event_id = _outcome_id(expected_digest)
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


def read_simulation_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Return the one recorded outcome of a proposal, or raise. Writes only the read decision.

    Needs read authority at the proposal's classification and a principal-bound identity. The
    chain must hold the proposal from the person the document names, then one approval from someone
    else, then one admission by someone other than the approver, then one outcome from that
    admitter, in that order. As with recording, the objects are not re-read. The result is still
    the admitter's report: this does not show that a simulation ran.
    """
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before the chain is read, so a denied caller learns nothing about what happened.
    _principal(store._authorize(
        "ontology_read", resource_ids, policy=policy, audit=writer,
        sensitivity=fields["sensitivity"]))
    admitter = _admission(writer, fields, expected_digest, resource_ids)
    approver, _ = _approval(writer, fields, expected_digest)
    # One pass in chain order. Each lookup above is by type; none of them compares positions.
    history = _events(writer, expected_digest, {
        _PROPOSED_TYPE, *_OUTCOMES.values(), *_ENDINGS, *_STATUSES.values()})
    steps = [e for e in history if e.get("event_type") != _PROPOSED_TYPE]
    reported = [e for e in steps if e.get("event_type") in _STATUSES.values()]
    event_id = _outcome_id(expected_digest)
    if not reported:
        # An event under the outcome ID that the typed read did not return is not "no outcome".
        if writer.find_event(event_id) is not None:
            raise OntologyError(_BAD_OUTCOME)
        raise OntologyError("no outcome has been recorded for this proposal")
    if len(reported) != 1:
        raise OntologyError("this proposal has more than one outcome")
    event = reported[0]
    result_digest = event.get("result_hash")
    if (event.get("event_id") != event_id or event.get("operation") != _OUTCOME
            or event.get("decision") != "allow" or event.get("subject_id") != admitter
            or event.get("resource_ids") != resource_ids
            or not isinstance(result_digest, str) or not _DIGEST.fullmatch(result_digest)
            or not isinstance(event.get("recorded_at"), str)):
        raise OntologyError(_BAD_OUTCOME)
    # ``_approval`` and ``_admission`` found one decision and one ending, so with the one outcome
    # there are three steps here. The outcome must be last, after the decision and the admission.
    proposed_first = any(
        e.get("event_type") == _PROPOSED_TYPE and e.get("decision") == "allow"
        and e.get("subject_id") == fields["proposed_by"]
        and e.get("policy_version") == fields["policy_version"]
        for e in history[:history.index(steps[0])])
    if (not proposed_first
            or [e.get("event_type") for e in steps]
            != ["ontology_action_approved", _ADMITTED_TYPE, event["event_type"]]):
        raise OntologyError("the chain does not hold these events in order")
    status = next(name for name, kind in _STATUSES.items() if kind == event["event_type"])
    return {"digest": expected_digest, "status": status, "result_digest": result_digest,
            "recorded_by": admitter, "recorded_at": event["recorded_at"],
            "proposed_by": fields["proposed_by"], "approved_by": approver}


__all__ = ["read_simulation_outcome", "record_simulation_outcome"]

"""The one outcome of a simulation that an admitted action allowed, recorded in the anchored chain.

``approvals.admit_approved_action`` uses an approval once. This module records what the caller says
happened next: ``succeeded`` or ``failed``, with the digest of the caller's result, once per
proposal. It runs nothing, so it does not show that a simulation ran, that the digest is of a real
result, or that nothing else was done with the admission.

The admission is read again from the chain. The dictionary ``admit_approved_action`` returned is
not an input.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .. import protection as _protection
from ..audit_anchor import AnchorWriteError
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from .approvals import (
    _ADMIT, _CO_TYPE, _DIGEST, _ENDINGS, _anchored, _approval, _events, _fields, _final_id, _principal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_OUTCOME = "ontology_action_outcome"
_OUTCOME_PREFIX = "ontology-action-outcome-"
_ADMITTED_TYPE = "ontology_action_admitted"
_STATUSES = {"succeeded": "ontology_action_simulation_succeeded",
             "failed": "ontology_action_simulation_failed"}
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
    # Checked whatever TWO_PERSON_SENSITIVE says now: a recorded second approver never admits.
    if any(e.get("subject_id") == admitter for e in _events(writer, digest, _CO_TYPE)):
        raise OntologyError("the admission is not from someone other than the second approver")
    return admitter


def record_simulation_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    status: str, result_digest: str, *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
) -> dict[str, str]:
    """Record a caller-supplied outcome. Refused under the protected defaults: use ``run_admitted_simulation``.

    With ``protection.RUNNER_ONLY_OUTCOMES`` set (the default) the digest must come from the runner, which
    builds the result document itself, so this entry point raises. When relaxed it behaves as
    ``_record_outcome`` below. Not a boundary against code in this process, which can call the private
    function.
    """
    if _protection.RUNNER_ONLY_OUTCOMES:
        raise OntologyError("outcomes are recorded by run_admitted_simulation, not from a supplied digest")
    return _record_outcome(store, document, expected_digest, status, result_digest, policy=policy,
                           audit=audit, purpose=purpose, retention=retention)


def _record_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    status: str, result_digest: str, *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
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
        _OUTCOME, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"],
        **store._record_privacy(fields["sensitivity"], purpose, retention))
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


__all__ = ["record_simulation_outcome"]

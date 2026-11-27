"""The one outcome of a simulation that an admitted action allowed, recorded in the anchored chain.

``approvals.admit_approved_action`` uses an approval once. This module records what the caller says
happened next: ``succeeded`` or ``failed``, with the digest of the caller's result, once per
proposal. It runs nothing, so it does not show that a simulation ran, that the digest is of a real
result, or that nothing else was done with the admission. ``runner.run_admitted_simulation`` computes
the digest itself; once it has started a run, a hand-reported outcome is refused.

The admission is read again from the chain. The dictionary ``admit_approved_action`` returned is
not an input.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..audit_anchor import AnchorWriteError
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from .approvals import (
    _ADMIT, _DIGEST, _ENDINGS, _anchored, _approval, _events, _fields, _final_id, _principal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_OUTCOME = "ontology_action_outcome"
_OUTCOME_PREFIX = "ontology-action-outcome-"
_ADMITTED_TYPE = "ontology_action_admitted"
_STATUSES = {"succeeded": "ontology_action_simulation_succeeded",
             "failed": "ontology_action_simulation_failed"}
_ALREADY = "this admission already has an outcome"
# Written by ``runner`` before it calls a simulator.
_RUN_PREFIX = "ontology-action-run-"
_RUN_OWNS = "a simulation runner owns this admission's outcome; it cannot be reported by hand"


def _has_event(db: Any, event_id: str) -> bool:
    """Lookup on the chain's own connection, for use inside an append transaction."""
    return db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (event_id,)).fetchone() is not None


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
    run_id = _RUN_PREFIX + expected_digest.split(":", 1)[1]

    def no_run_started(db: Any) -> None:
        if _has_event(db, run_id):
            raise OntologyError(_RUN_OWNS)

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
        }, in_transaction=no_run_started)
    except AuditReplayError as exc:
        raise OntologyError(_ALREADY) from exc
    except AnchorWriteError as exc:
        raise OntologyError(
            "the outcome was appended but not anchored; reconcile the audit chain") from exc
    return {"digest": expected_digest, "status": status, "result_digest": result_digest,
            "recorded_by": subject}


__all__ = ["record_simulation_outcome"]

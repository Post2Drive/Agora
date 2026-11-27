"""A dry-run simulation of an admitted action, and the check of its recorded result. Changes no state.

``run_admitted_simulation`` is for the identity that admitted the action. It rebuilds the proposal from the
objects and sources as they are now (so the preconditions are evaluated again), builds a result document
from what the rebuild shows, and records its digest as the outcome. If the proposal no longer matches, it
records a failed outcome with a failure report instead. If the rebuild cannot be completed for any other
reason, the error is raised, nothing is recorded and the run can be tried again. The caller keeps the result
document; the chain holds only its digest, so ``verify_simulation_result`` can later show that a document is
the one recorded.

What the "simulation" is: the action's declared effects are listed as simulated, next to digests of the
actor and target values and the parameters. The effects are names, not programs, so nothing is applied to
any data and nothing leaves the system. A result shows that a rebuild passed at the time of the run, not
what an effect would have done.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .actions import proposal_digest, recheck_action_proposal
from .approvals import _DIGEST, _anchored, _events, _fields
from .outcomes import _OUTCOME_PREFIX, _STATUSES, _record_outcome
from .registry import ProposalMismatchError
from .store import OntologyError, OntologyObjectStore

RESULT_FORMAT = "agora.ontology.simulation_result/v1"
FAILURE_FORMAT = "agora.ontology.simulation_failure/v1"
_READ = "ontology_read"
_BY_TYPE = {event_type: status for status, event_type in _STATUSES.items()}


def _result_document(document: Mapping[str, Any], digest: str) -> dict[str, Any]:
    action = document["action_type"]
    return {
        "format": RESULT_FORMAT,
        "proposal_digest": digest,
        "pack_fingerprint": document["pack_fingerprint"],
        "action_type": {"action_type_id": action["action_type_id"], "version": action["version"],
                        "fingerprint": action["fingerprint"]},
        "actor_values_sha256": document["actor"]["values_sha256"],
        "target_values_sha256": document["target"]["values_sha256"],
        "parameters_sha256": proposal_digest(document["parameters"]),
        "preconditions_met": list(document.get("preconditions_met", [])),
        "simulated_effects": [{"effect": effect, "simulated": True} for effect in document["declared_effects"]],
        "state_changed": False,
    }


def _failure_document(digest: str) -> dict[str, Any]:
    return {"format": FAILURE_FORMAT, "proposal_digest": digest, "reason": "proposal_no_longer_valid",
            "state_changed": False}


def run_admitted_simulation(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: Any, audit: Any | None, purpose: str | None = None, retention: str | None = None,
) -> dict[str, Any]:
    """Dry-run one admitted action and record the outcome. Returns the result document and what was recorded.

    Only the admitting identity can record, so anyone else is refused after the rebuild and nothing is
    written. A false precondition, a changed or missing source row or a rebuild that differs records a
    failed outcome. Every other error is raised and records nothing, including a refusal by policy and a
    snapshot or ingest record that cannot be read or verified.
    """
    _fields(store, document, expected_digest)
    writer = _anchored(audit)
    try:
        recheck_action_proposal(store, document, expected_digest, policy=policy, audit=writer,
                                purpose=purpose, retention=retention)
        status, report = "succeeded", _result_document(document, expected_digest)
    except ProposalMismatchError:
        # Only a positive finding is recorded. A refusal, an outage or an unverifiable read propagates.
        status, report = "failed", _failure_document(expected_digest)
    recorded = _record_outcome(
        store, document, expected_digest, status, proposal_digest(report), policy=policy, audit=writer)
    return {"status": status, "result": report, "result_digest": recorded["result_digest"],
            "recorded_by": recorded["recorded_by"]}


def verify_simulation_result(
    store: OntologyObjectStore, result: Any, *, policy: Any, audit: Any | None,
) -> dict[str, str]:
    """Raise unless this result or failure document is exactly the one recorded as its proposal's outcome."""
    if not isinstance(result, Mapping) or result.get("format") not in (RESULT_FORMAT, FAILURE_FORMAT):
        raise OntologyError("not a simulation result document")
    digest = result.get("proposal_digest")
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise OntologyError("the result does not name a proposal digest")
    try:
        result_digest = proposal_digest(result)
    except (TypeError, ValueError) as exc:
        raise OntologyError("the result is not canonical JSON content") from exc
    writer = _anchored(audit)
    store._authorize(_READ, [digest], policy=policy, audit=writer)
    found = _events(writer, digest, _BY_TYPE)
    if len(found) != 1:
        raise OntologyError("the proposal has no single recorded outcome")
    event = found[0]
    if (event.get("event_id") != _OUTCOME_PREFIX + digest.split(":", 1)[1] or event.get("decision") != "allow"
            or event.get("operation") != "ontology_action_outcome"
            or not isinstance(event.get("subject_id"), str) or not event["subject_id"].strip()):
        raise OntologyError("the recorded outcome is not well formed")
    if event.get("result_hash") != result_digest:
        raise OntologyError("the document is not the recorded result")
    status = _BY_TYPE[event["event_type"]]
    if (status == "succeeded") != (result["format"] == RESULT_FORMAT):
        raise OntologyError("the document kind does not match the recorded status")
    return {"digest": digest, "status": status, "result_digest": result_digest,
            "recorded_by": event["subject_id"]}


__all__ = ["FAILURE_FORMAT", "RESULT_FORMAT", "run_admitted_simulation", "verify_simulation_result"]

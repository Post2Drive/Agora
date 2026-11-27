"""A dry-run simulation of an admitted action, and the check of its recorded result. Changes no state.

``run_admitted_simulation`` is for the identity that admitted the action. It rebuilds the proposal from the
objects and sources as they are now (so the preconditions are evaluated again), builds a result document
from what the rebuild shows, and records its digest as the outcome. If the proposal no longer matches, it
records a failed outcome with a failure report instead. The caller keeps the result document; the chain
holds only its digest, so ``verify_simulation_result`` can later show that a document is the one recorded.

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
from .approvals import (
    _ADMIT, _CO_PREFIX, _CO_TYPE, _DECIDE, _DECISION_PREFIX, _DIGEST, _ENDINGS, _OUTCOMES, _PROPOSED_TYPE,
    _anchored, _events, _fields, _final_id,
)
from .outcomes import _OUTCOME_PREFIX, _STATUSES, _record_outcome
from .store import OntologyError, OntologyObjectStore

RESULT_FORMAT = "agora.ontology.simulation_result/v1"
FAILURE_FORMAT = "agora.ontology.simulation_failure/v1"
_READ = "ontology_read"
_BY_TYPE = {event_type: status for status, event_type in _STATUSES.items()}
_HISTORY = {_PROPOSED_TYPE, _CO_TYPE, *_OUTCOMES.values(), *_ENDINGS, *_BY_TYPE}


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
    written. A proposal that no longer matches the pack, objects, sources or preconditions records a
    failed outcome; a refusal by policy (including a runner without read authority) is raised and records nothing.
    """
    _fields(store, document, expected_digest)
    writer = _anchored(audit)
    try:
        recheck_action_proposal(store, document, expected_digest, policy=policy, audit=writer,
                                purpose=purpose, retention=retention)
        status, report = "succeeded", _result_document(document, expected_digest)
    except OntologyError as exc:
        if isinstance(exc.__cause__, PermissionError):
            raise  # a refusal by policy is not a finding about the proposal
        status, report = "failed", _failure_document(expected_digest)
    recorded = _record_outcome(
        store, document, expected_digest, status, proposal_digest(report), policy=policy, audit=writer)
    return {"status": status, "result": report, "result_digest": recorded["result_digest"],
            "recorded_by": recorded["recorded_by"]}


def _named(event: Mapping[str, Any]) -> str | None:
    subject = event.get("subject_id")
    return subject if isinstance(subject, str) and subject.strip() and subject != "unknown" else None


def _check_history(history: list[dict[str, Any]], digest: str, outcome: Mapping[str, Any]) -> None:
    """Raise unless the chain shows proposal, approval, any second approval, admission, then this outcome.

    ``history`` is the digest's proposal events in chain order. The caller has no proposal document, so
    the proposer, pack, action and version are the ones the chain's proposal events agree on.
    """
    refused = "the chain does not show an approved and admitted action behind this outcome: "
    at = {kind: [n for n, e in enumerate(history) if e.get("event_type") == kind] for kind in _HISTORY}
    proposals = [n for n in at[_PROPOSED_TYPE]
                 if history[n].get("decision") == "allow" and _named(history[n])]
    if not proposals:
        raise OntologyError(refused + "no recorded proposal")
    first = history[proposals[0]]
    # The same content may be proposed again, so repeats are normal. They must agree.
    if any(any(history[n].get(k) != first.get(k) for k in ("subject_id", "policy_version", "resource_ids"))
           for n in proposals[1:]):
        raise OntologyError(refused + "the proposal records disagree")
    recorded = first["resource_ids"]  # pack, action, version, the bound objects, then the digest
    resources = [*recorded[:3], digest]
    suffix = digest.split(":", 1)[1]

    def step(kinds: Any, event_id: str, operation: str, name: str) -> tuple[int, str]:
        found = sorted(n for kind in kinds for n in at[kind])
        if len(found) != 1:
            raise OntologyError(refused + f"not exactly one {name}")
        event = history[found[0]]
        who = _named(event)
        if (event.get("event_id") != event_id or event.get("operation") != operation
                or event.get("decision") != "allow" or who is None or event.get("resource_ids") != resources):
            raise OntologyError(refused + f"the {name} is not well formed")
        return found[0], who

    decided, approver = step(_OUTCOMES.values(), _DECISION_PREFIX + suffix, _DECIDE, "decision")
    if history[decided]["event_type"] != _OUTCOMES["approve"] or approver == _named(first):
        raise OntologyError(refused + "no approval by someone other than the proposer")
    order, approvers = [proposals[0], decided], [approver]
    # Whether a second approval was required depends on the classification, which the chain does not hold.
    if at[_CO_TYPE]:
        co_at, co = step([_CO_TYPE], _CO_PREFIX + suffix, _DECIDE, "second approval")
        if co in (approver, _named(first)):
            raise OntologyError(refused + "the second approval is not from a third person")
        order.append(co_at)
        approvers.append(co)
    admitted, admitter = step(_ENDINGS, _final_id(digest), _ADMIT, "admission")
    if history[admitted]["event_type"] != "ontology_action_admitted" or admitter in approvers:
        raise OntologyError(refused + "no admission by someone other than an approver")
    reported = history.index(dict(outcome))
    if outcome.get("subject_id") != admitter or outcome.get("resource_ids") != resources:
        raise OntologyError(refused + "the outcome is not the admitter's for this proposal")
    order += [admitted, reported]
    if order != sorted(order):
        raise OntologyError(refused + "the events are out of order")


def verify_simulation_result(
    store: OntologyObjectStore, result: Any, *, policy: Any, audit: Any | None,
) -> dict[str, str]:
    """Raise unless this result or failure document is exactly the one recorded as its proposal's outcome.

    The chain must also show, in this order, the proposal, an approval by someone else, any second
    approval by a third person, an admission by someone who approved neither, and the outcome from that
    admitter. This reads the chain only. It does not re-read objects or sources, check the approval's
    age or a signed statement, or know whether a second approval was required.
    """
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
    history = _events(writer, digest, _HISTORY)  # one verified read, in chain order
    found = [e for e in history if e.get("event_type") in _BY_TYPE]
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
    _check_history(history, digest, event)
    return {"digest": digest, "status": status, "result_digest": result_digest,
            "recorded_by": event["subject_id"]}


__all__ = ["FAILURE_FORMAT", "RESULT_FORMAT", "run_admitted_simulation", "verify_simulation_result"]

"""A recorded simulation outcome, returned only with every step behind it, in chain order. Changes no state.

``outcomes`` records the one outcome of an admitted proposal. ``read_simulation_outcome`` reads it back
after checking the proposal, the approval (and the second approval where one is recorded or required),
the admission and the outcome, and that their positions in the chain are in that order.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..policy_enforcement import PolicyCallable
from .approvals import (
    _APPROVED_TYPE, _CO_TYPE, _DIGEST, _PROPOSED_TYPE, _anchored, _approval, _co_approval, _events,
    _fields, _lifetime, _now, _principal, _two_person,
)
from .outcomes import _ADMITTED_TYPE, _OUTCOME, _OUTCOME_PREFIX, _STATUSES, _admission
from .states import _STATUS_STATES, _TYPES, _derive
from .store import OntologyError, OntologyObjectStore

_READ = "ontology_read"
_BAD_OUTCOME = "the outcome event is not well formed"
_BY_TYPE = {event_type: status for status, event_type in _STATUSES.items()}


def read_simulation_outcome(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Return the one recorded outcome of a proposal, or raise. Writes only the read decision.

    Needs read authority at the proposal's classification and a principal-bound identity. The chain
    must hold the proposal from the person the document names, then one approval from someone else,
    then the second approval where there is one, then one admission by someone who gave neither
    approval, then one outcome from that admitter, in that order. A sensitive proposal needs the
    second approval while ``protection.TWO_PERSON_SENSITIVE`` is set; a second approval that is
    recorded is checked whatever the flag says. The history must also pass the checks of
    ``states.action_proposal_state``. The objects are not re-read and neither signed
    statements nor the approval's age are checked again.
    """
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before the chain is read, so a denied caller learns nothing about what happened.
    _principal(store._authorize(
        _READ, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"]))
    admitter = _admission(writer, fields, expected_digest, resource_ids)
    approver, _ = _approval(writer, fields, expected_digest)
    co_approver = None
    if _two_person(fields) or _events(writer, expected_digest, _CO_TYPE):
        co_approver, _ = _co_approval(writer, fields, expected_digest, approver)
        if admitter == co_approver:
            raise OntologyError("the admission is not from someone other than the second approver")
    # One pass in chain order. Each lookup above is by type; none of them compares positions.
    history = _events(writer, expected_digest, _TYPES)
    steps = [e for e in history if e.get("event_type") != _PROPOSED_TYPE]
    reported = [e for e in steps if e.get("event_type") in _BY_TYPE]
    event_id = _OUTCOME_PREFIX + expected_digest.split(":", 1)[1]
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
    expected_steps = [_APPROVED_TYPE, *([_CO_TYPE] if co_approver else []), _ADMITTED_TYPE,
                      event["event_type"]]
    proposed_first = any(
        e.get("event_type") == _PROPOSED_TYPE and e.get("decision") == "allow"
        and e.get("subject_id") == fields["proposed_by"]
        and e.get("policy_version") == fields["policy_version"]
        for e in history[:history.index(steps[0])])
    if not proposed_first or [e.get("event_type") for e in steps] != expected_steps:
        raise OntologyError("the chain does not hold these events in order")
    # The state view's rules apply too (matching proposal records, the same resources on every step),
    # so this read never reports an outcome for a history the view calls inconsistent.
    view = _derive(expected_digest, history, _now(), _lifetime(None))
    if view["state"] != _STATUS_STATES[event["event_type"]]:
        raise OntologyError(
            f"the proposal state view does not accept this history: {view.get('reason', view['state'])}")
    found = {"digest": expected_digest, "status": _BY_TYPE[event["event_type"]],
             "result_digest": result_digest, "recorded_by": admitter,
             "recorded_at": event["recorded_at"], "proposed_by": fields["proposed_by"],
             "approved_by": approver}
    if co_approver:
        found["co_approved_by"] = co_approver
    return found


__all__ = ["read_simulation_outcome"]

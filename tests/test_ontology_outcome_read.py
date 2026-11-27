"""A recorded outcome is returned only when the chain holds every step behind it, in order."""
import pytest

from agora.ontology import OntologyError, outcomes, read_simulation_outcome
from agora.ontology.actions import proposal_digest
from agora.policy import decide

from test_ontology_action_admission import RUNNER, _admit, _approved
from test_ontology_action_approvals import APPROVER, READER, _decide, _events, catalog, world  # noqa: F401
from test_ontology_action_outcomes import _RESULT, _admitted, _forge, _hex, _record, _resources
from test_ontology_action_proposals import _allow, _deny, _propose


def _read(w, proposal, policy=READER, document=None, digest=None):
    return read_simulation_outcome(
        w.store, document if document is not None else proposal.document, digest or proposal.digest,
        policy=policy, audit=w.audit)


def _forge_outcome(w, proposal, **changes):
    event = {"event_id": "ontology-action-outcome-" + _hex(proposal),
             "event_type": "ontology_action_simulation_succeeded",
             "operation": "ontology_action_outcome", "decision": "allow", "subject_id": "runner-1",
             "policy_version": "v", "resource_ids": _resources(proposal), "result_hash": _RESULT,
             "reason": "policy_allow"}
    event.update(changes)
    w.audit.append({k: v for k, v in event.items() if v is not None})


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_a_recorded_outcome_is_read_back(world, status):
    proposal = _admitted(world)
    _record(world, proposal, status=status)
    (event,) = _events(world, "ontology_action_simulation_" + status)
    expected = {"digest": proposal.digest, "status": status, "result_digest": _RESULT,
                "recorded_by": "runner-1", "recorded_at": event["recorded_at"],
                "proposed_by": "ontology-test-operator", "approved_by": "approver-1"}
    assert _read(world, proposal) == expected
    assert _read(world, proposal) == expected
    assert world.audit.verify()["valid"]


def test_a_repeated_proposal_does_not_hide_the_outcome(world):
    proposal = _admitted(world)
    assert _propose(world).digest == proposal.digest
    _record(world, proposal)
    assert _read(world, proposal)["status"] == "succeeded"


def test_an_admission_without_an_outcome_says_so(world):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="no outcome has been recorded"):
        _read(world, proposal)


@pytest.mark.parametrize("state,message", [
    ("proposed", "has not been decided"), ("approved", "has not been admitted")])
def test_a_forged_outcome_without_the_earlier_steps_is_refused(world, state, message):
    proposal = _propose(world) if state == "proposed" else _approved(world)
    _forge_outcome(world, proposal)
    with pytest.raises(OntologyError, match=message):
        _read(world, proposal)


@pytest.mark.parametrize("changes", [
    {"event_id": "ontology-other-id"}, {"operation": "ontology_action_admit"},
    {"decision": "deny"}, {"subject_id": "runner-2"}, {"subject_id": None},
    {"resource_ids": "short"}, {"result_hash": None}, {"result_hash": "sha256:abc"},
    {"result_hash": 7}, {"recorded_at": 7}])
def test_a_malformed_outcome_event_is_refused(world, changes):
    proposal = _admitted(world)
    if changes.get("resource_ids") == "short":
        changes = {"resource_ids": ["p", proposal.digest]}
    _forge_outcome(world, proposal, **changes)
    with pytest.raises(OntologyError, match="outcome event is not well formed"):
        _read(world, proposal)


@pytest.mark.parametrize("changes", [
    {"event_type": "something_else"}, {"resource_ids": ["unrelated"]}])
def test_an_unreadable_event_under_the_outcome_id_is_not_reported_as_missing(world, changes):
    proposal = _admitted(world)
    _forge_outcome(world, proposal, **changes)
    with pytest.raises(OntologyError, match="outcome event is not well formed"):
        _read(world, proposal)


def test_two_outcomes_are_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    _forge_outcome(world, proposal, event_id="ontology-second-outcome",
                   event_type="ontology_action_simulation_failed")
    with pytest.raises(OntologyError, match="more than one outcome"):
        _read(world, proposal)


def test_an_outcome_before_the_admission_is_refused(world):
    proposal = _approved(world)
    _forge_outcome(world, proposal)
    _admit(world, proposal)
    with pytest.raises(OntologyError, match="in order"):
        _read(world, proposal)


def test_an_admission_before_the_approval_is_refused(world):
    proposal = _propose(world)
    _forge(world, proposal)
    _decide(world, proposal)
    _forge_outcome(world, proposal)
    with pytest.raises(OntologyError, match="in order"):
        _read(world, proposal)


def test_a_proposal_recorded_after_its_approval_is_refused(world):
    first = _propose(world)
    # For a second digest: approval, admission and outcome come before its proposal event.
    other = dict(first.document, reason="a different reason")
    digest = proposal_digest(other)
    resources = _resources(first)[:3] + [digest]
    suffix = digest.split(":")[1]
    for event_id, kind, operation, subject in (
            ("ontology-action-decision-", "ontology_action_approved", "ontology_action_decide", "approver-1"),
            ("ontology-action-final-", "ontology_action_admitted", "ontology_action_admit", "runner-1"),
            ("ontology-action-outcome-", "ontology_action_simulation_succeeded",
             "ontology_action_outcome", "runner-1")):
        world.audit.append({"event_id": event_id + suffix, "event_type": kind, "operation": operation,
                            "decision": "allow", "subject_id": subject, "policy_version": "v",
                            "resource_ids": resources, "result_hash": _RESULT,
                            "reason": "policy_allow"})
    world.audit.append({
        "event_id": "late-proposal", "event_type": "ontology_action_proposed",
        "operation": "ontology_action_propose", "decision": "allow",
        "subject_id": other["proposed_by"], "policy_version": other["policy_version"],
        "resource_ids": resources, "reason": "policy_allow"})
    with pytest.raises(OntologyError, match="in order"):
        read_simulation_outcome(world.store, other, digest, policy=READER, audit=world.audit)


def test_the_read_is_decided_before_the_chain_is_read(world, monkeypatch):
    proposal = _admitted(world)
    _record(world, proposal)
    seen = []

    def deny(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource)

    def unread(*args, **kwargs):
        raise AssertionError("chain read before the decision")

    monkeypatch.setattr(outcomes, "_admission", unread)
    with pytest.raises(OntologyError, match="policy denied"):
        _read(world, proposal, policy=deny)
    assert seen == [("ontology_read", "sensitive")]


def test_an_unknown_identity_cannot_read(world):
    proposal = _admitted(world)
    _record(world, proposal)
    with pytest.raises(OntologyError, match="principal-bound identity"):
        _read(world, proposal, policy=lambda o, r: {**_allow(o, r), "subject_id": "unknown"})


def test_a_changed_proposal_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    with pytest.raises(OntologyError, match="does not match the expected digest"):
        _read(world, proposal, document={**proposal.document, "sensitivity": "public"})


def test_an_unanchored_writer_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    anchored, world.audit = world.audit, world.audit.chain
    try:
        with pytest.raises(OntologyError, match="anchored audit writer"):
            _read(world, proposal)
    finally:
        world.audit = anchored


def test_an_unanchored_tail_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    world.audit.chain.append({"event_id": "unanchored-tail", "event_type": "x", "reason": "policy_allow"})
    with pytest.raises((OntologyError, PermissionError), match="not cleanly anchored"):
        _read(world, proposal)


def test_who_may_read_an_outcome_under_the_central_roles():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_read", resource)["decision"] == "allow"}
    assert allowed == {"operator", "reviewer", "reader"}

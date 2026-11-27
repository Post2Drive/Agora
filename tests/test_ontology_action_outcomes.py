"""One outcome per admitted action, recorded by the admitter from the chain's own record; nothing runs."""
from datetime import datetime, timedelta, timezone

import pytest

from agora.audit_anchor import AnchorStore
from agora.ontology import OntologyError, approvals, outcomes, record_simulation_outcome
from agora.policy import decide

from test_ontology_action_admission import RUNNER, _admit, _approved, _withdraw
from test_ontology_action_approvals import APPROVER, _as, _decide, _events, catalog, world  # noqa: F401
from test_ontology_action_proposals import _allow, _deny, _propose

_RESULT = "sha256:" + "a" * 64
_OTHER = "sha256:" + "b" * 64


def _record(w, proposal, status="succeeded", result=_RESULT, policy=RUNNER, document=None, digest=None):
    return record_simulation_outcome(
        w.store, document if document is not None else proposal.document, digest or proposal.digest,
        status, result, policy=policy, audit=w.audit)


def _outcomes(w):
    return (_events(w, "ontology_action_simulation_succeeded")
            + _events(w, "ontology_action_simulation_failed"))


def _admitted(w):
    proposal = _approved(w)
    _admit(w, proposal)
    return proposal


def _hex(proposal):
    return proposal.digest.split(":")[1]


def _resources(proposal):
    action = proposal.document["action_type"]
    return [proposal.document["pack_fingerprint"], action["action_type_id"], action["version"],
            proposal.digest]


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_the_admitter_records_how_the_simulation_ended(world, status):
    proposal = _admitted(world)
    assert _record(world, proposal, status=status) == {
        "digest": proposal.digest, "status": status, "result_digest": _RESULT, "recorded_by": "runner-1"}
    (event,) = _outcomes(world)
    assert event["event_type"] == "ontology_action_simulation_" + status
    assert event["event_id"] == "ontology-action-outcome-" + _hex(proposal)
    assert event["operation"] == "ontology_action_outcome" and event["subject_id"] == "runner-1"
    assert event["result_hash"] == _RESULT and event["resource_ids"] == _resources(proposal)
    assert event["policy_version"] == "v-runner-1"
    assert _events(world, "ontology_action_executed") == []
    assert world.audit.verify()["valid"]


@pytest.mark.parametrize("second", [("succeeded", _RESULT), ("failed", _RESULT), ("succeeded", _OTHER)])
def test_an_admission_has_one_outcome(world, second):
    proposal = _admitted(world)
    _record(world, proposal, status="failed")
    with pytest.raises(OntologyError, match="already has an outcome"):
        _record(world, proposal, status=second[0], result=second[1])
    assert len(_outcomes(world)) == 1


def test_the_chain_refuses_a_second_outcome_that_raced_the_check(world, monkeypatch):
    proposal = _admitted(world)
    _record(world, proposal)
    monkeypatch.setattr(type(world.audit), "find_event", lambda self, event_id: None)
    with pytest.raises(OntologyError, match="already has an outcome"):
        _record(world, proposal, status="failed")
    assert len(_outcomes(world)) == 1


@pytest.mark.parametrize("state,message", [
    ("proposed", "has not been decided"), ("rejected", "was not approved"),
    ("approved", "has not been admitted"), ("withdrawn", "has not been admitted")])
def test_nothing_is_recorded_without_an_admission(world, state, message):
    proposal = _propose(world)
    if state != "proposed":
        _decide(world, proposal, outcome="reject" if state == "rejected" else "approve")
    if state == "withdrawn":
        _withdraw(world, proposal)
    with pytest.raises(OntologyError, match=message):
        _record(world, proposal)
    assert _outcomes(world) == []


@pytest.mark.parametrize("by", [_as("runner-2"), APPROVER, _allow])
def test_only_the_admitter_records(world, by):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="only the identity that admitted"):
        _record(world, proposal, policy=by)
    assert _outcomes(world) == []


def _forge(w, proposal, **changes):
    event = {"event_id": "ontology-action-final-" + _hex(proposal),
             "event_type": "ontology_action_admitted", "operation": "ontology_action_admit",
             "decision": "allow", "subject_id": "runner-1", "policy_version": "v",
             "resource_ids": _resources(proposal), "reason": "policy_allow"}
    event.update(changes)
    w.audit.append(event)


@pytest.mark.parametrize("changes", [
    {"event_id": "ontology-other-id"}, {"operation": "ontology_action_decide"}, {"decision": "deny"},
    {"resource_ids": "short"}])
def test_a_malformed_admission_event_is_refused(world, changes):
    proposal = _approved(world)
    if changes.get("resource_ids") == "short":
        changes = {"resource_ids": ["p", proposal.digest]}
    _forge(world, proposal, **changes)
    with pytest.raises(OntologyError, match="admission event is not well formed"):
        _record(world, proposal)
    assert _outcomes(world) == []


@pytest.mark.parametrize("subject", ["approver-1", "", None])
def test_an_admission_by_the_approver_or_by_nobody_is_refused(world, subject):
    proposal = _approved(world)
    _forge(world, proposal, subject_id=subject)
    with pytest.raises(OntologyError, match="other than the approver"):
        _record(world, proposal, policy=APPROVER if subject == "approver-1" else RUNNER)
    assert _outcomes(world) == []


def test_two_endings_are_refused(world):
    proposal = _admitted(world)
    _forge(world, proposal, event_id="ontology-second-ending", event_type="ontology_action_withdrawn")
    with pytest.raises(OntologyError, match="has not been admitted"):
        _record(world, proposal)
    assert _outcomes(world) == []


def test_an_admission_without_an_approval_is_refused(world):
    proposal = _propose(world)
    _forge(world, proposal)
    with pytest.raises(OntologyError, match="has not been decided"):
        _record(world, proposal)
    assert _outcomes(world) == []


def test_a_later_change_or_expiry_does_not_hide_the_outcome(world, monkeypatch):
    proposal = _admitted(world)
    later = datetime.now(timezone.utc) + timedelta(days=30)
    monkeypatch.setattr(approvals, "_now", lambda: later)

    def no_reread(*args, **kwargs):
        raise AssertionError("objects must not be re-read")

    monkeypatch.setattr(approvals, "recheck_action_proposal", no_reread)
    assert _record(world, proposal, status="failed")["status"] == "failed"


@pytest.mark.parametrize("status", ["done", "Succeeded", "", None, ["succeeded"]])
def test_only_two_statuses_exist(world, status):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="succeeded or failed"):
        _record(world, proposal, status=status)
    assert _outcomes(world) == []


@pytest.mark.parametrize("result", [
    "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63, _RESULT + "\n", "the run went well", None])
def test_the_result_must_be_a_digest(world, result):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="result digest"):
        _record(world, proposal, result=result)
    assert _outcomes(world) == []


def test_a_changed_proposal_is_refused(world):
    proposal = _admitted(world)
    changed = {**proposal.document, "sensitivity": "public"}
    with pytest.raises(OntologyError, match="does not match the expected digest"):
        _record(world, proposal, document=changed)
    assert _outcomes(world) == []


def test_the_outcome_is_decided_before_the_chain_is_read(world, monkeypatch):
    proposal = _admitted(world)
    seen = []

    def deny(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource)

    def unread(*args, **kwargs):
        raise AssertionError("chain read before the decision")

    monkeypatch.setattr(outcomes, "_admission", unread)
    with pytest.raises(OntologyError, match="policy denied"):
        _record(world, proposal, policy=deny)
    assert seen == [("ontology_action_outcome", "sensitive")]


def test_an_unknown_identity_cannot_record(world):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="principal-bound identity"):
        _record(world, proposal, policy=lambda o, r: {**_allow(o, r), "subject_id": "unknown"})
    assert _outcomes(world) == []


def test_an_unanchored_writer_is_refused(world):
    proposal = _admitted(world)
    anchored, world.audit = world.audit, world.audit.chain
    try:
        with pytest.raises(OntologyError, match="anchored audit writer"):
            _record(world, proposal)
    finally:
        world.audit = anchored
    assert _outcomes(world) == []


def test_a_rolled_back_chain_is_refused(world):
    proposal = _admitted(world)
    world.audit.chain.append({"event_id": "unanchored-tail", "event_type": "x", "reason": "policy_allow"})
    with pytest.raises((OntologyError, PermissionError), match="not cleanly anchored"):
        _record(world, proposal)
    assert _outcomes(world) == []


def test_an_outcome_that_is_not_anchored_says_so(world, monkeypatch):
    proposal = _admitted(world)
    event_id = "ontology-action-outcome-" + _hex(proposal)
    original = AnchorStore.advance

    def fail_on_outcome(self, sequence, head):
        if world.audit.chain.find_event(event_id) is not None:
            raise OSError("disk full")
        return original(self, sequence, head)

    monkeypatch.setattr(AnchorStore, "advance", fail_on_outcome)
    with pytest.raises(OntologyError, match="appended but not anchored"):
        _record(world, proposal)


def test_only_operators_record_outcomes_under_the_central_roles():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_action_outcome", resource)["decision"] == "allow"}
    assert allowed == {"operator"}

"""An approval expires, can be withdrawn, and admits an action for simulation once; nothing executes."""
from datetime import datetime, timedelta, timezone

import pytest

from agora.audit_anchor import AnchorStore
from agora.ontology import (
    APPROVAL_LIFETIME_SECONDS, OntologyError, admit_approved_action, approvals, withdraw_approval,
)
from agora.policy import decide

from test_ontology_action_approvals import (  # noqa: F401
    APPROVER, READER, _as, _decide, _events, _verify, catalog, world,
)
from test_ontology_action_proposals import _allow, _deny, _propose

RUNNER = _as("runner-1")


def _admit(w, proposal, policy=RUNNER, document=None, digest=None, **options):
    return admit_approved_action(
        w.store, document if document is not None else proposal.document, digest or proposal.digest,
        policy=policy, audit=w.audit, purpose="account support", retention="90 days", **options)


def _withdraw(w, proposal, policy=APPROVER, reason="customer asked us to stop"):
    return withdraw_approval(w.store, proposal.document, proposal.digest, reason,
                             policy=policy, audit=w.audit)


def _endings(w):
    return _events(w, "ontology_action_admitted") + _events(w, "ontology_action_withdrawn")


def _approved(w):
    proposal = _propose(w)
    _decide(w, proposal)
    return proposal


def _later(monkeypatch, **delta):
    moment = datetime.now(timezone.utc) + timedelta(**delta)
    monkeypatch.setattr(approvals, "_now", lambda: moment)


def test_an_approval_admits_once(world):
    proposal = _approved(world)
    result = _admit(world, proposal)
    expires = datetime.fromisoformat(result.pop("expires_at"))
    assert result == {"digest": proposal.digest, "approved_by": "approver-1",
                      "proposed_by": "ontology-test-operator", "admitted_by": "runner-1"}
    (approval,) = _events(world, "ontology_action_approved")
    assert expires - datetime.fromisoformat(approval["recorded_at"]) == timedelta(seconds=APPROVAL_LIFETIME_SECONDS)
    (event,) = _endings(world)
    assert event["event_id"] == "ontology-action-final-" + proposal.digest.split(":")[1]
    assert event["subject_id"] == "runner-1" and event["operation"] == "ontology_action_admit"
    assert event["resource_ids"][-1] == proposal.digest and event["policy_version"] == "v-runner-1"
    assert _events(world, "ontology_action_executed") == []
    for again in (RUNNER, _as("runner-2")):
        with pytest.raises(OntologyError, match="already used"):
            _admit(world, proposal, policy=again)
    with pytest.raises(OntologyError, match="already used"):
        _verify(world, proposal)
    with pytest.raises(OntologyError, match="already used"):
        _withdraw(world, proposal)
    assert len(_endings(world)) == 1


def test_the_proposer_may_admit_what_another_person_approved(world):
    proposal = _approved(world)
    assert _admit(world, proposal, policy=_allow)["admitted_by"] == "ontology-test-operator"


def test_the_approver_cannot_admit(world):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="other than its approver"):
        _admit(world, proposal, policy=APPROVER)
    assert _endings(world) == []


@pytest.mark.parametrize("by", [APPROVER, _as("approver-2")])
def test_a_withdrawn_approval_admits_nothing(world, by):
    proposal = _approved(world)
    result = _withdraw(world, proposal, policy=by)
    assert result["digest"] == proposal.digest
    (event,) = _endings(world)
    assert event["event_type"] == "ontology_action_withdrawn" and event["subject_id"] == result["withdrawn_by"]
    assert event["reason_hash"].startswith("sha256:") and "customer asked" not in str(event)
    for step in (_admit, _verify, _withdraw):
        with pytest.raises(OntologyError, match="was withdrawn"):
            step(world, proposal)
    with pytest.raises(OntologyError, match="already has a decision"):
        _decide(world, proposal, policy=_as("approver-3"))
    assert len(_endings(world)) == 1


def test_the_proposer_cannot_withdraw(world):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="other than the proposer"):
        _withdraw(world, proposal, policy=_allow)
    assert _endings(world) == []


@pytest.mark.parametrize("outcome,message", [(None, "has not been decided"), ("reject", "was not approved")])
def test_only_an_approval_can_be_withdrawn_or_used(world, outcome, message):
    proposal = _propose(world)
    if outcome:
        _decide(world, proposal, outcome=outcome)
    for step in (_withdraw, _admit):
        with pytest.raises(OntologyError, match=message):
            step(world, proposal)
    assert _endings(world) == []


@pytest.mark.parametrize("step", [_admit, _verify])
def test_an_approval_expires(world, monkeypatch, step):
    proposal = _approved(world)
    _later(monkeypatch, seconds=APPROVAL_LIFETIME_SECONDS + 1)
    with pytest.raises(OntologyError, match="has expired"):
        step(world, proposal)
    assert _endings(world) == []


def test_an_expired_approval_can_still_be_withdrawn(world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, days=30)
    assert _withdraw(world, proposal)["withdrawn_by"] == "approver-1"


def test_a_caller_can_shorten_the_lifetime(world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, seconds=120)
    with pytest.raises(OntologyError, match="has expired"):
        _admit(world, proposal, max_age_seconds=60)
    assert _admit(world, proposal, max_age_seconds=600)["admitted_by"] == "runner-1"


@pytest.mark.parametrize("value", [0, -1, APPROVAL_LIFETIME_SECONDS + 1, True, 60.0, "60"])
def test_a_caller_cannot_lengthen_or_garble_the_lifetime(world, value):
    proposal = _approved(world)
    for call in (lambda: _admit(world, proposal, max_age_seconds=value),
                 lambda: approvals.verify_approved_action(
                     world.store, proposal.document, proposal.digest, policy=READER, audit=world.audit,
                     purpose="account support", retention="90 days", max_age_seconds=value)):
        with pytest.raises(OntologyError, match="max_age_seconds"):
            call()
    assert _endings(world) == []


def test_an_approval_dated_in_the_future_is_refused(world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, minutes=-10)
    with pytest.raises(OntologyError, match="dated after the current time"):
        _admit(world, proposal)
    assert _endings(world) == []


def test_expiry_is_checked_again_under_the_write_lock(world, monkeypatch):
    """Time passes between the first check and the append: nothing is written."""
    proposal = _approved(world)
    start = datetime.now(timezone.utc)
    times = iter([start, start + timedelta(seconds=APPROVAL_LIFETIME_SECONDS + 1)])
    monkeypatch.setattr(approvals, "_now", lambda: next(times))
    with pytest.raises(OntologyError, match="has expired"):
        _admit(world, proposal)
    assert _endings(world) == []
    assert world.audit.verify()["valid"]


@pytest.mark.parametrize("recorded_at", ["yesterday", "2026-11-27T10:00:00", "", 5])
def test_an_approval_without_a_readable_time_is_refused(world, recorded_at):
    proposal = _propose(world)
    world.audit.append({
        "event_id": "ontology-action-decision-" + proposal.digest.split(":")[1],
        "event_type": "ontology_action_approved", "operation": "ontology_action_decide",
        "decision": "allow", "subject_id": "approver-1", "policy_version": "v",
        "resource_ids": ["p", proposal.digest], "recorded_at": recorded_at, "reason": "policy_allow"})
    with pytest.raises(OntologyError, match="no readable time"):
        _admit(world, proposal)
    assert _endings(world) == []


@pytest.mark.parametrize("first,second", [(_admit, _withdraw), (_withdraw, _admit),
                                          (_admit, _admit), (_withdraw, _withdraw)])
def test_the_chain_refuses_a_second_ending_that_raced_the_check(world, monkeypatch, first, second):
    proposal = _approved(world)
    first(world, proposal)
    monkeypatch.setattr(approvals, "_not_ended", lambda writer, digest: None)
    with pytest.raises(OntologyError, match="already ended"):
        second(world, proposal)
    assert len(_endings(world)) == 1


def test_anything_under_the_final_event_id_ends_the_approval(world):
    proposal = _approved(world)
    world.audit.append({"event_id": "ontology-action-final-" + proposal.digest.split(":")[1],
                        "event_type": "something_else", "resource_ids": ["p"], "reason": "policy_allow"})
    for step in (_verify, _withdraw, _admit):
        with pytest.raises(OntologyError, match="already ended"):
            step(world, proposal)


@pytest.mark.parametrize("kind,message", [("ontology_action_withdrawn", "was withdrawn"),
                                          ("ontology_action_admitted", "already used")])
def test_an_ending_under_another_event_id_still_ends_the_approval(world, kind, message):
    proposal = _approved(world)
    world.audit.append({"event_id": "ontology-other-id", "event_type": kind,
                        "resource_ids": ["p", proposal.digest], "reason": "policy_allow"})
    with pytest.raises(OntologyError, match=message):
        _admit(world, proposal)


def test_an_admission_that_is_not_anchored_is_spent(world, monkeypatch):
    proposal = _approved(world)
    final_id = "ontology-action-final-" + proposal.digest.split(":")[1]
    original = AnchorStore.advance

    def fail_on_admission(self, sequence, head):
        if world.audit.chain.find_event(final_id) is not None:
            raise OSError("disk full")
        return original(self, sequence, head)

    monkeypatch.setattr(AnchorStore, "advance", fail_on_admission)
    with pytest.raises(OntologyError, match="spent, do not act"):
        _admit(world, proposal)
    monkeypatch.setattr(AnchorStore, "advance", original)
    with pytest.raises(PermissionError, match="not cleanly anchored"):   # nothing more until reconciled
        _admit(world, proposal)


def test_admission_is_decided_before_anything_is_read(world):
    proposal = _approved(world)
    seen = []

    def deny(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource)

    with pytest.raises(OntologyError, match="policy denied"):
        _admit(world, proposal, policy=deny)
    assert seen == [("ontology_action_admit", "sensitive")]
    assert _endings(world) == []


def test_withdrawal_is_decided_before_anything_is_read(world):
    proposal = _approved(world)
    seen = []

    def deny(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource)

    with pytest.raises(OntologyError, match="policy denied"):
        _withdraw(world, proposal, policy=deny)
    assert seen == [("ontology_action_decide", "sensitive")]


@pytest.mark.parametrize("step", [_admit, _withdraw])
def test_an_unknown_identity_cannot_end_an_approval(world, step):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="principal-bound identity"):
        step(world, proposal, policy=lambda o, r: {**_allow(o, r), "subject_id": "unknown"})
    assert _endings(world) == []


def test_admission_also_needs_read_authority(world):
    proposal = _approved(world)

    def admit_only(operation, resource):
        return RUNNER(operation, resource) if operation == "ontology_action_admit" else _deny(operation, resource)

    with pytest.raises(OntologyError, match="policy denied"):
        _admit(world, proposal, policy=admit_only)
    assert _endings(world) == []


def test_only_operators_admit_under_the_central_roles():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_action_admit", resource)["decision"] == "allow"}
    assert allowed == {"operator"}


@pytest.mark.parametrize("step", [_admit, _withdraw])
def test_an_unanchored_writer_is_refused(world, step):
    proposal = _approved(world)
    anchored, world.audit = world.audit, None
    try:
        with pytest.raises(OntologyError, match="anchored audit writer"):
            step(world, proposal)
    finally:
        world.audit = anchored

"""Where each action proposal stands, read from the chain; reads only."""
from datetime import timedelta

import pytest

from agora.ontology import (
    OntologyError, action_proposal_state, approvals, list_action_proposals, record_simulation_outcome,
)

from test_ontology_action_admission import RUNNER, _admit, _approved, _later, _withdraw
from test_ontology_action_approvals import APPROVER, _as, _decide, _events, catalog, world  # noqa: F401
from test_ontology_action_proposals import _allow, _deny, _propose

RESULT = "sha256:" + "a" * 64
READER = _as("reader-1")


def _state(w, proposal, policy=READER, **kw):
    return action_proposal_state(w.store, proposal.document, proposal.digest, policy=policy, audit=w.audit, **kw)


def _list(w, policy=READER, **kw):
    return list_action_proposals(w.store, policy=policy, audit=w.audit, **kw)


def _outcome(w, proposal, status="succeeded"):
    return record_simulation_outcome(w.store, proposal.document, proposal.digest, status, RESULT,
                                     policy=RUNNER, audit=w.audit)


def test_each_step_moves_the_state_and_names_who_did_it(world):
    proposal = _propose(world)
    assert _state(world, proposal) == {"digest": proposal.digest, "proposed_by": "ontology-test-operator",
                                       "state": "proposed"}
    _decide(world, proposal)
    approved = _state(world, proposal)
    assert approved["state"] == "approved" and approved["decided_by"] == "approver-1" and approved["expires_at"]
    _admit(world, proposal)
    assert _state(world, proposal)["state"] == "admitted" and _state(world, proposal)["admitted_by"] == "runner-1"
    _outcome(world, proposal)
    done = _state(world, proposal)
    assert done["state"] == "simulation_succeeded" and done["result_hash"] == RESULT


def test_proposing_the_same_content_again_does_not_change_the_state(world):
    proposal = _propose(world)
    assert _propose(world).digest == proposal.digest
    assert _state(world, proposal)["state"] == "proposed"
    _decide(world, proposal)
    _admit(world, proposal)
    assert _propose(world).digest == proposal.digest  # also after the admission
    assert _state(world, proposal)["state"] == "admitted"
    _outcome(world, proposal)
    assert _state(world, proposal)["state"] == "simulation_succeeded"
    assert [(e["digest"], e["state"]) for e in _list(world)] == [(proposal.digest, "simulation_succeeded")]


def test_a_failed_outcome_is_its_own_state(world):
    proposal = _approved(world)
    _admit(world, proposal)
    _outcome(world, proposal, "failed")
    assert _state(world, proposal)["state"] == "simulation_failed"


def test_rejected_withdrawn_and_expired(world, monkeypatch):
    rejected = _propose(world)
    _decide(world, rejected, outcome="reject")
    assert _state(world, rejected)["state"] == "rejected"
    withdrawn = _propose(world, reason="two")
    _decide(world, withdrawn)
    _withdraw(world, withdrawn)
    entry = _state(world, withdrawn)
    assert entry["state"] == "withdrawn" and entry["ended_by"] == "approver-1"
    expiring = _propose(world, reason="three")
    _decide(world, expiring)
    assert _state(world, expiring)["state"] == "approved"
    _later(monkeypatch, hours=25)
    assert _state(world, expiring)["state"] == "expired"
    assert _state(world, expiring, max_age_seconds=3600)["state"] == "expired"


def test_a_shorter_lifetime_expires_an_approval_sooner(world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, minutes=10)
    assert _state(world, proposal)["state"] == "approved"
    assert _state(world, proposal, max_age_seconds=60)["state"] == "expired"


def test_listing_gives_one_entry_per_proposal_and_filters_by_state(world):
    one, two, three = _propose(world), _propose(world, reason="two"), _propose(world, reason="three")
    _decide(world, two)
    _decide(world, three, outcome="reject")
    entries = _list(world)
    assert [(e["digest"], e["state"]) for e in entries] == [
        (one.digest, "proposed"), (two.digest, "approved"), (three.digest, "rejected")]
    assert [e["digest"] for e in _list(world, state="approved")] == [two.digest]
    assert _list(world, state="admitted") == []


def test_an_empty_chain_lists_nothing(world):
    assert _list(world) == []


def test_a_proposal_that_was_never_recorded_is_reported_not_guessed(world):
    proposal = _propose(world)
    # a second world's proposal document with a digest this chain never saw
    other = _propose(world, reason="never recorded here")
    chain_state = _state(world, other)
    assert chain_state["state"] == "proposed"
    from agora.ontology import actions
    forged = {**proposal.document, "proposed_by": "someone-else"}
    digest = actions.proposal_digest(forged)
    entry = action_proposal_state(world.store, forged, digest, policy=READER, audit=world.audit)
    assert entry["state"] == "inconsistent" and "not recorded" in entry["reason"]


def test_a_document_naming_a_different_proposer_is_inconsistent(world, monkeypatch):
    proposal = _propose(world)
    from agora.ontology import states
    real = states._derive

    def other(digest, events, now, lifetime):
        entry = real(digest, events, now, lifetime)
        return {**entry, "proposed_by": "someone-else"}

    monkeypatch.setattr(states, "_derive", other)
    entry = _state(world, proposal)
    assert entry["state"] == "inconsistent" and "someone other" in entry["reason"]


def test_reading_needs_read_authority_and_listing_needs_the_highest_classification(world):
    proposal = _propose(world)
    with pytest.raises(Exception):
        _state(world, proposal, policy=_deny)
    with pytest.raises(Exception):
        _list(world, policy=_deny)


def test_reading_changes_nothing_in_the_decision_chain(world):
    proposal = _approved(world)
    before = _events(world, "ontology_action_approved")
    _state(world, proposal)
    _list(world)
    assert _events(world, "ontology_action_approved") == before
    assert _events(world, "ontology_action_admitted") == []


def test_a_bad_digest_or_document_is_refused(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError):
        action_proposal_state(world.store, proposal.document, "sha256:" + "0" * 64, policy=READER, audit=world.audit)
    with pytest.raises(OntologyError):
        action_proposal_state(world.store, "not a mapping", proposal.digest, policy=READER, audit=world.audit)
    with pytest.raises(OntologyError):
        _state(world, proposal, max_age_seconds=0)


def test_a_chain_that_is_not_anchored_is_refused(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError):
        action_proposal_state(world.store, proposal.document, proposal.digest, policy=READER, audit=None)
    with pytest.raises(OntologyError):
        list_action_proposals(world.store, policy=READER, audit=None)


def _ev(event_type, subject="x", **extra):
    return {"event_type": event_type, "subject_id": subject, "decision": "allow",
            "resource_ids": ["pack", "action", "1", DIGEST], **extra}


DIGEST = "sha256:" + "c" * 64
HEX = "c" * 64


def _derive(events):
    from agora.ontology import states
    from datetime import datetime, timezone
    return states._derive(DIGEST, events, datetime(2026, 11, 27, 1, tzinfo=timezone.utc), timedelta(hours=24))


def _proposed(subject="p", **extra):
    bound = ["pack", "action", "1", "an-object", DIGEST]  # a proposal also names the objects it binds
    return _ev("ontology_action_proposed", subject, **{"policy_version": "v1", "resource_ids": bound, **extra})


def _decided(kind="approved", subject="a", **extra):
    return {**_ev("ontology_action_" + kind, subject, event_id="ontology-action-decision-" + HEX,
                  operation="ontology_action_decide", recorded_at="2026-11-27T00:00:00+00:00"), **extra}


def _ending(kind="admitted", subject="r", **extra):
    return {**_ev("ontology_action_" + kind, subject, event_id="ontology-action-final-" + HEX,
                  operation="ontology_action_admit" if kind == "admitted" else "ontology_action_withdraw"), **extra}


def _second(subject="b", **extra):
    return {**_ev("ontology_action_co_approved", subject, event_id="ontology-action-coapproval-" + HEX,
                  operation="ontology_action_decide"), **extra}


def _result(subject="r", kind="succeeded", **extra):
    return {**_ev("ontology_action_simulation_" + kind, subject, event_id="ontology-action-outcome-" + HEX,
                  operation="ontology_action_outcome", result_hash=RESULT), **extra}


@pytest.mark.parametrize("events,fragment", [
    ([], "not recorded"),
    ([_proposed(), _proposed("q")], "records disagree"),
    ([_proposed(), _proposed(policy_version="v2")], "records disagree"),
    ([_proposed(), _proposed(resource_ids=["other", "action", "1", DIGEST])], "records disagree"),
    ([_decided(), _proposed()], "decision is not well formed"),
    ([_proposed(), _decided(resource_ids=["x", DIGEST])], "decision is not well formed"),
    ([_proposed(), _decided(), _second(resource_ids=["x", DIGEST])], "second approval is not well formed"),
    ([_proposed(), _second(), _decided()], "second approval is not well formed"),
    ([_proposed(), _decided(), _ending(), _second()], "second approval is not well formed"),
    ([_proposed(), _ending(), _decided()], "ending is not well formed"),
    ([_proposed(), _decided(), _ending(resource_ids=["x", DIGEST])], "ending is not well formed"),
    ([_proposed(), _decided(), _result(), _ending()], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(operation="other")], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(resource_ids=["x", DIGEST])], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(result_hash=None)], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(result_hash="nonsense")], "outcome is not well formed"),
    ([{**_proposed(), "decision": "deny"}], "not recorded"),
    ([{**_proposed(), "subject_id": " "}], "not recorded"),
    ([_proposed(), _decided(), _decided()], "more than one decision"),
    ([_proposed(), _ending()], "no decision"),
    ([_proposed(), _result()], "no decision"),
    ([_proposed(), _decided(event_id="wrong")], "decision is not well formed"),
    ([_proposed(), _decided(operation="other")], "decision is not well formed"),
    ([_proposed(), {**_decided(), "decision": "deny"}], "decision is not well formed"),
    ([_proposed(), _decided(subject="p")], "decision is not well formed"),
    ([_proposed(), _decided(subject=" ")], "decision is not well formed"),
    ([_proposed(), _decided("rejected"), _ending()], "rejected proposal"),
    ([_proposed(), _decided("rejected"), _result()], "rejected proposal"),
    ([_proposed(), {k: v for k, v in _decided().items() if k != "recorded_at"}], "no readable time"),
    ([_proposed(), _decided(), _result()], "no admission"),
    ([_proposed(), _decided(), _ending("admitted"), _ending("admitted")], "more than one ending"),
    ([_proposed(), _decided(), _ending(event_id="wrong")], "ending is not well formed"),
    ([_proposed(), {**_decided(), }, {**_ending(), "decision": "deny"}], "ending is not well formed"),
    ([_proposed(), _decided(), _ending(subject=" ")], "ending is not well formed"),
    ([_proposed(), _decided(), _ending("withdrawn"), _result()], "no admission"),
    ([_proposed(), _decided(), _ending(subject="a")], "admission is not well formed"),
    ([_proposed(), _decided(), _ending(operation="other")], "admission is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(), _result()], "more than one outcome"),
    ([_proposed(), _decided(), _ending(), _result(event_id="wrong")], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), _result(subject="someone")], "outcome is not well formed"),
    ([_proposed(), _decided(), _ending(), {**_result(), "decision": "deny"}], "outcome is not well formed"),
])
def test_events_that_break_the_rules_are_reported_as_inconsistent(events, fragment):
    entry = _derive(events)
    assert entry["state"] == "inconsistent" and fragment in entry["reason"], entry


def test_well_formed_events_derive_every_state():
    assert _derive([_proposed()])["state"] == "proposed"
    assert _derive([_proposed(), _decided()])["state"] == "approved"
    from agora.ontology import states
    from datetime import datetime, timezone
    late = datetime(2026, 11, 28, 0, 0, tzinfo=timezone.utc)  # exactly the lifetime after the decision
    assert states._derive(DIGEST, [_proposed(), _decided()], late, timedelta(hours=24))["state"] == "expired"
    almost = datetime(2026, 11, 27, 23, 59, 59, tzinfo=timezone.utc)
    assert states._derive(DIGEST, [_proposed(), _decided()], almost, timedelta(hours=24))["state"] == "approved"
    assert _derive([_proposed(), _decided("rejected")])["state"] == "rejected"
    assert _derive([_proposed(), _decided(), _ending("withdrawn")])["state"] == "withdrawn"
    assert _derive([_proposed(), _decided(), _ending()])["state"] == "admitted"
    assert _derive([_proposed(), _decided(), _ending(), _result()])["state"] == "simulation_succeeded"
    assert _derive([_proposed(), _decided(), _ending(), _result(kind="failed")])["state"] == "simulation_failed"


def test_reads_are_authorised_at_the_proposals_classification_and_listing_at_the_highest(world):
    proposal = _propose(world)
    seen = []

    def watching(operation, resource):
        seen.append((operation, resource["source_sensitivity"], list(resource["resource_ids"])))
        return {**_allow(operation, resource), "subject_id": "reader-1", "policy_version": "v-reader-1"}

    _state(world, proposal, policy=watching)
    _list(world, policy=watching)
    assert [(o, s) for o, s, _ in seen] == [("ontology_read", proposal.document["sensitivity"]),
                                            ("ontology_read", "sensitive")]
    assert seen[0][2][-1] == proposal.digest and seen[1][2] == ["action_proposal_states"]


def _co(subject="c", **extra):
    return {**_ev("ontology_action_co_approved", subject, event_id="ontology-action-coapproval-" + HEX,
                  operation="ontology_action_decide"), **extra}


def test_an_admission_by_the_second_approver_is_inconsistent():
    entry = _derive([_proposed(), _decided(), _co(), _ending(subject="c")])
    assert entry["state"] == "inconsistent" and "admission is not well formed" in entry["reason"], entry


def test_a_second_approval_is_named_in_the_state():
    entry = _derive([_proposed(), _decided(), _co(), _ending()])
    assert entry["state"] == "admitted" and entry["co_approved_by"] == "c"
    assert _derive([_proposed(), _decided(), _co()])["co_approved_by"] == "c"


@pytest.mark.parametrize("events,fragment", [
    ([_proposed(), _co()], "without exactly one approval"),
    ([_proposed(), _decided("rejected"), _co()], "without exactly one approval"),
    ([_proposed(), _decided(), _co(), _co()], "without exactly one approval"),
    ([_proposed(), _decided(), _co(event_id="x")], "second approval is not well formed"),
    ([_proposed(), _decided(), _co(operation="x")], "second approval is not well formed"),
    ([_proposed(), _decided(), {**_co(), "decision": "deny"}], "second approval is not well formed"),
    ([_proposed(), _decided(), _co(subject=" ")], "second approval is not well formed"),
    ([_proposed(), _decided(), _co(subject="p")], "second approval is not well formed"),
    ([_proposed(), _decided(), _co(subject="a")], "second approval is not well formed"),
])
def test_a_bad_second_approval_is_inconsistent(events, fragment):
    entry = _derive(events)
    assert entry["state"] == "inconsistent" and fragment in entry["reason"], entry

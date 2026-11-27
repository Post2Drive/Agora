"""Sensitive action proposals need a second approver; admission needs a signed statement from each."""
from datetime import timedelta

import pytest

from agora import protection
from agora.ontology import (
    OntologyError, action_proposal_state, co_approve_action_proposal, list_action_proposals,
    run_admitted_simulation, verify_approved_action, withdraw_approval,
)
from agora.ontology import approvals, states
from agora.ontology.approvals import SignedApproval

from test_ontology_action_admission import RUNNER, _admit, _endings, _later  # noqa: F401
from test_ontology_action_approvals import APPROVER, _as, _decide, _events, catalog  # noqa: F401
import test_ontology_action_states as _state_events
from test_ontology_action_proposals import _allow, _deny, _propose, world  # noqa: F401
from test_ontology_action_signed_admission import _gate, _signed, _statement, clock  # noqa: F401

SECOND = _as("approver-2")
READER = _as("reader-1")


@pytest.fixture
def two(monkeypatch):
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", True)


def _co(w, proposal, policy=SECOND, reason="second look", document=None, digest=None, **kw):
    return co_approve_action_proposal(
        w.store, document if document is not None else proposal.document, digest or proposal.digest, reason,
        policy=policy, audit=w.audit, **kw)


def _verify(w, proposal):
    return verify_approved_action(w.store, proposal.document, proposal.digest, policy=RUNNER, audit=w.audit,
                                  purpose="account support", retention="90 days")


def _approved(w):
    proposal = _propose(w)
    _decide(w, proposal)
    return proposal


def test_the_second_approval_is_recorded_and_returned(two, world):
    proposal = _approved(world)
    assert _co(world, proposal) == {"digest": proposal.digest, "co_approved_by": "approver-2",
                                    "approved_by": "approver-1", "proposed_by": "ontology-test-operator"}
    (event,) = _events(world, "ontology_action_co_approved")
    assert event["event_id"] == "ontology-action-coapproval-" + proposal.digest.split(":")[1]
    assert event["operation"] == "ontology_action_decide" and event["subject_id"] == "approver-2"
    assert event["reason_hash"].startswith("sha256:") and event["resource_ids"][-1] == proposal.digest


def test_a_sensitive_proposal_is_not_admissible_with_one_approval(two, world):
    proposal = _approved(world)
    assert proposal.document["sensitivity"] == "sensitive"
    with pytest.raises(OntologyError, match="needs a second approver"):
        _verify(world, proposal)
    with pytest.raises(OntologyError, match="needs a second approver"):
        _admit(world, proposal)
    assert _endings(world) == []


def test_two_approvals_admit_and_verify_names_both(two, world):
    proposal = _approved(world)
    _co(world, proposal)
    assert _verify(world, proposal)["co_approved_by"] == "approver-2"
    result = _admit(world, proposal)
    assert result["approved_by"] == "approver-1" and result["co_approved_by"] == "approver-2"
    assert len(_endings(world)) == 1


def test_the_flag_off_keeps_one_approval_enough(world):
    proposal = _approved(world)
    assert "co_approved_by" not in _verify(world, proposal)
    _admit(world, proposal)


def test_the_second_approval_is_required_only_for_sensitive_proposals_and_only_when_on(monkeypatch):
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", True)
    assert approvals._two_person({"sensitivity": "sensitive"}) is True
    for level in ("public", "internal", "personal"):
        assert approvals._two_person({"sensitivity": level}) is False
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", False)
    assert approvals._two_person({"sensitivity": "sensitive"}) is False


def test_the_chain_refuses_a_second_second_approval_that_raced_the_check(two, world, monkeypatch):
    proposal = _approved(world)
    _co(world, proposal)
    monkeypatch.setattr(type(world.audit), "find_event", lambda self, event_id: None)
    with pytest.raises(OntologyError, match="already has a second approval"):
        _co(world, proposal, policy=_as("approver-3"))
    assert len(_events(world, "ontology_action_co_approved")) == 1


def test_a_withdrawal_that_lands_after_the_check_still_blocks_the_second_approval(two, world, monkeypatch):
    proposal = _approved(world)
    withdraw_approval(world.store, proposal.document, proposal.digest, "stop", policy=APPROVER, audit=world.audit)
    monkeypatch.setattr(approvals, "_not_ended", lambda writer, digest: None)  # the check ran before it
    with pytest.raises(OntologyError, match="already ended"):
        _co(world, proposal)
    assert _events(world, "ontology_action_co_approved") == []
    assert world.audit.verify()["valid"]


def test_an_approval_that_expires_after_the_check_cannot_be_seconded(two, world, monkeypatch):
    proposal = _approved(world)
    start, calls = approvals._now(), []

    def clock_that_jumps():
        calls.append(1)
        return start if len(calls) == 1 else start + timedelta(hours=25)

    monkeypatch.setattr(approvals, "_now", clock_that_jumps)
    with pytest.raises(OntologyError, match="expired"):
        _co(world, proposal)
    assert len(calls) == 2 and _events(world, "ontology_action_co_approved") == []


@pytest.mark.parametrize("policy,message", [
    (_as("ontology-test-operator"), "other than its proposer"),
    (APPROVER, "other than the first approver"),
])
def test_the_second_approver_is_a_third_person(two, world, policy, message):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match=message):
        _co(world, proposal, policy=policy)
    assert _events(world, "ontology_action_co_approved") == []


def test_a_second_approval_is_once(two, world):
    proposal = _approved(world)
    _co(world, proposal)
    with pytest.raises(OntologyError, match="already has a second approval"):
        _co(world, proposal, policy=_as("approver-3"))
    assert len(_events(world, "ontology_action_co_approved")) == 1


@pytest.mark.parametrize("state", ["proposed", "rejected"])
def test_there_is_nothing_to_second_without_an_approval(two, world, state):
    proposal = _propose(world)
    if state == "rejected":
        _decide(world, proposal, outcome="reject")
    with pytest.raises(OntologyError):
        _co(world, proposal)
    assert _events(world, "ontology_action_co_approved") == []


def test_a_withdrawn_used_or_expired_approval_cannot_be_seconded(two, world, monkeypatch):
    withdrawn = _approved(world)
    withdraw_approval(world.store, withdrawn.document, withdrawn.digest, "stop", policy=APPROVER, audit=world.audit)
    with pytest.raises(OntologyError, match="withdrawn"):
        _co(world, withdrawn)
    expiring = _propose(world, reason="two")
    _decide(world, expiring)
    _later(monkeypatch, hours=25)
    with pytest.raises(OntologyError, match="expired"):
        _co(world, expiring)
    with pytest.raises(OntologyError, match="expired"):
        _co(world, expiring, max_age_seconds=3600)


def test_the_second_approval_does_not_extend_the_first_ones_lifetime(two, world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, hours=23)
    _co(world, proposal)
    _later(monkeypatch, hours=25)
    with pytest.raises(OntologyError, match="expired"):
        _admit(world, proposal)


def test_either_approver_cannot_admit(two, world):
    proposal = _approved(world)
    _co(world, proposal)
    for who in (APPROVER, SECOND):
        with pytest.raises(OntologyError, match="other than its approver"):
            _admit(world, proposal, policy=who)
    assert _endings(world) == []


def test_a_second_approver_cannot_admit_even_when_a_second_approval_was_not_required(world, monkeypatch):
    # Same path as a proposal that is not sensitive: verification does not name the second approver.
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", False)
    proposal = _approved(world)
    _co(world, proposal)
    assert "co_approved_by" not in _verify(world, proposal)
    with pytest.raises(OntologyError, match="other than its second approver"):
        _admit(world, proposal, policy=SECOND)
    assert _endings(world) == []  # the approval is not spent
    assert _admit(world, proposal)["admitted_by"] == "runner-1"


def test_a_second_approval_that_lands_after_verification_still_blocks_its_author(world, monkeypatch):
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", False)
    proposal = _approved(world)
    real = approvals.verify_approved_action

    def verify_then_second(*args, **kwargs):
        live = real(*args, **kwargs)
        _co(world, proposal)
        return live

    monkeypatch.setattr(approvals, "verify_approved_action", verify_then_second)
    with pytest.raises(OntologyError, match="other than its second approver"):
        _admit(world, proposal, policy=SECOND)
    assert _endings(world) == [] and len(_events(world, "ontology_action_co_approved")) == 1
    assert world.audit.verify()["valid"]


def test_a_decision_needs_authority_before_anything_is_read(two, world):
    proposal = _approved(world)
    with pytest.raises(Exception):
        _co(world, proposal, policy=_deny)
    assert _events(world, "ontology_action_co_approved") == []


@pytest.mark.parametrize("kind", ["two", "missing", "wrong_id", "wrong_op", "deny", "self", "first"])
def test_a_malformed_second_approval_is_refused(two, world, kind):
    proposal = _approved(world)
    action = proposal.document["action_type"]
    event = {"event_id": "ontology-action-coapproval-" + proposal.digest.split(":")[1],
             "event_type": "ontology_action_co_approved", "operation": "ontology_action_decide",
             "decision": "allow", "subject_id": "approver-2", "policy_version": "v",
             "resource_ids": [proposal.document["pack_fingerprint"], action["action_type_id"], action["version"],
                              proposal.digest], "reason": "policy_allow"}
    change = {"wrong_id": {"event_id": "other"}, "wrong_op": {"operation": "ontology_action_admit"},
              "deny": {"decision": "deny"}, "self": {"subject_id": "ontology-test-operator"},
              "first": {"subject_id": "approver-1"}}.get(kind, {})
    if kind != "missing":
        world.audit.append({**event, **change})
    if kind == "two":
        world.audit.append({**event, "event_id": "second-copy"})
    message = "needs a second approver" if kind == "missing" else (
        "more than one" if kind == "two" else "second approval")
    with pytest.raises(OntologyError, match=message):
        _verify(world, proposal)


def test_admission_with_signatures_needs_one_statement_per_approver(two, world, clock):
    proposal = _approved(world)
    _co(world, proposal)
    gate = _gate(world, clock)
    first = SignedApproval(gate, _statement(world, proposal, clock))
    second = SignedApproval(gate, _statement(world, proposal, clock, approved_by="approver-2"))
    for bad in (first, [first], [second, first], [first, first], [first, second, second]):
        with pytest.raises(OntologyError):
            _admit(world, proposal, signed_approval=bad)
    assert _endings(world) == []
    result = _admit(world, proposal, signed_approval=[first, second])
    assert result["approval_statement_hash"].startswith("sha256:")
    (event,) = _endings(world)
    assert event["approval_statement_hash"] == result["approval_statement_hash"]


def test_the_recorded_hash_covers_both_statements(two, world, clock):
    import hashlib
    from agora.ontology import approvals as a
    proposal = _approved(world)
    _co(world, proposal)
    gate = _gate(world, clock)
    first = SignedApproval(gate, _statement(world, proposal, clock))
    second = SignedApproval(gate, _statement(world, proposal, clock, approved_by="approver-2"))
    hashes = [gate.check_approval(s.envelope, request={
        "project": world.store.project_id, "proposal_digest": proposal.digest,
        "proposed_by": "ontology-test-operator", "approved_by": who}).statement_hash
        for s, who in ((first, "approver-1"), (second, "approver-2"))]
    result = _admit(world, proposal, signed_approval=(first, second))
    expected = "sha256:" + hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()
    assert result["approval_statement_hash"] == expected and hashes[0] != hashes[1]


def test_one_statement_still_works_for_a_single_approval(world, clock):
    proposal = _approved(world)
    result = _admit(world, proposal, signed_approval=_signed(world, proposal, clock))
    assert result["approval_statement_hash"].startswith("sha256:")


@pytest.mark.protected_defaults
def test_the_flag_is_on_under_protected_defaults():
    assert protection.TWO_PERSON_SENSITIVE is True


def test_each_statements_expiry_is_checked_again_at_the_write(two, world, clock, monkeypatch):
    from datetime import timedelta
    from agora.security import approval_receipt as ap  # noqa: F401
    proposal = _approved(world)
    _co(world, proposal)
    gate = _gate(world, clock)
    first = SignedApproval(gate, _statement(world, proposal, clock))
    short = SignedApproval(gate, _statement(world, proposal, clock, approved_by="approver-2",
                                            expires_at=(clock.now + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")))
    real = approvals._check_signed_approval
    seen = []

    def after_both(signed, *args, **kwargs):
        checked = real(signed, *args, **kwargs)
        seen.append(1)
        if len(seen) == 2:
            clock.now += timedelta(seconds=60)  # past the short statement, inside the first
        return checked

    monkeypatch.setattr(approvals, "_check_signed_approval", after_both)
    with pytest.raises(OntologyError, match="expired before admission"):
        _admit(world, proposal, signed_approval=[first, short])
    assert _endings(world) == []


def test_the_state_view_names_the_second_approver(world):
    from agora.ontology import action_proposal_state, list_action_proposals
    proposal = _approved(world)
    _co(world, proposal)
    entry = action_proposal_state(world.store, proposal.document, proposal.digest, policy=_as("reader-1"),
                                  audit=world.audit)
    assert entry["state"] == "approved" and entry["co_approved_by"] == "approver-2"
    (listed,) = list_action_proposals(world.store, policy=_as("reader-1"), audit=world.audit)
    assert listed["co_approved_by"] == "approver-2"


@pytest.mark.parametrize("still_required", [True, False])
def test_no_outcome_for_an_admission_recorded_under_the_second_approver(two, world, monkeypatch, still_required):
    """admit_approved_action refuses this; an event that reached the chain another way is refused too."""
    proposal = _approved(world)
    _co(world, proposal)
    # A recorded second approver stays barred when the flag is turned off afterwards.
    monkeypatch.setattr(protection, "TWO_PERSON_SENSITIVE", still_required)
    action = proposal.document["action_type"]
    world.audit.append({
        "event_id": "ontology-action-final-" + proposal.digest.split(":")[1],
        "event_type": "ontology_action_admitted", "operation": "ontology_action_admit", "decision": "allow",
        "subject_id": "approver-2", "policy_version": "v", "reason": "policy_allow",
        "resource_ids": [proposal.document["pack_fingerprint"], action["action_type_id"], action["version"],
                         proposal.digest]})
    with pytest.raises(OntologyError, match="other than the second approver"):
        run_admitted_simulation(world.store, proposal.document, proposal.digest, policy=SECOND,
                                audit=world.audit, purpose="account support", retention="90 days")
    for kind in ("ontology_action_simulation_succeeded", "ontology_action_simulation_failed"):
        assert _events(world, kind) == []


def test_the_second_statement_may_not_outlive_the_approval(two, world, clock, monkeypatch):
    from datetime import datetime, timedelta
    proposal = _approved(world)
    _co(world, proposal)
    gate = _gate(world, clock)
    statements = [SignedApproval(gate, _statement(world, proposal, clock)),
                  SignedApproval(gate, _statement(world, proposal, clock, approved_by="approver-2"))]
    real = approvals._check_signed_approval

    def second_outlives(signed, fields, digest, approver, store):
        checked = real(signed, fields, digest, approver, store)
        if approver != "approver-2":
            return checked
        from dataclasses import replace
        return replace(checked, expires_at=checked.expires_at + timedelta(days=2))

    monkeypatch.setattr(approvals, "_check_signed_approval", second_outlives)
    with pytest.raises(OntologyError, match="outlives the approval"):
        _admit(world, proposal, signed_approval=statements)
    assert _endings(world) == []


def _views(w, proposal):
    one = action_proposal_state(w.store, proposal.document, proposal.digest, policy=READER, audit=w.audit)
    (listed,) = list_action_proposals(w.store, policy=READER, audit=w.audit)
    return one, listed


def test_both_state_views_wait_for_the_second_approval(two, world):
    proposal = _approved(world)
    for entry in _views(world, proposal):
        assert entry["state"] == "awaiting_second_approval" and entry["decided_by"] == "approver-1"
        assert entry["expires_at"] and "second_approval_requirement" not in entry
    assert list_action_proposals(world.store, policy=READER, audit=world.audit, state="approved") == []
    _co(world, proposal)
    for entry in _views(world, proposal):
        assert entry["state"] == "approved" and entry["co_approved_by"] == "approver-2"


def test_with_the_flag_off_one_approval_shows_as_approved(world):
    proposal = _approved(world)
    assert [e["state"] for e in _views(world, proposal)] == ["approved", "approved"]


def test_the_proposal_record_holds_the_classification_unredacted(two, world):
    _propose(world)
    (event,) = _events(world, "ontology_action_proposed")
    assert event["proposal_sensitivity"] == "sensitive"


def test_an_expired_first_approval_is_expired_not_waiting(two, world, monkeypatch):
    proposal = _approved(world)
    _later(monkeypatch, hours=25)
    assert [e["state"] for e in _views(world, proposal)] == ["expired", "expired"]


def _derived(*records, document=None):
    """Derive from one approval and one proposal record per entry of ``records`` (extra record fields)."""
    from datetime import datetime, timezone
    events = [*(_state_events._proposed(**extra) for extra in records), _state_events._decided()]
    return states._derive(_state_events.DIGEST, events, datetime(2026, 11, 27, 1, tzinfo=timezone.utc),
                          timedelta(hours=24), document)


def test_a_record_without_a_classification_is_marked_unknown(two):
    entry = _derived({})
    assert entry["state"] == "approved" and entry["second_approval_requirement"] == "unknown"
    # An older record next to a newer one is not a disagreement; the classification that is there counts.
    assert _derived({}, {"proposal_sensitivity": "sensitive"})["state"] == "awaiting_second_approval"
    assert _derived({}, document="sensitive")["state"] == "awaiting_second_approval"
    assert _derived({"proposal_sensitivity": "internal"}) == {
        "digest": _state_events.DIGEST, "proposed_by": "p", "decided_by": "a", "state": "approved",
        "expires_at": "2026-11-28T00:00:00+00:00"}


@pytest.mark.parametrize("records,document", [
    (({"proposal_sensitivity": "sensitive"}, {"proposal_sensitivity": "internal"}), None),
    (({"proposal_sensitivity": "internal"},), "sensitive"),
    (({"proposal_sensitivity": "[REDACTED]"},), None),
    (({"proposal_sensitivity": ["sensitive"]},), None),
    (({"proposal_sensitivity": None},), None),
])
def test_a_disagreeing_or_unknown_classification_is_inconsistent(two, records, document):
    entry = _derived(*records, document=document)
    assert entry["state"] == "inconsistent" and "classification" in entry["reason"], entry


def test_for_an_older_record_one_view_uses_the_document_and_the_list_says_unknown(two, world, monkeypatch):
    proposal = _approved(world)
    real = states._read

    def older(writer, digest):
        return {d: [{k: v for k, v in e.items() if k != "proposal_sensitivity"} for e in events]
                for d, events in real(writer, digest).items()}

    monkeypatch.setattr(states, "_read", older)
    one, listed = _views(world, proposal)
    assert one["state"] == "awaiting_second_approval"
    assert listed["state"] == "approved" and listed["second_approval_requirement"] == "unknown"

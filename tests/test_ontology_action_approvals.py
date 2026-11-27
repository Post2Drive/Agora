"""An approver other than the proposer decides a proposal once, in the anchored chain; nothing executes."""
import hashlib
import json
import sqlite3

import pytest

from agora.ontology import OntologyError, decide_action_proposal, verify_approved_action
from agora.ontology.actions import proposal_digest
from agora.policy import decide

from test_ontology_action_proposals import _allow, _deny, _propose, world  # noqa: F401
from test_ontology_store import _binding, _pack  # noqa: F401
from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyObjectStore

_DECISION_PREFIX = "ontology-action-decision-"


@pytest.fixture
def catalog(tmp_path):
    """The proposals fixture's catalog, but with an anchored audit chain kept outside the project."""
    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    (tmp_path / "ops").mkdir()
    chain = AuditChainStore(tmp_path / "ops" / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "ops" / "anchor.jsonl", "ontology-approval-test")
    bootstrap_anchor(chain, anchors, performed_by="test-operator")
    audit = AnchoredAuditChain(chain, anchors)
    store = OntologyObjectStore(project)
    pack_fingerprint = store.register_pack(_pack(), policy=_allow, audit=audit)
    binding_fingerprint = store.register_binding(pack_fingerprint, _binding(), policy=_allow, audit=audit)
    try:
        yield project, store, audit, pack_fingerprint, binding_fingerprint
    finally:
        chain.close()


def _as(subject):
    def policy(operation, resource):
        return {**_allow(operation, resource), "subject_id": subject, "policy_version": "v-" + subject}
    return policy


APPROVER, READER = _as("approver-1"), _as("reader-1")


def _decide(w, proposal, outcome="approve", reason="checked with the customer", policy=APPROVER,
            document=None, digest=None):
    return decide_action_proposal(w.store, document if document is not None else proposal.document,
                                  digest or proposal.digest, outcome, reason, policy=policy, audit=w.audit)


def _verify(w, proposal, policy=READER, document=None, digest=None):
    return verify_approved_action(w.store, document if document is not None else proposal.document,
                                  digest or proposal.digest, policy=policy, audit=w.audit,
                                  purpose="account support", retention="90 days")


def _events(w, event_type):
    rows = w.audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq").fetchall()
    return [e for e in (json.loads(r[0]) for r in rows) if e.get("event_type") == event_type]


def _decided(w):
    return _events(w, "ontology_action_approved") + _events(w, "ontology_action_rejected")


def test_an_approver_decides_once_and_the_decision_is_in_the_chain(world):
    proposal = _propose(world)
    result = _decide(world, proposal)
    assert result == {"digest": proposal.digest, "outcome": "approved", "decided_by": "approver-1",
                      "proposed_by": "ontology-test-operator"}
    (event,) = _events(world, "ontology_action_approved")
    assert event["event_id"] == _DECISION_PREFIX + proposal.digest.split(":")[1]
    assert event["subject_id"] == "approver-1" and event["operation"] == "ontology_action_decide"
    assert event["reason_hash"] == "sha256:" + hashlib.sha256(b"checked with the customer").hexdigest()
    assert "checked with the customer" not in json.dumps(event)
    assert event["resource_ids"][-1] == proposal.digest and event["policy_version"] == "v-approver-1"
    assert _events(world, "ontology_action_executed") == []


def test_an_approved_proposal_verifies_for_a_reader(world):
    proposal = _propose(world)
    _decide(world, proposal)
    result = _verify(world, proposal)
    assert result.pop("expires_at")
    assert result == {
        "digest": proposal.digest, "approved_by": "approver-1", "proposed_by": "ontology-test-operator"}


def test_the_proposer_cannot_decide_their_own_proposal(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError, match="someone other than its proposer"):
        _decide(world, proposal, policy=_allow)
    assert _decided(world) == []


def test_a_proposal_is_decided_once(world):
    proposal = _propose(world)
    _decide(world, proposal)
    for outcome in ("approve", "reject"):
        with pytest.raises(OntologyError, match="already has a decision"):
            _decide(world, proposal, outcome=outcome, policy=_as("approver-2"))
    assert len(_decided(world)) == 1
    assert _verify(world, proposal)["approved_by"] == "approver-1"


def test_a_decision_that_races_the_check_is_still_refused(world, monkeypatch):
    proposal = _propose(world)
    _decide(world, proposal)
    monkeypatch.setattr(type(world.audit), "find_event", lambda self, event_id: None)
    with pytest.raises(OntologyError, match="already has a decision"):
        _decide(world, proposal, policy=_as("approver-2"))


def test_a_rejected_proposal_does_not_verify(world):
    proposal = _propose(world)
    assert _decide(world, proposal, outcome="reject")["outcome"] == "rejected"
    with pytest.raises(OntologyError, match="was not approved"):
        _verify(world, proposal)


def test_an_undecided_proposal_does_not_verify(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError, match="has not been decided"):
        _verify(world, proposal)


def test_the_decision_is_made_before_anything_is_read(world):
    proposal = _propose(world)
    seen = []

    def deny(operation, resource):
        seen.append(operation)
        return _deny(operation, resource)

    with pytest.raises(OntologyError, match="policy denied"):
        _decide(world, proposal, policy=deny)
    assert seen == ["ontology_action_decide"]
    never = "sha256:" + "0" * 64
    document = {**proposal.document}
    # A denied caller gets the same refusal whether or not the digest was ever proposed.
    with pytest.raises(OntologyError, match="policy denied"):
        _decide(world, proposal, policy=_deny, document=document, digest=proposal_digest(document))
    other = {**proposal.document, "reason": "another reason"}
    with pytest.raises(OntologyError, match="policy denied"):
        _decide(world, proposal, policy=_deny, document=other, digest=proposal_digest(other))
    assert never  # shape only


def test_an_unknown_identity_is_refused(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError, match="principal-bound identity"):
        _decide(world, proposal, policy=lambda o, r: {**_allow(o, r), "subject_id": "unknown"})


def test_only_approvers_decide_under_the_central_roles():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_action_decide", resource)["decision"] == "allow"}
    assert allowed == {"approver"}


def test_a_proposal_the_chain_never_recorded_cannot_be_decided(world):
    proposal = _propose(world)
    forged = {**proposal.document, "reason": "invented"}
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _decide(world, proposal, document=forged, digest=proposal_digest(forged))
    # the authorization event of that attempt names the digest too, and does not count as a proposal
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _decide(world, proposal, document=forged, digest=proposal_digest(forged))
    assert _decided(world) == []


def test_a_proposal_cannot_be_credited_to_someone_else(world):
    proposal = _propose(world)
    forged = {**proposal.document, "proposed_by": "approver-1"}
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _decide(world, proposal, document=forged, digest=proposal_digest(forged), policy=_as("approver-2"))
    forged = {**proposal.document, "policy_version": "v-other"}
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _decide(world, proposal, document=forged, digest=proposal_digest(forged))


@pytest.mark.parametrize("change", [
    {"outcome": "maybe"}, {"outcome": ""}, {"outcome": None}, {"reason": ""}, {"reason": " padded "},
    {"reason": None}, {"digest": "sha256:" + "0" * 64}, {"digest": "SHA256:" + "A" * 64}, {"digest": "x"},
    {"digest": None}, {"document": "text"}, {"document": None}, {"document": {"format": "other"}},
])
def test_badly_formed_requests_are_refused_and_decide_nothing(world, change):
    proposal = _propose(world)
    request = {"outcome": "approve", "reason": "ok", "digest": proposal.digest, "document": proposal.document}
    request.update(change)
    with pytest.raises(OntologyError):
        decide_action_proposal(world.store, request["document"], request["digest"], request["outcome"],
                               request["reason"], policy=APPROVER, audit=world.audit)
    assert _decided(world) == []


@pytest.mark.parametrize("path,value,message", [
    (("format",), "other/v1", "not an action proposal"), (("project_id",), "someone-else", "not an action proposal"),
    (("sensitivity",), "secret", "unknown classification"), (("proposed_by",), "", "missing required content"),
    (("policy_version",), 5, "missing required content"), (("pack_fingerprint",), None, "missing required content"),
])
def test_a_document_of_the_wrong_kind_is_refused(world, path, value, message):
    proposal = _propose(world)
    document = {**proposal.document, path[0]: value}
    with pytest.raises(OntologyError, match=message):
        _decide(world, proposal, document=document, digest=proposal_digest(document))
    document = {k: v for k, v in proposal.document.items() if k != "action_type"}
    with pytest.raises(OntologyError, match="missing required content"):
        _decide(world, proposal, document=document, digest=proposal_digest(document))


def test_a_changed_document_does_not_match_its_digest(world):
    proposal = _propose(world)
    _decide(world, proposal)
    changed = {**proposal.document, "reason": "other"}
    with pytest.raises(OntologyError, match="expected digest"):
        _verify(world, proposal, document=changed)
    with pytest.raises(OntologyError, match="expected digest"):
        _decide(world, proposal, document=changed)


def test_writers_that_are_not_anchored_are_refused(world):
    proposal = _propose(world)
    with pytest.raises(OntologyError, match="anchored audit writer"):
        decide_action_proposal(world.store, proposal.document, proposal.digest, "approve", "ok",
                               policy=APPROVER, audit=None)
    with pytest.raises(OntologyError, match="anchored audit writer"):
        verify_approved_action(world.store, proposal.document, proposal.digest, policy=READER, audit=None)


def test_an_approval_goes_stale_when_a_source_row_changes(world):
    proposal = _propose(world)
    _decide(world, proposal)
    conn = sqlite3.connect(world.project / "data" / "tabular.sqlite3")
    try:
        for name in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]:
            conn.execute(f'DROP TRIGGER "{name}"')
        for column in [r[1] for r in conn.execute("PRAGMA table_info(import_rows)")]:
            conn.execute(f"UPDATE import_rows SET {column}=replace({column}, 'two@', 'xyz@') "
                         f"WHERE instr({column}, 'two@')>0")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(OntologyError, match="no longer matches|does not match its row ID"):
        _verify(world, proposal)


def test_verification_needs_read_authority(world):
    proposal = _propose(world)
    _decide(world, proposal)
    with pytest.raises(OntologyError, match="policy denied"):
        _verify(world, proposal, policy=_deny)


def _append(world, proposal, **changes):
    event = {"event_id": _DECISION_PREFIX + proposal.digest.split(":")[1],
             "event_type": "ontology_action_approved", "operation": "ontology_action_decide",
             "decision": "allow", "subject_id": "approver-1", "policy_version": "v-approver-1",
             "resource_ids": ["p", "a", "1", proposal.digest], "reason_hash": "sha256:" + "0" * 64,
             "reason": "policy_allow"}
    event.update(changes)
    world.audit.append(event)


@pytest.mark.parametrize("changes,message", [
    ({"subject_id": "ontology-test-operator"}, "someone other than the proposer"),
    ({"subject_id": ""}, "someone other than the proposer"),
    ({"subject_id": None}, "someone other than the proposer"),
    ({"operation": "ontology_read"}, "not well formed"),
    ({"decision": "deny"}, "not well formed"),
    ({"event_type": "ontology_action_rejected"}, "was not approved"),
    ({"event_type": "ontology_action_decided"}, "has not been decided"),
    ({"event_type": "ontology_action_approved "}, "has not been decided"),
])
def test_a_decision_event_that_decide_would_not_have_written_is_not_trusted(world, changes, message):
    proposal = _propose(world)
    _append(world, proposal, **changes)
    with pytest.raises(OntologyError, match=message):
        _verify(world, proposal)


def test_a_decision_under_the_wrong_event_id_is_not_trusted(world):
    proposal = _propose(world)
    _append(world, proposal, event_id="ontology-action-decision-forged")
    with pytest.raises(OntologyError, match="not been decided|not well formed"):
        _verify(world, proposal)


def test_two_decisions_for_one_digest_are_refused(world):
    proposal = _propose(world)
    _decide(world, proposal)
    _append(world, proposal, event_id="ontology-action-decision-second")
    with pytest.raises(OntologyError, match="more than one decision"):
        _verify(world, proposal)


def test_a_decision_without_a_recorded_proposal_does_not_verify(world):
    proposal = _propose(world)
    other = {**proposal.document, "reason": "never proposed"}
    digest = proposal_digest(other)
    event = {"event_id": _DECISION_PREFIX + digest.split(":")[1], "event_type": "ontology_action_approved",
             "operation": "ontology_action_decide", "decision": "allow", "subject_id": "approver-1",
             "policy_version": "v", "resource_ids": ["p", digest], "reason": "policy_allow"}
    world.audit.append(event)
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _verify(world, proposal, document=other, digest=digest)


def test_the_same_proposal_made_twice_is_decided_once(world):
    first = _propose(world)
    again = _propose(world)
    assert first.digest == again.digest
    _decide(world, first)
    with pytest.raises(OntologyError, match="already has a decision"):
        _decide(world, again, policy=_as("approver-2"))
    assert _verify(world, again)["approved_by"] == "approver-1"


def test_a_tampered_chain_is_not_read(world):
    proposal = _propose(world)
    _decide(world, proposal)
    db = world.audit.chain.db
    for name in [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]:
        db.execute(f'DROP TRIGGER "{name}"')   # an attacker with file access is not stopped by triggers
    db.execute(
        "UPDATE audit_events SET event_json=replace(event_json, 'approver-1', 'approver-9') "
        "WHERE instr(event_json, 'ontology_action_approved') > 0")
    world.audit.chain.db.commit()
    with pytest.raises(PermissionError, match="not cleanly anchored"):   # the first authorization append refuses
        _verify(world, proposal)
    from agora.ontology import approvals
    with pytest.raises(OntologyError, match="not cleanly anchored"):     # and the chain read does not trust it either
        approvals._events(world.audit, proposal.digest, "ontology_action_approved")
    with pytest.raises(PermissionError, match="not cleanly anchored"):   # the authorization event cannot be appended
        _decide(world, proposal, policy=_as("approver-2"))


def test_the_decision_is_taken_at_the_proposals_classification(world):
    proposal = _propose(world)
    assert proposal.document["sensitivity"] == "sensitive"
    seen = []

    def policy(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource) if resource["source_sensitivity"] == "sensitive" else APPROVER(operation, resource)

    with pytest.raises(OntologyError, match="policy denied"):
        _decide(world, proposal, policy=policy)
    assert seen == [("ontology_action_decide", "sensitive")]
    assert _decided(world) == []


def _propose_event(w, digest, **changes):
    event = {"event_id": "ontology-forged-" + digest[-8:] + str(len(changes)), "event_type": "ontology_action_proposed",
             "operation": "ontology_action_propose", "decision": "allow", "subject_id": "mallory",
             "policy_version": "ontology-test-v1", "resource_ids": ["p", digest], "reason": "proposal_recorded_not_executed"}
    event.update(changes)
    w.audit.append(event)


@pytest.mark.parametrize("changes", [
    {"subject_id": "mallory"}, {"subject_id": "ontology-test-operator", "policy_version": "someone-elses-policy"}, {"decision": "deny", "subject_id": "ontology-test-operator"},
])
def test_a_proposal_event_must_come_from_the_person_the_document_names(world, changes):
    proposal = _propose(world)
    forged = {**proposal.document, "reason": "invented"}
    digest = proposal_digest(forged)
    _propose_event(world, digest, **changes)
    with pytest.raises(OntologyError, match="was not recorded in the audit chain"):
        _decide(world, proposal, document=forged, digest=digest)
    assert _decided(world) == []


def test_only_events_that_end_with_the_digest_count(world):
    proposal = _propose(world)
    _decide(world, proposal)
    for kind in ("ontology_action_rejected", "ontology_action_approved"):
        world.audit.append({"event_id": "ontology-extra-" + kind, "event_type": kind,
                            "operation": "ontology_action_decide", "decision": "allow",
                            "subject_id": "approver-2", "policy_version": "v",
                            "resource_ids": [proposal.digest, "something-else"], "reason": "policy_allow"})
    assert _verify(world, proposal)["approved_by"] == "approver-1"

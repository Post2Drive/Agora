"""A dry-run simulation of an admitted action: the result it records and how that result is checked."""
import sqlite3

import pytest

from agora.ontology import (
    OntologyError, record_simulation_outcome, run_admitted_simulation, verify_simulation_result,
)
from agora.ontology import simulation
from agora.ontology.actions import proposal_digest

from test_ontology_action_admission import RUNNER, _admit, _approved
from test_ontology_action_approvals import APPROVER, _as, _decide, _events, catalog, world  # noqa: F401
from test_ontology_action_proposals import _allow, _deny, _propose

READER = _as("reader-1")


def _run(w, proposal, policy=RUNNER, document=None, digest=None):
    return run_admitted_simulation(w.store, document if document is not None else proposal.document,
                                   digest or proposal.digest, policy=policy, audit=w.audit,
                                   purpose="account support", retention="90 days")


def _verify(w, result, policy=READER):
    return verify_simulation_result(w.store, result, policy=policy, audit=w.audit)


def _admitted(w):
    proposal = _approved(w)
    _admit(w, proposal)
    return proposal


def _outcomes(w):
    return (_events(w, "ontology_action_simulation_succeeded")
            + _events(w, "ontology_action_simulation_failed"))


def _break_source(w):
    conn = sqlite3.connect(w.project / "data" / "tabular.sqlite3")
    try:
        for name in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]:
            conn.execute(f'DROP TRIGGER "{name}"')
        for column in [r[1] for r in conn.execute("PRAGMA table_info(import_rows)")]:
            conn.execute(f"UPDATE import_rows SET {column}=replace({column}, 'two@', 'xyz@') "
                         f"WHERE instr({column}, 'two@')>0")
        conn.commit()
    finally:
        conn.close()


def test_a_run_records_the_digest_of_the_result_it_returns(world):
    proposal = _admitted(world)
    out = _run(world, proposal)
    d = proposal.document
    assert out["status"] == "succeeded" and out["recorded_by"] == "runner-1"
    result = out["result"]
    assert out["result_digest"] == proposal_digest(result)
    assert result["format"] == simulation.RESULT_FORMAT and result["proposal_digest"] == proposal.digest
    assert result["pack_fingerprint"] == d["pack_fingerprint"] and result["state_changed"] is False
    assert result["action_type"] == {"action_type_id": d["action_type"]["action_type_id"],
                                     "version": d["action_type"]["version"],
                                     "fingerprint": d["action_type"]["fingerprint"]}
    assert result["actor_values_sha256"] == d["actor"]["values_sha256"]
    assert result["target_values_sha256"] == d["target"]["values_sha256"]
    assert result["parameters_sha256"] == proposal_digest(d["parameters"])
    assert result["simulated_effects"] == [{"effect": e, "simulated": True} for e in d["declared_effects"]]
    assert result["preconditions_met"] == []
    (event,) = _outcomes(world)
    assert event["event_type"] == "ontology_action_simulation_succeeded" and event["result_hash"] == out["result_digest"]


def test_a_result_is_deterministic_apart_from_who_runs(world):
    proposal = _admitted(world)
    first = _run(world, proposal)["result"]
    assert first == simulation._result_document(proposal.document, proposal.digest)


def test_a_proposal_that_no_longer_matches_records_a_failure_report(world):
    proposal = _admitted(world)
    _break_source(world)
    out = _run(world, proposal)
    assert out["status"] == "failed"
    assert out["result"] == {"format": simulation.FAILURE_FORMAT, "proposal_digest": proposal.digest,
                             "reason": "proposal_no_longer_valid", "state_changed": False}
    (event,) = _outcomes(world)
    assert event["event_type"] == "ontology_action_simulation_failed"
    assert event["result_hash"] == proposal_digest(out["result"])
    assert "xyz" not in str(out) and "two@" not in str(out)


def test_a_second_run_is_refused_and_the_first_outcome_stands(world):
    proposal = _admitted(world)
    first = _run(world, proposal)
    with pytest.raises(OntologyError, match="already has an outcome"):
        _run(world, proposal)
    assert len(_outcomes(world)) == 1 and _events(world, "ontology_action_simulation_succeeded")[0]["result_hash"] == first["result_digest"]


@pytest.mark.parametrize("by", [_as("runner-2"), APPROVER])
def test_only_the_admitter_can_run_it(world, by):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="only the identity that admitted"):
        _run(world, proposal, policy=by)
    assert _outcomes(world) == []


@pytest.mark.parametrize("state", ["proposed", "approved"])
def test_nothing_runs_before_admission(world, state):
    proposal = _propose(world)
    if state == "approved":
        _decide(world, proposal)
    with pytest.raises(OntologyError):
        _run(world, proposal)
    assert _outcomes(world) == []


def test_a_policy_refusal_is_raised_and_records_nothing(world):
    proposal = _admitted(world)
    with pytest.raises((PermissionError, OntologyError)):
        _run(world, proposal, policy=_deny)
    assert _outcomes(world) == []


def test_a_runner_who_cannot_read_gets_an_error_not_a_failed_outcome(world):
    proposal = _admitted(world)

    def record_only(operation, resource):
        decision = {**RUNNER(operation, resource)}
        if operation != "ontology_action_outcome":
            decision["decision"] = "deny"
        return decision

    with pytest.raises(OntologyError, match="policy denied"):
        _run(world, proposal, policy=record_only)
    assert _outcomes(world) == []


def test_a_wrong_digest_or_document_is_refused_before_anything_is_read(world):
    proposal = _admitted(world)
    with pytest.raises(OntologyError):
        _run(world, proposal, digest="sha256:" + "0" * 64)
    with pytest.raises(OntologyError):
        _run(world, proposal, document="nope")
    with pytest.raises(OntologyError):
        run_admitted_simulation(world.store, proposal.document, proposal.digest, policy=RUNNER, audit=None)
    assert _outcomes(world) == []


def test_a_recorded_result_verifies(world):
    proposal = _admitted(world)
    out = _run(world, proposal)
    assert _verify(world, out["result"]) == {
        "digest": proposal.digest, "status": "succeeded", "result_digest": out["result_digest"],
        "recorded_by": "runner-1"}


def test_a_recorded_failure_report_verifies_as_failed(world):
    proposal = _admitted(world)
    _break_source(world)
    out = _run(world, proposal)
    assert _verify(world, out["result"])["status"] == "failed"


def test_an_altered_result_does_not_verify(world):
    proposal = _admitted(world)
    result = _run(world, proposal)["result"]
    for change in ({"state_changed": True}, {"simulated_effects": []}, {"parameters_sha256": "sha256:" + "1" * 64}):
        with pytest.raises(OntologyError, match="not the recorded result"):
            _verify(world, {**result, **change})


def test_a_result_for_a_proposal_without_an_outcome_does_not_verify(world):
    proposal = _admitted(world)
    result = simulation._result_document(proposal.document, proposal.digest)
    with pytest.raises(OntologyError, match="no single recorded outcome"):
        _verify(world, result)


def test_a_result_cannot_stand_in_for_a_failure_or_the_reverse(world):
    proposal = _admitted(world)
    # a caller-supplied outcome recorded as failed, with the digest of a success-format document
    result = simulation._result_document(proposal.document, proposal.digest)
    record_simulation_outcome(world.store, proposal.document, proposal.digest, "failed",
                              proposal_digest(result), policy=RUNNER, audit=world.audit)
    with pytest.raises(OntologyError, match="does not match the recorded status"):
        _verify(world, result)


@pytest.mark.parametrize("bad", [None, "x", [], {}, {"format": "other"}, {"format": simulation.RESULT_FORMAT},
                                 {"format": simulation.RESULT_FORMAT, "proposal_digest": "sha256:short"},
                                 {"format": simulation.RESULT_FORMAT, "proposal_digest": 5}])
def test_documents_that_are_not_results_are_refused(world, bad):
    with pytest.raises(OntologyError):
        _verify(world, bad)


def test_non_json_content_is_refused(world):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="canonical JSON"):
        _verify(world, {"format": simulation.RESULT_FORMAT, "proposal_digest": proposal.digest, "x": object()})


def test_verifying_needs_read_authority_and_an_anchored_chain(world):
    proposal = _admitted(world)
    out = _run(world, proposal)
    with pytest.raises((PermissionError, OntologyError)):
        _verify(world, out["result"], policy=_deny)
    with pytest.raises(OntologyError):
        verify_simulation_result(world.store, out["result"], policy=READER, audit=None)


def test_a_malformed_recorded_outcome_is_refused(world):
    proposal = _admitted(world)
    result = simulation._result_document(proposal.document, proposal.digest)
    action = proposal.document["action_type"]
    world.audit.append({
        "event_id": "ontology-action-outcome-other", "event_type": "ontology_action_simulation_succeeded",
        "operation": "ontology_action_outcome", "decision": "allow", "subject_id": "runner-1",
        "policy_version": "v", "resource_ids": [proposal.document["pack_fingerprint"], action["action_type_id"],
                                                action["version"], proposal.digest],
        "result_hash": proposal_digest(result), "reason": "policy_allow"})
    with pytest.raises(OntologyError, match="not well formed"):
        _verify(world, result)


def _forged_outcome(w, proposal, result, **changes):
    action = proposal.document["action_type"]
    event = {"event_id": "ontology-action-outcome-" + proposal.digest.split(":")[1],
             "event_type": "ontology_action_simulation_succeeded", "operation": "ontology_action_outcome",
             "decision": "allow", "subject_id": "runner-1", "policy_version": "v",
             "resource_ids": [proposal.document["pack_fingerprint"], action["action_type_id"], action["version"],
                              proposal.digest],
             "result_hash": proposal_digest(result), "reason": "policy_allow"}
    event.update(changes)
    w.audit.append(event)


def test_a_forged_outcome_from_the_admitter_after_a_real_admission_verifies(world):
    proposal = _admitted(world)
    result = simulation._result_document(proposal.document, proposal.digest)
    _forged_outcome(world, proposal, result)
    assert _verify(world, result)["recorded_by"] == "runner-1"  # the chain cannot show who wrote an event


@pytest.mark.parametrize("changes", [{"operation": "ontology_action_decide"}, {"decision": "deny"},
                                     {"subject_id": " "}, {"subject_id": None}])
def test_an_outcome_with_the_right_id_but_a_wrong_field_is_refused(world, changes):
    proposal = _admitted(world)
    result = simulation._result_document(proposal.document, proposal.digest)
    _forged_outcome(world, proposal, result, **changes)
    with pytest.raises(OntologyError, match="not well formed"):
        _verify(world, result)


def test_two_outcome_events_for_one_proposal_are_refused(world):
    proposal = _admitted(world)
    result = simulation._result_document(proposal.document, proposal.digest)
    _forged_outcome(world, proposal, result)
    _forged_outcome(world, proposal, result, event_id="ontology-action-outcome-second")
    with pytest.raises(OntologyError, match="no single recorded outcome"):
        _verify(world, result)


def test_a_supplied_digest_is_refused_under_the_protected_defaults_but_the_runner_still_records(world, monkeypatch):
    from agora import protection
    proposal = _admitted(world)
    monkeypatch.setattr(protection, "RUNNER_ONLY_OUTCOMES", True)
    with pytest.raises(OntologyError, match="run_admitted_simulation"):
        record_simulation_outcome(world.store, proposal.document, proposal.digest, "succeeded",
                                  "sha256:" + "a" * 64, policy=RUNNER, audit=world.audit)
    assert _outcomes(world) == []
    out = _run(world, proposal)
    assert out["status"] == "succeeded" and len(_outcomes(world)) == 1
    assert _verify(world, out["result"])["result_digest"] == out["result_digest"]


@pytest.mark.protected_defaults
def test_the_flag_is_on_under_protected_defaults():
    from agora import protection
    assert protection.RUNNER_ONLY_OUTCOMES is True


def test_the_shipped_default_is_runner_only():
    import ast
    from pathlib import Path
    from agora import protection
    tree = ast.parse(Path(protection.__file__).read_text(encoding="utf-8"))
    values = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)}
    assert values["RUNNER_ONLY_OUTCOMES"] is True and values["SIGNED_APPROVAL_REQUIRED"] is True


# --- the history behind a recorded outcome ----------------------------------------------------------

def _forged_chain(w, steps):
    """A proposal that was only proposed, plus hand-written chain events for the later steps."""
    proposal = _propose(w)
    result = simulation._result_document(proposal.document, proposal.digest)
    action = proposal.document["action_type"]
    resources = [proposal.document["pack_fingerprint"], action["action_type_id"], action["version"],
                 proposal.digest]
    suffix = proposal.digest.split(":")[1]
    shapes = {
        "approve": ("ontology-action-decision-", "ontology_action_approved", "ontology_action_decide", "approver-1"),
        "reject": ("ontology-action-decision-", "ontology_action_rejected", "ontology_action_decide", "approver-1"),
        "co": ("ontology-action-coapproval-", "ontology_action_co_approved", "ontology_action_decide", "approver-2"),
        "admit": ("ontology-action-final-", "ontology_action_admitted", "ontology_action_admit", "runner-1"),
        "withdraw": ("ontology-action-final-", "ontology_action_withdrawn", "ontology_action_decide", "approver-1"),
        "outcome": ("ontology-action-outcome-", "ontology_action_simulation_succeeded", "ontology_action_outcome",
                    "runner-1"),
    }
    for name, changes in steps:
        prefix, kind, operation, who = shapes[name]
        event = {"event_id": prefix + suffix, "event_type": kind, "operation": operation, "decision": "allow",
                 "subject_id": who, "policy_version": "v", "resource_ids": resources, "reason": "policy_allow"}
        if name == "outcome":
            event["result_hash"] = proposal_digest(result)
        event.update(changes)
        w.audit.append(event)
    return result


def _good(**changes):
    return [(name, changes.get(name, {})) for name in ("approve", "admit", "outcome")]


def test_a_complete_hand_written_history_verifies(world):
    # the control for the refusals below: the chain is local, so a whole forged history is accepted
    assert _verify(world, _forged_chain(world, _good()))["recorded_by"] == "runner-1"


def test_a_history_with_a_second_approval_verifies(world):
    result = _forged_chain(world, [("approve", {}), ("co", {}), ("admit", {}), ("outcome", {})])
    assert _verify(world, result)["recorded_by"] == "runner-1"


@pytest.mark.parametrize("steps, why", [
    ([("outcome", {})], "not exactly one decision"),
    ([("approve", {}), ("outcome", {})], "not exactly one admission"),
    ([("admit", {}), ("outcome", {})], "not exactly one decision"),
    (_good() + [("approve", {"event_id": "second-decision"})], "not exactly one decision"),
    (_good() + [("withdraw", {"event_id": "second-ending"})], "not exactly one admission"),
    ([("reject", {}), ("admit", {}), ("outcome", {})], "no approval by someone other"),
    (_good(approve={"subject_id": "ontology-test-operator"}), "no approval by someone other"),
    ([("approve", {}), ("withdraw", {}), ("outcome", {})], "the admission is not well formed"),
    ([("approve", {}), ("withdraw", {"operation": "ontology_action_admit", "subject_id": "runner-1"}),
      ("outcome", {})], "no admission by someone other"),
    (_good(admit={"subject_id": "approver-1"}, outcome={"subject_id": "approver-1"}),
     "no admission by someone other"),
    (_good(outcome={"subject_id": "mallory"}), "not the admitter's"),
    ([("approve", {}), ("co", {"subject_id": "approver-1"}), ("admit", {}), ("outcome", {})],
     "not from a third person"),
    ([("approve", {}), ("co", {"subject_id": "ontology-test-operator"}), ("admit", {}), ("outcome", {})],
     "not from a third person"),
    ([("approve", {}), ("co", {}), ("admit", {"subject_id": "approver-2"}),
      ("outcome", {"subject_id": "approver-2"})], "no admission by someone other"),
    ([("approve", {}), ("co", {}), ("co", {"event_id": "another-co"}), ("admit", {}), ("outcome", {})],
     "not exactly one second approval"),
    ([("outcome", {}), ("approve", {}), ("admit", {})], "out of order"),
    ([("approve", {}), ("outcome", {}), ("admit", {})], "out of order"),
    ([("admit", {}), ("approve", {}), ("outcome", {})], "out of order"),
    ([("approve", {}), ("admit", {}), ("co", {}), ("outcome", {})], "out of order"),
    ([("co", {}), ("approve", {}), ("admit", {}), ("outcome", {})], "out of order"),
])
def test_an_outcome_without_the_right_history_does_not_verify(world, steps, why):
    result = _forged_chain(world, steps)
    with pytest.raises(OntologyError, match=why):
        _verify(world, result)


@pytest.mark.parametrize("name, label", [("approve", "decision"), ("admit", "admission")])
@pytest.mark.parametrize("changes", [{"event_id": "wrong-id"}, {"operation": "ontology_read"},
                                     {"decision": "deny"}, {"subject_id": " "}, {"subject_id": "unknown"}])
def test_a_malformed_step_does_not_verify(world, name, label, changes):
    result = _forged_chain(world, _good(**{name: changes}))
    with pytest.raises(OntologyError, match=f"the {label} is not well formed"):
        _verify(world, result)


@pytest.mark.parametrize("name, why", [("approve", "the decision is not well formed"),
                                       ("admit", "the admission is not well formed"),
                                       ("outcome", "not the admitter's")])
def test_a_step_naming_another_action_does_not_verify(world, name, why):
    digest = _propose(world).digest
    result = _forged_chain(world, _good(**{name: {"resource_ids": ["other-pack", "other", "1", digest]}}))
    with pytest.raises(OntologyError, match=why):
        _verify(world, result)


def test_an_outcome_for_a_never_proposed_digest_does_not_verify(world):
    digest = "sha256:" + "5" * 64
    result = {"format": simulation.RESULT_FORMAT, "proposal_digest": digest}
    world.audit.append({
        "event_id": "ontology-action-outcome-" + "5" * 64,
        "event_type": "ontology_action_simulation_succeeded", "operation": "ontology_action_outcome",
        "decision": "allow", "subject_id": "mallory", "policy_version": "v",
        "resource_ids": ["p", "a", "1", digest], "result_hash": proposal_digest(result),
        "reason": "policy_allow"})
    with pytest.raises(OntologyError, match="no recorded proposal"):
        _verify(world, result)


def test_a_repeated_proposal_still_verifies_but_a_disagreeing_one_does_not(world):
    proposal = _admitted(world)
    out = _run(world, proposal)
    assert _propose(world).digest == proposal.digest
    assert _verify(world, out["result"])["status"] == "succeeded"
    (original, *_) = _events(world, "ontology_action_proposed")
    world.audit.append({
        **{k: original[k] for k in ("event_type", "operation", "decision", "policy_version",
                                    "resource_ids", "reason")},
        "event_id": "ontology-other-proposer", "subject_id": "someone-else"})
    with pytest.raises(OntologyError, match="proposal records disagree"):
        _verify(world, out["result"])

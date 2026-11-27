"""The runner calls a simulator once per admission and records the digest of what it returned."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import pytest

from agora.audit_anchor import AnchorStore
from agora.ontology import (
    RUN_START_WINDOW_SECONDS, OntologyError, approvals, run_admitted_simulation, runner,
)

from test_ontology_action_admission import RUNNER, _approved
from test_ontology_action_approvals import APPROVER, _as, _events, catalog, world  # noqa: F401
from test_ontology_action_outcomes import _admitted, _hex, _outcomes, _record, _resources
from test_ontology_action_proposals import _allow, _deny

_STARTED = "ontology_action_simulation_started"


def _sha(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class Sim:
    """Counts calls and returns (or raises) what it was given."""

    def __init__(self, output=None, error=None):
        self.output, self.error, self.calls = {"score": 1} if output is None else output, error, []

    def __call__(self, document):
        self.calls.append(document)
        if self.error is not None:
            raise self.error
        return self.output


def _run(w, proposal, sim, simulator_id="demo.sim:1", policy=RUNNER, document=None):
    return run_admitted_simulation(
        w.store, document if document is not None else proposal.document, proposal.digest,
        simulator=sim, simulator_id=simulator_id, policy=policy, audit=w.audit,
        purpose="account support", retention="90 days")


def _starts(w):
    return _events(w, _STARTED)


def test_the_recorded_digest_is_of_the_result_the_runner_built(world):
    proposal = _admitted(world)
    sim = Sim({"score": 0.5, "notes": ["é", None, True]})
    answer = _run(world, proposal, sim)
    assert json.loads(answer["result"]) == {
        "format": "agora.ontology.simulation_result/v1", "proposal_digest": proposal.digest,
        "simulator_id": "demo.sim:1", "status": "succeeded", "output": sim.output}
    assert answer["result_digest"] == _sha(answer["result"])
    assert (answer["status"], answer["recorded_by"]) == ("succeeded", "runner-1")
    assert sim.calls == [json.loads(json.dumps(proposal.document))]
    (start,), (outcome,) = _starts(world), _outcomes(world)
    assert start["event_id"] == "ontology-action-run-" + _hex(proposal)
    assert outcome["event_id"] == "ontology-action-outcome-" + _hex(proposal)
    assert outcome["event_type"] == "ontology_action_simulation_succeeded"
    assert outcome["result_hash"] == answer["result_digest"]
    for event in (start, outcome):
        assert event["resource_ids"] == _resources(proposal) and event["subject_id"] == "runner-1"
        assert event["simulator_id_hash"] == _sha("demo.sim:1")
    assert "score" not in json.dumps([start, outcome])
    assert world.audit.verify()["valid"]


def test_the_start_is_in_the_chain_before_the_simulator_is_called(world):
    proposal = _admitted(world)
    seen = []

    def sim(document):
        seen.append((len(_starts(world)), len(_outcomes(world))))
        return {}

    _run(world, proposal, sim)
    assert seen == [(1, 0)]


@pytest.mark.parametrize("first", ["succeeds", "raises", "interrupted"])
def test_there_is_one_run_per_admission(world, first):
    proposal = _admitted(world)
    if first == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            _run(world, proposal, Sim(error=KeyboardInterrupt()))
        assert len(_starts(world)) == 1 and _outcomes(world) == []
        message = "already started"
    else:
        _run(world, proposal, Sim(error=RuntimeError("boom") if first == "raises" else None))
        message = "already has an outcome"
    again = Sim()
    with pytest.raises(OntologyError, match=message):
        _run(world, proposal, again)
    assert again.calls == [] and len(_starts(world)) == 1


def test_the_chain_refuses_a_second_start_that_raced_the_checks(world, monkeypatch):
    proposal = _admitted(world)
    with pytest.raises(KeyboardInterrupt):
        _run(world, proposal, Sim(error=KeyboardInterrupt()))
    real = type(world.audit).find_event
    monkeypatch.setattr(type(world.audit), "find_event",
                        lambda self, i: None if i.startswith("ontology-action-run-") else real(self, i))
    again = Sim()
    with pytest.raises(OntologyError, match="already started"):
        _run(world, proposal, again)
    assert again.calls == []


def test_a_started_run_cannot_be_reported_by_hand(world):
    proposal = _admitted(world)
    refused = []

    def sim(document):
        with pytest.raises(OntologyError, match="runner owns") as caught:
            _record(world, proposal)
        refused.append(caught)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(world, proposal, sim)
    with pytest.raises(OntologyError, match="runner owns"):
        _record(world, proposal, status="failed")
    assert len(refused) == 1 and _outcomes(world) == []


def test_a_hand_report_that_raced_the_start_is_refused_in_the_transaction(world, monkeypatch):
    proposal = _admitted(world)
    with pytest.raises(KeyboardInterrupt):
        _run(world, proposal, Sim(error=KeyboardInterrupt()))
    monkeypatch.setattr(type(world.audit), "find_event", lambda self, event_id: None)
    with pytest.raises(OntologyError, match="runner owns"):
        _record(world, proposal)
    assert _outcomes(world) == []


def test_after_a_hand_report_nothing_runs(world):
    proposal = _admitted(world)
    _record(world, proposal)
    sim = Sim()
    with pytest.raises(OntologyError, match="already has an outcome"):
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


def test_a_start_that_raced_a_hand_report_is_refused_in_the_transaction(world, monkeypatch):
    proposal = _admitted(world)
    _record(world, proposal)
    monkeypatch.setattr(type(world.audit), "find_event",
                        _blind_to(world, "ontology-action-outcome-"))
    sim = Sim()
    with pytest.raises(OntologyError, match="already has an outcome"):
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


def _blind_to(w, prefix):
    real = type(w.audit).find_event
    return lambda self, event_id: None if event_id.startswith(prefix) else real(self, event_id)


def test_a_simulator_that_raises_is_recorded_as_failed_without_its_message(world):
    proposal = _admitted(world)
    answer = _run(world, proposal, Sim(error=ValueError("two@example.test")))
    assert answer["status"] == "failed"
    assert json.loads(answer["result"])["failure"] == {
        "kind": "simulator_raised", "error_type": "ValueError"}
    assert "example.test" not in answer["result"]
    (outcome,) = _outcomes(world)
    assert outcome["event_type"] == "ontology_action_simulation_failed"
    assert outcome["result_hash"] == _sha(answer["result"])


def _loop():
    value = []
    value.append(value)
    return value


@pytest.mark.parametrize("output", [
    (1, 2), {1: "a"}, {"a": float("nan")}, {"a": float("inf")}, {"a": {1, 2}}, b"x", object(),
    {"a": "\ud800"}, _loop(), {"a": [(1,)]}])
def test_output_that_is_not_exactly_json_is_a_failed_run(world, output):
    proposal = _admitted(world)
    answer = _run(world, proposal, Sim(output))
    assert answer["status"] == "failed"
    assert json.loads(answer["result"])["failure"] == {"kind": "unusable_output"}
    assert _outcomes(world)[0]["event_type"] == "ontology_action_simulation_failed"


def test_a_result_over_the_size_limit_is_a_failed_run(world, monkeypatch):
    monkeypatch.setattr(runner, "MAX_RESULT_BYTES", 400)
    proposal = _admitted(world)
    assert _run(world, proposal, Sim("x" * 400))["status"] == "failed"


def test_the_simulator_gets_a_copy_of_the_proposal(world):
    proposal = _admitted(world)
    before = json.dumps(proposal.document, sort_keys=True)

    def sim(document):
        document["parameters"] = "changed"
        return {}

    _run(world, proposal, sim)
    assert json.dumps(proposal.document, sort_keys=True) == before


@pytest.mark.parametrize("by", [_as("runner-2"), APPROVER, _allow])
def test_only_the_admitter_runs(world, by):
    proposal, sim = _admitted(world), Sim()
    with pytest.raises(OntologyError, match="only the identity that admitted"):
        _run(world, proposal, sim, policy=by)
    assert sim.calls == [] and _starts(world) == []


def test_a_denied_caller_runs_nothing_and_the_chain_is_not_read(world, monkeypatch):
    proposal, sim = _admitted(world), Sim()

    def unread(*args, **kwargs):
        raise AssertionError("chain read before the decision")

    monkeypatch.setattr(runner, "_admission", unread)
    with pytest.raises(OntologyError, match="policy denied"):
        _run(world, proposal, sim, policy=_deny)
    assert sim.calls == []


def test_an_approval_alone_runs_nothing(world):
    proposal, sim = _approved(world), Sim()
    with pytest.raises(OntologyError, match="has not been admitted"):
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


def _later(monkeypatch, seconds):
    moment = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    monkeypatch.setattr(approvals, "_now", lambda: moment)


@pytest.mark.parametrize("seconds,message", [
    (RUN_START_WINDOW_SECONDS + 5, "too old to start"), (-120, "dated after the current time")])
def test_a_run_starts_only_inside_the_window_after_admission(world, monkeypatch, seconds, message):
    proposal, sim = _admitted(world), Sim()
    _later(monkeypatch, seconds)
    with pytest.raises(OntologyError, match=message):
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


def test_the_window_is_checked_again_inside_the_start_transaction(world, monkeypatch):
    proposal, sim = _admitted(world), Sim()
    real = runner.recheck_action_proposal

    def slow_recheck(*args, **kwargs):
        real(*args, **kwargs)
        _later(monkeypatch, RUN_START_WINDOW_SECONDS + 5)

    monkeypatch.setattr(runner, "recheck_action_proposal", slow_recheck)
    with pytest.raises(OntologyError, match="too old to start"):
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


def test_a_source_changed_since_admission_stops_the_run(world):
    proposal, sim = _admitted(world), Sim()
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
        _run(world, proposal, sim)
    assert sim.calls == [] and _starts(world) == []


@pytest.mark.parametrize("simulator_id", ["", "Demo", "a b", "a" * 129, "-a", "a\n", None, 7])
def test_a_badly_formed_simulator_id_is_refused(world, simulator_id):
    proposal, sim = _admitted(world), Sim()
    with pytest.raises(OntologyError, match="simulator_id must be"):
        _run(world, proposal, sim, simulator_id=simulator_id)
    assert sim.calls == [] and _starts(world) == []


def test_a_simulator_that_cannot_be_called_spends_no_run(world):
    proposal = _admitted(world)
    with pytest.raises(OntologyError, match="must be callable"):
        _run(world, proposal, "not callable")
    assert _starts(world) == []


@pytest.mark.parametrize("which,message,calls", [
    ("ontology-action-run-", "nothing was run", 0),
    ("ontology-action-outcome-", "the simulation ran", 1)])
def test_an_event_that_cannot_be_anchored_is_reported(world, monkeypatch, which, message, calls):
    proposal, sim = _admitted(world), Sim()
    event_id = which + _hex(proposal)
    original = AnchorStore.advance

    def fail(self, sequence, head):
        if world.audit.chain.find_event(event_id) is not None:
            raise OSError("disk full")
        return original(self, sequence, head)

    monkeypatch.setattr(AnchorStore, "advance", fail)
    with pytest.raises(OntologyError, match=message):
        _run(world, proposal, sim)
    assert len(sim.calls) == calls


class _Hostile(dict):
    def items(self):
        raise RuntimeError("no")


def test_an_object_that_raises_while_read_still_gets_an_outcome(world):
    proposal = _admitted(world)
    answer = _run(world, proposal, Sim(_Hostile(a=1)))
    assert answer["status"] == "failed" and len(_outcomes(world)) == 1


def test_an_odd_exception_name_is_not_copied_into_the_result(world):
    proposal = _admitted(world)
    odd = type("two@example.test", (Exception,), {})
    answer = _run(world, proposal, Sim(error=odd()))
    assert json.loads(answer["result"])["failure"]["error_type"] == "other"


def test_the_result_is_built_from_one_reading_of_the_output(world, monkeypatch):
    proposal = _admitted(world)
    output = {"value": "first"}
    real = runner._same_json

    def change_after_check(left, right):
        same = real(left, right)
        if left is output:
            output["value"] = "second"
        return same

    monkeypatch.setattr(runner, "_same_json", change_after_check)
    assert json.loads(_run(world, proposal, Sim(output))["result"])["output"] == {"value": "first"}


@pytest.mark.parametrize("state,message", [("started", "already started"), ("stale", "too old to start")])
def test_a_run_that_cannot_start_is_refused_before_the_objects_are_read(
        world, monkeypatch, state, message):
    proposal = _admitted(world)
    if state == "started":
        with pytest.raises(KeyboardInterrupt):
            _run(world, proposal, Sim(error=KeyboardInterrupt()))
    else:
        _later(monkeypatch, RUN_START_WINDOW_SECONDS + 5)

    def unread(*args, **kwargs):
        raise AssertionError("objects must not be read")

    monkeypatch.setattr(runner, "recheck_action_proposal", unread)
    with pytest.raises(OntologyError, match=message):
        _run(world, proposal, Sim())

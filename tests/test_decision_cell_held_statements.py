"""Statements a source study already holds are traced to their ratings and need the grant again. Synthetic data."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3

import pytest

from agora.decision_cell import (
    Escalation, EscalationStatus, InputGrant, Option, ProjectRecord, StatementRating, StudyState,
    execute_continuation, execute_event_fork, item_evidence, record_run_result, register_item_statements,
    request_labelled_option, statement_input_id,
)
from agora.decision_cell import executor as ex
from agora.decision_cell.held import trace_held_statements
from agora.decision_cell.statements import StatementSetError
from agora.sim.engine import Simulation
from conftest import make_project
from tests.test_decision_cell_evidence import PAIR, SOLE, STUDY as GATE_STUDY, choice, run_context, view
from tests.test_decision_cell_executor import STUDY, go, left, recorded, refused
from tests.test_decision_cell_retractions import SCOPE
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401

EARLIER = "the price will rise next month"
OTHER = "an unrelated remark"
KEY = statement_input_id("old", "o1")
MISSING = f"data_owner_grant_missing:{KEY}"
PERSONAL = StatementRating("personal", "dana")
PLAIN = StatementRating("internal")
HELD = json.dumps({"round": 1, "text": EARLIER, "type": "news"}, sort_keys=True, separators=(",", ":"))


def built(tmp_path_factory, raw_events):
    project = make_project(tmp_path_factory.mktemp("held"), "source", rounds=6,
                           population={"llm_agents": 2, "crowd_agents": 20})
    sim = Simulation(project, snapshot_rounds=(2,))
    try:
        sim.prepare()
        with sim.store.db:
            sim.store.db.executemany("INSERT INTO injected (round, event) VALUES (?, ?)", raw_events)
        sim.run()
    finally:
        sim.close()
    return project


@pytest.fixture(scope="module")
def built_held(tmp_path_factory):
    return built(tmp_path_factory, [(1, HELD)])


@pytest.fixture
def source(built_held, tmp_path):
    copy = tmp_path / "source"
    shutil.copytree(built_held, copy)
    return copy


def register(audit, item="old", wording=EARLIER, rating=PERSONAL, version=0, scope=SCOPE):
    return register_item_statements(item_id=item, statements={"o1": wording}, ratings={"o1": rating},
                                    expected_version=version, audit=audit, **scope)


def parent(audit, other_items=("old",), result="p0", source=None, out=None):
    """A recorded earlier result whose basis includes ``other_items``.

    With ``source`` and ``out``, it also leaves the manifest an executor would have left if that source's
    round-2 snapshot were one of its branches. The tests of a real chain are in the lineage module.
    """
    raw = b"no output"
    if source is not None:
        meta = json.loads((source / "snapshots" / "round-00002.json").read_text(encoding="utf-8"))
        raw = json.dumps({"branches": {ex.WITH_EVENT: {"snapshots": {"2": meta["meta_digest"]}}}}).encode()
        directory = ex._result_dir(out, "t1", "p1", "s1", result)
        directory.mkdir(parents=True)
        (directory / ex.RESULT_FILE).write_bytes(raw)
    evidence = view(audit)
    gate = request_labelled_option(
        OWNER, choice(Option.FORK_FROM_EVENT, evidence.evidence_hash, event_round=2), statements=(PAIR,),
        tenant_id="t1", project_id="p1", audit=audit, study=GATE_STUDY, now=NOW, **run_context()).gate
    assert gate.executable, gate.failures
    record_run_result(result_id=result, gate_event_id=gate.audit_event_id,
                      result_hash=hashlib.sha256(raw).hexdigest(),
                      other_item_ids=other_items, audit=audit, **SCOPE)
    return (result,)


def grant(input_id=KEY):
    return InputGrant("p1", "s1", input_id, OWNER.subject_id, "dana")


def made(audit, source, tmp_path, **kw):
    return parent(audit, source=source, out=tmp_path / "out", **kw)


def untraced(audit, source, tmp_path, code="SOURCE_EVENT_UNTRACED", **kw):
    view(audit)
    before, there = len(events(audit)), left(tmp_path / "out")
    refused(code, lambda: go(audit, source, tmp_path / "out", **kw))
    assert len(events(audit)) == before and left(tmp_path / "out") == there


def blocked(audit, source, tmp_path, failures, **kw):
    there = left(tmp_path / "out")
    error = refused("GATE_BLOCKED", lambda: go(audit, source, tmp_path / "out", **kw))
    assert error.gate.failures == failures
    assert recorded(audit) is None and left(tmp_path / "out") == there


def test_a_held_personal_statement_needs_its_owners_grant(audit, source, tmp_path):
    register(audit)
    parents = made(audit, source, tmp_path)
    blocked(audit, source, tmp_path, (MISSING,), parent_result_ids=parents)
    assert events(audit)[-1]["decision"] == "deny" and f"held:{KEY}" in events(audit)[-1]["resource_ids"]


def test_with_the_grant_it_runs_and_the_result_says_what_it_holds(audit, source, tmp_path):
    register(audit)
    done = go(audit, source, tmp_path / "out", parent_result_ids=made(audit, source, tmp_path),
              grants=(grant(),))
    assert done.manifest["held_statement_ids"] == [KEY]
    assert done.basis.item_ids == ("e1", "old")


def test_an_internal_held_statement_needs_no_grant(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    done = go(audit, source, tmp_path / "out", parent_result_ids=made(audit, source, tmp_path))
    assert done.manifest["held_statement_ids"] == [KEY]


def test_a_continuation_asks_for_the_held_grant_too(audit, tmp_path):
    register(audit)
    # Its own project: a continuation needs a source stopped part-way, with a snapshot at its last round.
    project = make_project(tmp_path, "unfinished", rounds=6, population={"llm_agents": 2, "crowd_agents": 20})
    sim = Simulation(project, snapshot_rounds=(2,))
    try:
        sim.prepare()
        with sim.store.db:
            sim.store.db.execute("INSERT INTO injected (round, event) VALUES (1, ?)", (HELD,))
        sim.run(should_stop=lambda: sim.store.last_round() >= 2)
    finally:
        sim.close()
    parents = made(audit, project, tmp_path)
    request = choice(Option.CONTINUE, view(audit).evidence_hash, budget_units=100_000)
    error = refused("GATE_BLOCKED", lambda: execute_continuation(
        OWNER, request, statements=(PAIR,), tenant_id="t1", project_id="p1", study=StudyState("s1", 2),
        result_id="res1", source=project, out_dir=tmp_path / "out", kill_switch_on=lambda: False,
        audit=audit, parent_result_ids=parents, now=NOW))
    assert error.gate.failures == (MISSING,)


def test_a_source_with_held_events_and_no_parent_is_refused(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    untraced(audit, source, tmp_path, code="SOURCE_NOT_PARENT_OUTPUT")


def test_a_parent_that_does_not_rest_on_the_item_does_not_trace_it(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    untraced(audit, source, tmp_path, parent_result_ids=made(audit, source, tmp_path, other_items=()))


def test_a_parent_that_only_rests_on_the_item_does_not_trace_it_for_the_producer(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    producer = made(audit, source, tmp_path, other_items=())
    bystander = parent(audit, result="p9")  # rests on the item, produced nothing
    untraced(audit, source, tmp_path, parent_result_ids=producer + bystander)


def test_words_recorded_nowhere_are_untraced(audit, source, tmp_path):
    register(audit, wording=OTHER, rating=PLAIN)
    untraced(audit, source, tmp_path, parent_result_ids=made(audit, source, tmp_path))


def test_the_same_words_rated_higher_elsewhere_still_need_the_grant(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    register(audit, item="twin")  # not in any parent's basis
    twin = statement_input_id("twin", "o1")
    blocked(audit, source, tmp_path, (f"data_owner_grant_missing:{twin}",), parent_result_ids=parents)


def test_another_studys_rating_of_the_words_is_not_judged(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    register(audit, item="elsewhere", scope={**SCOPE, "study_id": "s2"})
    done = go(audit, source, tmp_path / "out", parent_result_ids=made(audit, source, tmp_path))
    assert done.manifest["held_statement_ids"] == [KEY]


def test_a_rating_raised_after_the_source_ran_applies(audit, source, tmp_path):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    register(audit, version=1)
    blocked(audit, source, tmp_path, (MISSING,), parent_result_ids=parents)


@pytest.mark.parametrize("event", [
    {"round": 1, "text": EARLIER, "type": "post"},
    {"round": 1, "text": EARLIER, "type": "news", "shift": {"x": 1}},
    {"round": 0, "text": EARLIER, "type": "news"},
    {"text": EARLIER, "type": "news"},
    {"round": 1, "text": 7, "type": "news"},
    {},
])
def test_an_event_not_shaped_like_a_run_adds_is_untraced(audit, event):
    register(audit, rating=PLAIN)
    parents = parent(audit)
    trace = dict(parent_result_ids=parents, audit=audit, **SCOPE)
    assert trace_held_statements(added_events=((1, HELD),), **trace).inputs
    assert trace_held_statements(added_events=((1, HELD), (1, json.dumps(event))), **trace) is None


def test_a_list_recorded_between_the_read_and_the_commit_stops_the_run(audit, source, tmp_path, monkeypatch):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    real = ex.trace_held_statements

    def then_register(**kw):
        held = real(**kw)
        register(audit, item="twin")
        return held

    monkeypatch.setattr(ex, "trace_held_statements", then_register)
    view(audit)
    there = left(tmp_path / "out")
    before = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    with pytest.raises(StatementSetError) as caught:
        go(audit, source, tmp_path / "out", parent_result_ids=parents)
    assert caught.value.code == "STATEMENTS_CHANGED"
    assert [e for e in events(audit) if e["event_type"] == "decision_cell_option"] == before
    assert left(tmp_path / "out") == there


def test_another_studys_new_list_does_not_stop_the_run(audit, source, tmp_path, monkeypatch):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    real = ex.trace_held_statements

    def then_register(**kw):
        held = real(**kw)
        register(audit, item="elsewhere", scope={**SCOPE, "study_id": "s2"})
        return held

    monkeypatch.setattr(ex, "trace_held_statements", then_register)
    assert go(audit, source, tmp_path / "out", parent_result_ids=parents).manifest["held_statement_ids"] == [KEY]


def test_a_snapshot_whose_events_changed_after_the_trace_is_blocked(audit, source, tmp_path, monkeypatch):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    real, calls = ex._carried_events, []

    def changing(*args):
        calls.append(args)
        events_now, digest = real(*args)
        return (events_now if len(calls) == 1 else events_now + ((1, HELD),)), digest

    monkeypatch.setattr(ex, "_carried_events", changing)
    blocked(audit, source, tmp_path, ("snapshot_unavailable",), parent_result_ids=parents)


def test_a_failed_first_restore_is_never_passed_as_verified(audit, source, tmp_path, monkeypatch):
    register(audit)  # personal: skipping the check would let the run through without a grant
    parents = made(audit, source, tmp_path)
    real, calls = ex._carried_events, []

    def flaky(*args):
        calls.append(args)
        if len(calls) == 1:
            raise OSError("busy")
        return real(*args)

    monkeypatch.setattr(ex, "_carried_events", flaky)
    blocked(audit, source, tmp_path, ("snapshot_unavailable",), parent_result_ids=parents)


def test_a_branch_carrying_other_events_is_not_run(audit, source, tmp_path, monkeypatch):
    register(audit, rating=PLAIN)
    parents = made(audit, source, tmp_path)
    real = Simulation.fork_from

    def tampering(src, round, dest, **kw):
        made = real(src, round, dest, **kw)
        if made.name == ex.WITH_EVENT:
            conn = sqlite3.connect(made / "agora.db")
            with conn:
                conn.execute("INSERT INTO injected (round, event) VALUES (2, ?)", (HELD,))
            conn.close()
        return made

    monkeypatch.setattr(Simulation, "fork_from", staticmethod(tampering))
    there = left(tmp_path / "out")
    refused("SOURCE_CHANGED", lambda: go(audit, source, tmp_path / "out", parent_result_ids=parents))
    assert recorded(audit) is None and left(tmp_path / "out") == there


def test_a_second_approval_covers_the_held_ratings(audit):
    register(audit, rating=PLAIN)
    parents = parent(audit)
    evidence = view(audit)

    def ask(held):
        return request_labelled_option(
            OWNER, choice(Option.FORK_FROM_EVENT, evidence.evidence_hash, event_round=2), statements=(PAIR,),
            tenant_id="t1", project_id="p1", audit=audit, study=GATE_STUDY, now=NOW, held=held,
            grants=(grant(),), **run_context()).gate

    trace = lambda: trace_held_statements(added_events=((1, HELD),), parent_result_ids=parents,
                                          audit=audit, **SCOPE)
    without, plain = ask(None), ask(trace())
    register(audit, version=1)
    raised = ask(trace())
    assert len({without.action_fingerprint, plain.action_fingerprint, raised.action_fingerprint}) == 3


def test_a_caller_cannot_hand_the_gate_raw_held_inputs_or_another_studys(audit):
    register(audit)
    parents = parent(audit)
    evidence = view(audit)
    request = choice(Option.FORK_FROM_EVENT, evidence.evidence_hash, event_round=2)
    kw = dict(statements=(PAIR,), tenant_id="t1", project_id="p1", audit=audit, study=GATE_STUDY, now=NOW)
    held = trace_held_statements(added_events=((1, HELD),), parent_result_ids=parents, audit=audit, **SCOPE)
    before = len(events(audit))
    with pytest.raises(Exception) as caught:
        request_labelled_option(OWNER, request, held_statements=(), **kw, **run_context())
    assert getattr(caught.value, "code", None) == "RECORD_INVALID"
    with pytest.raises(Exception) as caught:
        request_labelled_option(OWNER, request, held=held, **{**kw, "study": StudyState("s2", 5)},
                                **run_context())
    assert getattr(caught.value, "code", None) == "REQUEST_INVALID"
    assert len(events(audit)) == before

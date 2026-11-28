"""CONTINUE through the gate, run and recorded as one call. Synthetic data and the mock backend only."""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    Option,
    StudyState,
    execute_continuation,
    execute_event_fork,
    fork_branch_cost,
    read_continuation,
    read_event_fork,
)
from agora.decision_cell import executor as ex
from agora.sim.engine import Simulation
from conftest import make_project
from tests.test_decision_cell_evidence import PAIR, choice, view
from tests.test_decision_cell_executor import added_events, files, go, left, recorded, refused
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401

HALFWAY = StudyState("s1", 2)


@pytest.fixture(scope="module")
def built_halfway(tmp_path_factory):
    """Six rounds in the scenario, three of them run, with a snapshot at the last one."""
    project = make_project(tmp_path_factory.mktemp("built"), "source", rounds=6,
                           population={"llm_agents": 2, "crowd_agents": 20})
    sim = Simulation(project, snapshot_rounds=(2,))
    try:
        sim.prepare()
        sim.run(rounds=3)
    finally:
        sim.close()
    return project


@pytest.fixture
def source(built_halfway, tmp_path):
    copy = tmp_path / "source"
    shutil.copytree(built_halfway, copy)
    return copy


def cont(audit, source, out, result="res1", **kw):
    request = kw.pop("request", None)
    if request is None:
        request = choice(Option.CONTINUE, view(audit).evidence_hash, budget_units=100_000)
    kw.setdefault("study", HALFWAY)
    kw.setdefault("kill_switch_on", lambda: False)
    return execute_continuation(OWNER, request, statements=(PAIR,), tenant_id="t1", project_id="p1",
                                result_id=result, source=source, out_dir=out, audit=audit, now=NOW, **kw)


def read(audit, out, result="res1"):
    return read_continuation(result_id=result, out_dir=out, audit=audit, **SCOPE)


def last_round(project):
    conn = sqlite3.connect(project / "agora.db")
    try:
        return conn.execute("SELECT MAX(round) FROM rounds").fetchone()[0]
    finally:
        conn.close()


def no_gate(audit, source, out, code, **kw):
    view(audit)
    before = len(events(audit))
    refused(code, lambda: cont(audit, source, out, **kw))
    assert len(events(audit)) == before and recorded(audit) is None


def test_a_continuation_adds_the_item_at_the_next_round_and_leaves_the_source(audit, source, tmp_path):
    before = files(source)
    done = cont(audit, source, tmp_path / "out")
    assert files(source) == before and last_round(source) == 2
    project = done.path / ex.CONTINUED
    assert added_events(project) == [(3, {"round": 3, "text": PAIR.statement_text, "type": "news"})]
    assert last_round(project) == 5
    assert sorted(p.name for p in done.path.iterdir()) == [ex.CONTINUED, ex.RESULT_FILE]
    assert list(done.manifest["branches"]) == [ex.CONTINUED]
    assert done.manifest["schema"] == ex.CONTINUATION_SCHEMA
    assert done.manifest["continued_from_round"] == 2 and done.manifest["added_in_round"] == 3
    assert "event_round" not in done.manifest
    assert done.manifest["llm_backend"] == "mock" and done.manifest["validated_prediction_enabled"] is False
    assert done.basis == recorded(audit) and done.basis.item_ids == ("e1",) and done.stamps == ()
    gate = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    assert len(gate) == 1 and gate[0]["event_id"] == done.basis.gate_event_id and gate[0]["operation"] == "CONTINUE"
    # One branch, so the price is one branch of the remaining rounds.
    assert done.manifest["cost_units"] == gate[0]["count"] == fork_branch_cost(source, 2) > 0
    assert left(tmp_path / "out") == [done.path.name]
    assert read(audit, tmp_path / "out") == done


def test_a_later_retraction_stamps_the_continuation(audit, source, tmp_path):
    cont(audit, source, tmp_path / "out")
    new_item(audit, "r1")
    link(audit)
    assert read(audit, tmp_path / "out").stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_the_budget_is_judged_on_one_branch_from_the_last_round(audit, source, tmp_path):
    cost = fork_branch_cost(source, 2)
    short = choice(Option.CONTINUE, view(audit).evidence_hash, budget_units=cost - 1)
    error = refused("GATE_BLOCKED", lambda: cont(audit, source, tmp_path / "out", request=short))
    assert error.gate.failures == ("budget_confirmation_required",) and left(tmp_path / "out") == []
    exact = choice(Option.CONTINUE, view(audit).evidence_hash, budget_units=cost)
    assert cont(audit, source, tmp_path / "out", request=exact).manifest["cost_units"] == cost


def test_no_snapshot_at_the_last_round_blocks_and_nothing_is_rerun(audit, source, tmp_path):
    shutil.rmtree(source / "snapshots")
    error = refused("GATE_BLOCKED", lambda: cont(audit, source, tmp_path / "out"))
    assert error.gate.failures == ("snapshot_unavailable",) and left(tmp_path / "out") == []


@pytest.mark.parametrize("option", [o for o in Option if o is not Option.CONTINUE])
def test_the_continuation_call_executes_nothing_else(audit, source, tmp_path, option):
    request = choice(option, view(audit).evidence_hash, event_round=2)
    no_gate(audit, source, tmp_path / "out", "OPTION_NOT_EXECUTABLE", request=request)


@pytest.mark.parametrize("named", [0, 2])
def test_a_named_event_round_is_refused(audit, source, tmp_path, named):
    request = choice(Option.CONTINUE, view(audit).evidence_hash, event_round=named, budget_units=100_000)
    no_gate(audit, source, tmp_path / "out", "INPUT_INVALID", request=request)


def test_a_study_state_for_another_round_is_refused(audit, source, tmp_path):
    no_gate(audit, source, tmp_path / "out", "STUDY_ROUND_MISMATCH", study=StudyState("s1", 1))


def test_a_finished_study_has_no_round_to_continue_into(audit, source, tmp_path):
    sim = Simulation(source)
    try:
        sim.run()
    finally:
        sim.close()
    no_gate(audit, source, tmp_path / "out", "NO_ROUND_LEFT", study=StudyState("s1", 5))


def test_events_already_queued_for_later_rounds_are_not_silently_dropped(audit, source, tmp_path):
    conn = sqlite3.connect(source / "agora.db")
    with conn:
        conn.execute("INSERT INTO injected (round, event) VALUES (3, '{}')")
    conn.close()
    no_gate(audit, source, tmp_path / "out", "SOURCE_HAS_LATER_EVENTS")


def test_a_kill_switch_during_a_continuation_releases_and_records_nothing(audit, source, tmp_path):
    answers = iter([False, False])
    refused("STOPPED_BY_KILL_SWITCH", lambda: cont(
        audit, source, tmp_path / "out", kill_switch_on=lambda: next(answers, True)))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_nothing_is_released_if_a_continuation_cannot_be_recorded(audit, source, tmp_path):
    refused("RUN:ITEM_NOT_REGISTERED",
            lambda: cont(audit, source, tmp_path / "out", other_item_ids=("never-listed",)))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_changed_continued_database_is_not_shown(audit, source, tmp_path):
    done = cont(audit, source, tmp_path / "out")
    conn = sqlite3.connect(done.path / ex.CONTINUED / "agora.db")
    with conn:
        conn.execute("UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
    conn.close()
    refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))


def test_a_continuation_is_not_read_as_a_comparison(audit, source, tmp_path):
    cont(audit, source, tmp_path / "out")
    refused("WRONG_RESULT_KIND", lambda: read_event_fork(
        result_id="res1", out_dir=tmp_path / "out", audit=audit, **SCOPE))


def test_a_comparison_is_not_read_as_a_continuation(audit, source, tmp_path):
    go(audit, source, tmp_path / "out", study=HALFWAY)
    refused("WRONG_RESULT_KIND", lambda: read(audit, tmp_path / "out"))


def test_one_result_id_is_not_shared_between_the_two_kinds(audit, source, tmp_path):
    cont(audit, source, tmp_path / "out")
    refused("RESULT_ALREADY_RECORDED", lambda: go(audit, source, tmp_path / "other", study=HALFWAY))
    refused("OPTION_NOT_EXECUTABLE", lambda: execute_event_fork(
        OWNER, choice(Option.CONTINUE, view(audit).evidence_hash), statements=(PAIR,), tenant_id="t1",
        project_id="p1", study=HALFWAY, result_id="res2", source=source, out_dir=tmp_path / "out",
        kill_switch_on=lambda: False, audit=audit, now=NOW))

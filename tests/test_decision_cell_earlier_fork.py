"""FORK_FROM_EARLIER through the gate, run and recorded as one call. Synthetic data and the mock backend only."""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    Option,
    StudyState,
    execute_earlier_fork,
    fork_branch_cost,
    read_earlier_fork,
    read_event_fork,
)
from agora.decision_cell import executor as ex
from agora.sim.engine import Simulation
from conftest import make_project
from tests.test_decision_cell_evidence import PAIR, choice, view
from tests.test_decision_cell_executor import STUDY, added_events, files, go, left, recorded, refused
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401


@pytest.fixture(scope="module")
def built_source(tmp_path_factory):
    project = make_project(tmp_path_factory.mktemp("built-earlier"), "source", rounds=6,
                           population={"llm_agents": 2, "crowd_agents": 20})
    sim = Simulation(project, snapshot_rounds=(1, 3))
    try:
        sim.prepare()
        sim.run()
    finally:
        sim.close()
    return project


@pytest.fixture
def source(built_source, tmp_path):
    copy = tmp_path / "source"
    shutil.copytree(built_source, copy)
    return copy


def request_for(audit, *, event_round=3, from_round=1, **kw):
    kw.setdefault("budget_units", 100_000)
    return choice(Option.FORK_FROM_EARLIER, view(audit).evidence_hash, event_round=event_round,
                  from_round=from_round, **kw)


def earlier(audit, source, out, result="res1", **kw):
    request = kw.pop("request", None) or request_for(audit)
    kw.setdefault("study", STUDY)
    kw.setdefault("kill_switch_on", lambda: False)
    return execute_earlier_fork(OWNER, request, statements=(PAIR,), tenant_id="t1", project_id="p1",
                                result_id=result, source=source, out_dir=out, audit=audit, now=NOW, **kw)


def read(audit, out, result="res1"):
    return read_earlier_fork(result_id=result, out_dir=out, audit=audit, **SCOPE)


def no_gate(audit, source, out, code, **kw):
    kw.setdefault("request", request_for(audit))
    before = len(events(audit))
    refused(code, lambda: earlier(audit, source, out, **kw))
    assert len(events(audit)) == before and recorded(audit) is None and left(out) == []


def blocked(audit, source, out, request):
    error = refused("GATE_BLOCKED", lambda: earlier(audit, source, out, request=request))
    assert recorded(audit) is None and left(out) == []
    return error.gate.failures


def add_event(source, at):
    conn = sqlite3.connect(source / "agora.db")
    try:
        with conn:
            conn.execute("INSERT INTO injected (round, event) VALUES (?, '{}')", (at,))
    finally:
        conn.close()


def test_the_item_arrives_in_the_round_after_the_earlier_one(audit, source, tmp_path):
    before = files(source)
    done = earlier(audit, source, tmp_path / "out")
    assert files(source) == before
    assert added_events(done.path / ex.WITH_EVENT) == [(2, {"round": 2, "text": PAIR.statement_text,
                                                           "type": "news"})]
    assert added_events(done.path / ex.WITHOUT_EVENT) == []
    manifest, branches = done.manifest, done.manifest["branches"]
    assert manifest["schema"] == ex.EARLIER_FORK_SCHEMA
    assert (manifest["forked_from_round"], manifest["added_in_round"], manifest["event_round"]) == (1, 2, 3)
    assert manifest["event_placement"] == "hypothetical-earlier"
    assert "continued_from_round" not in manifest
    assert manifest["llm_backend"] == "mock" and manifest["validated_prediction_enabled"] is False
    assert branches[ex.WITH_EVENT]["final_state_digest"] != branches[ex.WITHOUT_EVENT]["final_state_digest"]
    assert branches[ex.WITH_EVENT]["snapshot_meta_digest"] == branches[ex.WITHOUT_EVENT]["snapshot_meta_digest"]
    assert done.basis == recorded(audit) and done.basis.item_ids == ("e1",) and done.stamps == ()
    gate = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    assert len(gate) == 1 and gate[0]["event_id"] == done.basis.gate_event_id
    assert gate[0]["operation"] == Option.FORK_FROM_EARLIER.value
    # Priced from the earlier round, which has more rounds left than the event round, for two branches.
    assert fork_branch_cost(source, 1) > fork_branch_cost(source, 3) > 0
    assert manifest["cost_units"] == gate[0]["count"] == 2 * fork_branch_cost(source, 1)
    assert read(audit, tmp_path / "out") == done


def test_it_runs_the_same_branches_as_a_fork_whose_event_round_is_the_earlier_one(audit, source, tmp_path):
    # On the mock backend only the placement decides the outcome; the two kinds differ in what they claim.
    plain = go(audit, source, tmp_path / "forks", result="fork1", request=choice(
        Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=1, budget_units=100_000))
    done = earlier(audit, source, tmp_path / "out")
    for name in (ex.WITH_EVENT, ex.WITHOUT_EVENT):
        assert done.manifest["branches"][name] == plain.manifest["branches"][name]


def test_the_two_kinds_of_fork_cannot_be_read_as_each_other(audit, source, tmp_path):
    earlier(audit, source, tmp_path / "out")
    refused("WRONG_RESULT_KIND", lambda: read_event_fork(
        result_id="res1", out_dir=tmp_path / "out", audit=audit, **SCOPE))
    go(audit, source, tmp_path / "out", result="fork1", request=choice(
        Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=3, budget_units=100_000))
    refused("WRONG_RESULT_KIND", lambda: read(audit, tmp_path / "out", "fork1"))


def test_a_later_retraction_stamps_the_earlier_fork(audit, source, tmp_path):
    earlier(audit, source, tmp_path / "out")
    new_item(audit, "r1")
    link(audit)
    assert read(audit, tmp_path / "out").stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_a_changed_branch_is_refused_on_read(audit, source, tmp_path):
    done = earlier(audit, source, tmp_path / "out")
    conn = sqlite3.connect(done.path / ex.WITHOUT_EVENT / "agora.db")
    try:
        with conn:
            conn.execute("DELETE FROM rounds WHERE round = 5")
    finally:
        conn.close()
    refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))


@pytest.mark.parametrize("from_round", [None, -1, True, 1.0])
def test_the_round_to_fork_from_is_required(audit, source, tmp_path, from_round):
    no_gate(audit, source, tmp_path / "out", "INPUT_INVALID",
            request=request_for(audit, from_round=from_round))


@pytest.mark.parametrize("event_round", [None, -1, True, 3.0])
def test_the_event_round_is_required(audit, source, tmp_path, event_round):
    no_gate(audit, source, tmp_path / "out", "INPUT_INVALID",
            request=request_for(audit, event_round=event_round))


def test_an_event_round_the_study_has_not_reached_is_refused(audit, source, tmp_path):
    conn = sqlite3.connect(source / "agora.db")
    try:
        with conn:
            conn.execute("DELETE FROM rounds WHERE round > 3")
    finally:
        conn.close()
    no_gate(audit, source, tmp_path / "out", "EVENT_ROUND_NOT_REACHED",
            request=request_for(audit, event_round=4), study=StudyState("s1", 3))


@pytest.mark.parametrize("from_round", [3, 4])
def test_a_round_that_is_not_earlier_than_the_event_is_blocked_by_the_gate(audit, source, tmp_path, from_round):
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, from_round=from_round))
    assert "from_round_not_before_event" in failures


def test_a_round_with_no_snapshot_is_blocked_and_nothing_is_rerun_in_its_place(audit, source, tmp_path):
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, from_round=2))
    assert failures == ("snapshot_unavailable",)


@pytest.mark.parametrize("at", [2, 3, 5])
def test_a_source_with_events_added_after_the_earlier_round_is_refused(audit, source, tmp_path, at):
    add_event(source, at)  # round 2 and 3 are not later than the event round, and would still be dropped
    no_gate(audit, source, tmp_path / "out", "SOURCE_HAS_LATER_EVENTS")


def test_over_budget_needs_the_exact_two_branch_cost(audit, source, tmp_path):
    cost = 2 * fork_branch_cost(source, 1)
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, budget_units=cost - 1))
    assert failures == ("budget_confirmation_required",)
    done = earlier(audit, source, tmp_path / "out",
                   request=request_for(audit, budget_units=cost - 1, confirmed_cost_units=cost))
    assert done.manifest["cost_units"] == cost


@pytest.mark.parametrize("option", [Option.FORK_FROM_EVENT, Option.CONTINUE, Option.RERUN_FROM_START])
def test_only_this_option_is_executed(audit, source, tmp_path, option):
    request = choice(option, view(audit).evidence_hash, event_round=3)
    no_gate(audit, source, tmp_path / "out", "OPTION_NOT_EXECUTABLE", request=request)


def test_the_kill_switch_during_the_run_releases_nothing(audit, source, tmp_path):
    seen = {"count": 0}

    def on_after_start():
        seen["count"] += 1
        return seen["count"] > 2

    refused("STOPPED_BY_KILL_SWITCH",
            lambda: earlier(audit, source, tmp_path / "out", kill_switch_on=on_after_start))
    assert recorded(audit) is None and left(tmp_path / "out") == []

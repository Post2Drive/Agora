"""FORK_FROM_EVENT through the gate, run and recorded as one call. Synthetic data and the mock backend only."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    CorrectionError,
    Option,
    StudyState,
    execute_event_fork,
    fork_branch_cost,
    load_run_result,
    read_event_fork,
)
from agora.decision_cell import executor as ex
from agora.sim.engine import Simulation
from conftest import make_project
from tests.test_decision_cell_evidence import PAIR, choice, view
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401

STUDY = StudyState("s1", 5)


def _run_source(project):
    sim = Simulation(project, snapshot_rounds=(2,))
    try:
        sim.prepare()
        sim.run()
    finally:
        sim.close()


@pytest.fixture(scope="module")
def built_source(tmp_path_factory):
    project = make_project(tmp_path_factory.mktemp("built"), "source", rounds=6,
                           population={"llm_agents": 2, "crowd_agents": 20})
    _run_source(project)
    return project


@pytest.fixture
def source(built_source, tmp_path):
    copy = tmp_path / "source"
    shutil.copytree(built_source, copy)
    return copy


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(("-wal", "-shm"))}


def go(audit, source, out, result="res1", **kw):
    request = kw.pop("request", None)
    if request is None:
        request = choice(Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=2,
                         budget_units=100_000)
    kw.setdefault("study", STUDY)
    kw.setdefault("kill_switch_on", lambda: False)
    kw.setdefault("statements", (PAIR,))
    return execute_event_fork(OWNER, request, tenant_id="t1", project_id="p1", result_id=result,
                              source=source, out_dir=out, audit=audit, now=NOW, **kw)


def read(audit, out, result="res1"):
    return read_event_fork(result_id=result, out_dir=out, audit=audit, **SCOPE)


def recorded(audit, result="res1"):
    return load_run_result(result_id=result, audit=audit, **SCOPE)


def refused(code, call):
    with pytest.raises(CorrectionError if code.startswith("RUN:") else ex.ExecutionError) as caught:
        call()
    assert caught.value.code == code.removeprefix("RUN:"), str(caught.value)
    return caught.value


def left(out):
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


def added_events(project):
    conn = sqlite3.connect(project / "agora.db")
    try:
        return [(r, json.loads(e)) for r, e in conn.execute("SELECT round, event FROM injected ORDER BY id")]
    finally:
        conn.close()


def test_a_fork_runs_two_branches_records_one_result_and_leaves_the_source(audit, source, tmp_path):
    before = files(source)
    done = go(audit, source, tmp_path / "out")
    assert files(source) == before
    assert added_events(done.path / ex.WITH_EVENT) == [(3, {"round": 3, "text": PAIR.statement_text,
                                                           "type": "news"})]
    assert added_events(done.path / ex.WITHOUT_EVENT) == []
    branches = done.manifest["branches"]
    assert branches[ex.WITH_EVENT]["final_state_digest"] != branches[ex.WITHOUT_EVENT]["final_state_digest"]
    assert done.basis == recorded(audit) and done.basis.item_ids == ("e1",) and done.stamps == ()
    gate = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    assert len(gate) == 1 and gate[0]["event_id"] == done.basis.gate_event_id
    cost = fork_branch_cost(source, 2)
    assert cost > 0 and done.manifest["cost_units"] == gate[0]["count"] == 2 * cost
    assert done.manifest["llm_backend"] == "mock"
    assert done.manifest["validated_prediction_enabled"] is False
    assert done.manifest["statement_labels"] == {"st1": "REPORTED-BY-MULTIPLE"}
    assert left(tmp_path / "out") == [done.path.name]
    assert read(audit, tmp_path / "out") == done


def test_a_later_retraction_stamps_the_comparison_when_read(audit, source, tmp_path):
    go(audit, source, tmp_path / "out")
    new_item(audit, "r1")
    link(audit)
    assert read(audit, tmp_path / "out").stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_a_retraction_that_arrives_during_the_run_stamps_the_returned_result(audit, source, tmp_path):
    view(audit)  # registers e1 first: a correcting item has to be the newer one
    new_item(audit, "r1")
    linked = []

    def probe():
        gate_written = any(e["event_type"] == "decision_cell_option" for e in events(audit))
        if gate_written and not linked:
            linked.append(link(audit))
        return False

    done = go(audit, source, tmp_path / "out", kill_switch_on=probe)
    assert linked and done.stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_a_blocked_choice_runs_nothing(audit, source, tmp_path):
    view(audit)
    request = choice(Option.FORK_FROM_EVENT, "0" * 64, event_round=2, budget_units=100_000)
    error = refused("GATE_BLOCKED", lambda: go(audit, source, tmp_path / "out", request=request))
    assert error.gate.failures == ("evidence_changed_since_viewed",)
    assert events(audit)[-1]["decision"] == "deny"
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_the_budget_is_judged_on_the_cost_worked_out_here(audit, source, tmp_path):
    short = 2 * fork_branch_cost(source, 2) - 1
    request = choice(Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=2, budget_units=short)
    error = refused("GATE_BLOCKED", lambda: go(audit, source, tmp_path / "out", request=request))
    assert error.gate.failures == ("budget_confirmation_required",)


def test_a_snapshot_that_does_not_verify_blocks_at_the_gate(audit, source, tmp_path):
    snapshot = source / "snapshots" / "round-00002.db"
    os.chmod(snapshot, 0o644)
    conn = sqlite3.connect(snapshot)
    try:
        conn.execute("UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
        conn.commit()
    finally:
        conn.close()
    error = refused("GATE_BLOCKED", lambda: go(audit, source, tmp_path / "out"))
    assert error.gate.failures == ("snapshot_unavailable",)
    assert left(tmp_path / "out") == []


@pytest.mark.parametrize("option", [o for o in Option if o is not Option.FORK_FROM_EVENT])
def test_no_other_option_is_executed_or_reaches_the_gate(audit, source, tmp_path, option):
    request = choice(option, view(audit).evidence_hash, event_round=2)
    before = len(events(audit))
    refused("OPTION_NOT_EXECUTABLE", lambda: go(audit, source, tmp_path / "out", request=request))
    assert len(events(audit)) == before


def _no_gate(audit, source, tmp_path, code, **kw):
    view(audit)
    before = len(events(audit))
    refused(code, lambda: go(audit, source, tmp_path / "out", **kw))
    assert len(events(audit)) == before


def test_a_study_state_for_another_round_is_refused(audit, source, tmp_path):
    _no_gate(audit, source, tmp_path, "STUDY_ROUND_MISMATCH", study=StudyState("s1", 4))


def test_an_event_in_the_last_round_has_nowhere_to_go(audit, source, tmp_path):
    request = choice(Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=5, budget_units=100_000)
    _no_gate(audit, source, tmp_path, "NO_ROUND_LEFT", request=request)


def test_a_source_with_later_added_events_is_refused(audit, source, tmp_path):
    conn = sqlite3.connect(source / "agora.db")
    with conn:
        conn.execute("INSERT INTO injected (round, event) VALUES (3, '{}')")
    conn.close()
    _no_gate(audit, source, tmp_path, "SOURCE_HAS_LATER_EVENTS")


def test_output_inside_the_source_is_refused(audit, source):
    view(audit)
    refused("OUTPUT_INSIDE_SOURCE", lambda: go(audit, source, source / "out"))
    assert not (source / "out").exists()


def test_an_unrecorded_parent_is_refused_before_the_gate(audit, source, tmp_path):
    _no_gate(audit, source, tmp_path, "PARENT_NOT_RECORDED", parent_result_ids=("ghost",))


def test_a_recorded_result_id_is_not_run_again(audit, source, tmp_path):
    done = go(audit, source, tmp_path / "out")
    before = files(done.path)
    count = len(events(audit))
    # A different output directory, so only the record can refuse it.
    refused("RESULT_ALREADY_RECORDED", lambda: go(audit, source, tmp_path / "other"))
    assert len(events(audit)) == count and files(done.path) == before


@pytest.mark.parametrize("suffix", ["", ".executing"])
def test_existing_output_is_refused_and_not_touched(audit, source, tmp_path, suffix):
    out = tmp_path / "out"
    final = ex._result_dir(out, "t1", "p1", "s1", "res1")
    taken = final.with_name(final.name + suffix)
    taken.mkdir(parents=True)
    (taken / "keep").write_text("mine")
    _no_gate(audit, source, tmp_path, "OUTPUT_EXISTS")
    assert (taken / "keep").read_text() == "mine" and left(out) == [taken.name]


@pytest.mark.parametrize("answer", [True, None, 0, "no"])
def test_only_exactly_false_lets_a_run_start(audit, source, tmp_path, answer):
    _no_gate(audit, source, tmp_path, "STOPPED_BY_KILL_SWITCH", kill_switch_on=lambda: answer)


@pytest.mark.parametrize("off_for", [1, 2, 6])
def test_a_kill_switch_during_the_run_releases_and_records_nothing(audit, source, tmp_path, off_for):
    answers = iter([False] * off_for)

    def probe():
        return next(answers, True)

    refused("STOPPED_BY_KILL_SWITCH", lambda: go(audit, source, tmp_path / "out", kill_switch_on=probe))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_kill_switch_after_the_last_round_still_stops_the_record(audit, source, tmp_path):
    out = tmp_path / "out"
    # Comes on only once both branches have finished and the manifest is written.
    refused("STOPPED_BY_KILL_SWITCH", lambda: go(
        audit, source, out, kill_switch_on=lambda: any(out.glob("*.executing/result.json"))))
    assert recorded(audit) is None and left(out) == []


def test_a_kill_switch_that_goes_off_again_still_releases_nothing(audit, source, tmp_path):
    # On for one poll only, in the middle of the first branch; the half-run branch must not be recorded.
    answers = iter([False, False, True])
    refused("STOPPED_BY_KILL_SWITCH", lambda: go(
        audit, source, tmp_path / "out", kill_switch_on=lambda: next(answers, False)))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_an_unreadable_kill_switch_stops_the_run(audit, source, tmp_path):
    def broken():
        raise OSError("unreadable")

    _no_gate(audit, source, tmp_path, "STOPPED_BY_KILL_SWITCH", kill_switch_on=broken)


def test_nothing_is_released_if_the_result_cannot_be_recorded(audit, source, tmp_path):
    refused("RUN:ITEM_NOT_REGISTERED",
            lambda: go(audit, source, tmp_path / "out", other_item_ids=("never-listed",)))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_nothing_is_released_if_the_stamps_cannot_be_read(audit, source, tmp_path, monkeypatch):
    def broken(**_kw):
        raise ex.ExecutionError("STAMPS_UNREADABLE")

    monkeypatch.setattr(ex, "run_result_stamps", broken)
    refused("STAMPS_UNREADABLE", lambda: go(audit, source, tmp_path / "out"))
    assert recorded(audit) is not None and left(tmp_path / "out") == []


def test_a_failing_branch_releases_nothing(audit, source, tmp_path, monkeypatch):
    real = ex._run_branch

    def second_fails(project, kill_switch_on):
        if project.name == ex.WITHOUT_EVENT:
            raise KeyboardInterrupt
        return real(project, kill_switch_on)

    monkeypatch.setattr(ex, "_run_branch", second_fails)
    with pytest.raises(KeyboardInterrupt):
        go(audit, source, tmp_path / "out")
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_parents_retraction_is_carried_into_the_fork(audit, source, tmp_path):
    go(audit, source, tmp_path / "out")
    done = go(audit, source, tmp_path / "out", result="res2", parent_result_ids=("res1",))
    assert done.basis.parent_result_ids == ("res1",)


def test_an_unrecorded_result_is_not_read(audit, tmp_path):
    refused("RESULT_NOT_RECORDED", lambda: read(audit, tmp_path))


def test_a_changed_manifest_is_not_shown(audit, source, tmp_path):
    done = go(audit, source, tmp_path / "out")
    manifest = done.path / ex.RESULT_FILE
    manifest.write_bytes(manifest.read_bytes().replace(b'"mock"', b'"live"'))
    refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))


@pytest.mark.parametrize("branch", [ex.WITH_EVENT, ex.WITHOUT_EVENT])
def test_a_changed_branch_database_is_not_shown(audit, source, tmp_path, branch):
    done = go(audit, source, tmp_path / "out")
    conn = sqlite3.connect(done.path / branch / "agora.db")
    with conn:
        conn.execute("UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
    conn.close()
    refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))


def test_missing_output_is_refused(audit, source, tmp_path):
    done = go(audit, source, tmp_path / "out")
    shutil.rmtree(done.path)
    refused("OUTPUT_MISSING", lambda: read(audit, tmp_path / "out"))


def test_a_change_left_in_the_write_ahead_log_is_not_hidden(audit, source, tmp_path):
    done = go(audit, source, tmp_path / "out")
    writer = sqlite3.connect(done.path / ex.WITH_EVENT / "agora.db")
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        with writer:
            writer.execute("UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
        # Still open, so the change has not been copied into the main database file.
        refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))
    finally:
        writer.close()

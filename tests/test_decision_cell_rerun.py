"""RERUN_FROM_START through the gate, run and recorded as one call. Synthetic data and the mock backend only."""
from __future__ import annotations

import json
import sqlite3

import pytest
import yaml

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    Option,
    StudyState,
    execute_rerun,
    read_continuation,
    read_event_fork,
    read_rerun,
    rerun_cost,
)
from agora.decision_cell import executor as ex
from tests.test_decision_cell_evidence import PAIR, choice, view
from tests.test_decision_cell_executor import (  # noqa: F401
    STUDY, added_events, built_source, files, go, left, recorded, refused, source,
)
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401


def rerun(audit, source, out, result="res1", **kw):
    request = kw.pop("request", None)
    if request is None:
        request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=2,
                         budget_units=100_000)
    kw.setdefault("study", STUDY)
    kw.setdefault("kill_switch_on", lambda: False)
    return execute_rerun(OWNER, request, statements=(PAIR,), tenant_id="t1", project_id="p1",
                         result_id=result, source=source, out_dir=out, audit=audit, now=NOW, **kw)


def read(audit, out, result="res1"):
    return read_rerun(result_id=result, out_dir=out, audit=audit, **SCOPE)


def no_gate(audit, source, out, code, **kw):
    view(audit)
    before = len(events(audit))
    refused(code, lambda: rerun(audit, source, out, **kw))
    assert len(events(audit)) == before and recorded(audit) is None and left(out) == []


def sql(database, statement, args=()):
    conn = sqlite3.connect(database)
    try:
        with conn:
            conn.execute(statement, args)
    finally:
        conn.close()


def first_round_run(project):
    conn = sqlite3.connect(project / "agora.db")
    try:
        return conn.execute("SELECT MIN(round), MAX(round), COUNT(*) FROM rounds").fetchone()
    finally:
        conn.close()


def test_a_rerun_runs_every_round_in_a_new_project_and_leaves_the_source(audit, source, tmp_path):
    # A rerun needs no snapshot. Moved aside, not deleted: the files are read-only, which Windows will not delete.
    (source / "snapshots").rename(tmp_path / "snapshots-aside")
    before = files(source)
    done = rerun(audit, source, tmp_path / "out")
    assert files(source) == before
    branch = done.path / ex.RERUN
    assert first_round_run(branch) == (0, 5, 6)
    assert added_events(branch) == [(3, {"round": 3, "text": PAIR.statement_text, "type": "news"})]
    assert not (branch / "fork.json").exists()
    manifest = done.manifest
    assert manifest["schema"] == ex.RERUN_SCHEMA and set(manifest["branches"]) == {ex.RERUN}
    assert manifest["event_round"] == 2 and manifest["added_in_round"] == 3
    assert "continued_from_round" not in manifest
    assert manifest["llm_backend"] == "mock" and manifest["validated_prediction_enabled"] is False
    assert manifest["branches"][ex.RERUN]["graph_sha256"] is None
    assert done.basis == recorded(audit) and done.basis.item_ids == ("e1",) and done.stamps == ()
    gate = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    assert len(gate) == 1 and gate[0]["event_id"] == done.basis.gate_event_id
    assert rerun_cost(source) > 0 and manifest["cost_units"] == gate[0]["count"] == rerun_cost(source)
    assert read(audit, tmp_path / "out") == done


def test_on_the_mock_backend_a_rerun_ends_where_the_fork_with_the_event_ends(audit, source, tmp_path):
    forked = go(audit, source, tmp_path / "forks", result="fork1")
    done = rerun(audit, source, tmp_path / "out")
    final = done.manifest["branches"][ex.RERUN]["final_state_digest"]
    assert final == forked.manifest["branches"][ex.WITH_EVENT]["final_state_digest"]
    assert final != forked.manifest["branches"][ex.WITHOUT_EVENT]["final_state_digest"]


def test_the_budget_is_the_whole_run(audit, source, tmp_path):
    # Six rounds of every agent, whatever the event round.
    conn = sqlite3.connect(source / "agora.db")
    agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    conn.close()
    assert rerun_cost(source) == 6 * agents
    request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=2,
                     budget_units=6 * agents - 1)
    error = refused("GATE_BLOCKED", lambda: rerun(audit, source, tmp_path / "out", request=request))
    assert error.gate.failures == ("budget_confirmation_required",)
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_confirmed_amount_over_budget_runs(audit, source, tmp_path):
    cost = rerun_cost(source)
    request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=2, budget_units=1,
                     confirmed_cost_units=cost)
    assert rerun(audit, source, tmp_path / "out", request=request).manifest["cost_units"] == cost


@pytest.mark.parametrize("event_round", [None, -1, True, 1.0])
def test_a_rerun_needs_the_event_round(audit, source, tmp_path, event_round):
    request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=event_round)
    no_gate(audit, source, tmp_path / "out", "INPUT_INVALID", request=request)


def test_an_event_round_the_study_has_not_reached_is_refused(audit, source, tmp_path):
    sql(source / "agora.db", "DELETE FROM rounds WHERE round > 3")
    request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=4)
    no_gate(audit, source, tmp_path / "out", "EVENT_ROUND_NOT_REACHED", request=request,
            study=StudyState("s1", 3))


def test_an_event_in_the_last_round_has_nowhere_to_go(audit, source, tmp_path):
    request = choice(Option.RERUN_FROM_START, view(audit).evidence_hash, event_round=5)
    no_gate(audit, source, tmp_path / "out", "NO_ROUND_LEFT", request=request)


@pytest.mark.parametrize("at", [0, 3, 5])
def test_a_source_with_any_added_event_is_refused(audit, source, tmp_path, at):
    sql(source / "agora.db", "INSERT INTO injected (round, event) VALUES (?, '{}')", (at,))
    no_gate(audit, source, tmp_path / "out", "SOURCE_HAS_ADDED_EVENTS")


def test_a_governed_source_is_refused(audit, source, tmp_path):
    sql(source / "agora.db", "INSERT INTO meta (key, value) VALUES ('input_provenance', '{}')")
    no_gate(audit, source, tmp_path / "out", "SOURCE_GOVERNED")


def test_a_changed_scenario_is_refused(audit, source, tmp_path):
    scenario = source / "scenario.yaml"
    text = scenario.read_text(encoding="utf-8")
    assert "crowd_agents: 20" in text
    scenario.write_text(text.replace("crowd_agents: 20", "crowd_agents: 21"), encoding="utf-8")
    no_gate(audit, source, tmp_path / "out", "SOURCE_SCENARIO_CHANGED")


def test_a_source_that_records_no_starting_scenario_is_refused(audit, source, tmp_path):
    sql(source / "agora.db", "DELETE FROM meta WHERE key = 'scenario_hash'")
    no_gate(audit, source, tmp_path / "out", "SOURCE_SCENARIO_CHANGED")


def test_a_scenario_that_names_a_live_backend_is_refused_before_the_gate(audit, source, tmp_path):
    scenario = source / "scenario.yaml"
    data = yaml.safe_load(scenario.read_text(encoding="utf-8"))
    data["llm"] = {"backend": "ollama", "model": "none"}
    scenario.write_text(yaml.safe_dump(data), encoding="utf-8")
    # Recorded as the starting scenario, so only the backend check can refuse it.
    changed = ex.hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]
    sql(source / "agora.db", "UPDATE meta SET value = ? WHERE key = 'scenario_hash'", (json.dumps(changed),))
    no_gate(audit, source, tmp_path / "out", "BACKEND_NOT_DETERMINISTIC")


def test_a_scenario_changed_after_the_gate_releases_nothing(audit, source, tmp_path, monkeypatch):
    out = tmp_path / "out"
    real = ex.request_labelled_option

    def then_change(*args, **kwargs):
        decided = real(*args, **kwargs)
        scenario = source / "scenario.yaml"
        text = scenario.read_text(encoding="utf-8")
        scenario.write_text(text.replace("crowd_agents: 20", "crowd_agents: 21"), encoding="utf-8")
        return decided

    monkeypatch.setattr(ex, "request_labelled_option", then_change)
    refused("SOURCE_CHANGED", lambda: rerun(audit, source, out))
    assert recorded(audit) is None and left(out) == []


@pytest.mark.parametrize("option", [o for o in Option if o is not Option.RERUN_FROM_START])
def test_no_other_option_is_executed_or_reaches_the_gate(audit, source, tmp_path, option):
    request = choice(option, view(audit).evidence_hash, event_round=2)
    no_gate(audit, source, tmp_path / "out", "OPTION_NOT_EXECUTABLE", request=request)


@pytest.mark.parametrize("off_for", [1, 2, 6])
def test_a_kill_switch_during_the_rerun_releases_and_records_nothing(audit, source, tmp_path, off_for):
    answers = iter([False] * off_for)
    refused("STOPPED_BY_KILL_SWITCH", lambda: rerun(
        audit, source, tmp_path / "out", kill_switch_on=lambda: next(answers, True)))
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_later_retraction_stamps_the_rerun_when_read(audit, source, tmp_path):
    rerun(audit, source, tmp_path / "out")
    new_item(audit, "r1")
    link(audit)
    assert read(audit, tmp_path / "out").stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_a_rerun_is_not_read_as_another_kind(audit, source, tmp_path):
    rerun(audit, source, tmp_path / "out")
    for other in (read_event_fork, read_continuation):
        refused("WRONG_RESULT_KIND",
                lambda: other(result_id="res1", out_dir=tmp_path / "out", audit=audit, **SCOPE))
    go(audit, source, tmp_path / "forks", result="fork1")
    refused("WRONG_RESULT_KIND", lambda: read(audit, tmp_path / "forks", result="fork1"))


def test_a_changed_rerun_database_is_not_shown(audit, source, tmp_path):
    done = rerun(audit, source, tmp_path / "out")
    sql(done.path / ex.RERUN / "agora.db", "UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
    refused("OUTPUT_CHANGED", lambda: read(audit, tmp_path / "out"))


def test_the_sources_knowledge_graph_goes_with_the_rerun_and_is_hashed(audit, source, tmp_path):
    from agora.graph import GraphStore

    GraphStore(source / "graph.db").close()
    writer = sqlite3.connect(source / "graph.db")
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        with writer:
            writer.execute("CREATE TABLE marker (x TEXT)")
            writer.execute("INSERT INTO marker VALUES ('only in the log')")
        # Still open, so the marker is only in the write-ahead log.
        done = rerun(audit, source, tmp_path / "out")
    finally:
        writer.close()
    copied = sqlite3.connect(done.path / ex.RERUN / "graph.db")
    try:
        assert copied.execute("SELECT x FROM marker").fetchall() == [("only in the log",)]
    finally:
        copied.close()
    digest = done.manifest["branches"][ex.RERUN]["graph_sha256"]
    assert isinstance(digest, str) and len(digest) == 64

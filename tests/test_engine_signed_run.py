"""Simulation(signed_input=...): a run starts only on a single-use signed receipt for exactly what runs.

Test keys, the synthetic identity adapter, synthetic data and the mock model backend only.
"""
import copy
import json
import os

import pytest

from agora import scenario as scenario_mod
from agora.security import run_scope as rs
from agora.security import signed_receipt as sr
from agora.sim import engine
from agora.sim.engine import GovernedInputError, Simulation, SnapshotError
from conftest import make_project
from test_engine_governed_input import ACT, MAPPING, agent_count, gi, make_package, provenance_bytes
from test_receipt_gate import BASE, consumed, envelope_for, opened, paths, refused, settings, write
from test_receipt_run_scope import principal, signed

__all__ = ["paths"]  # fixture re-used from the gate tests


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture
def gate(tmp_path, paths):
    with opened(write(tmp_path, settings(paths))) as value:
        value.refresh_key_list(envelope_for())
        yield value


def signed_input(gate, project, nonce=0, **changes):
    """The input a worker would hand the engine, with a receipt signed over the project as it is now."""
    package, mapping = make_package(), copy.deepcopy(MAPPING)
    run = rs.describe_run(package=package, mapping=mapping, project_id=project.name, subject_id="op-1",
                          base_scenario=scenario_mod.load(project / "scenario.yaml"))
    return {"gate": gate, "envelope": signed(run, nonce), "principal": principal(), "package": package,
            "mapping": mapping, **changes}


def names(project):
    return sorted(p.name for p in project.iterdir())


def start(project, value, **kwargs):
    return Simulation(project, signed_input=value, **kwargs)


def refuse_before_admission(gate, project, value, match, **kwargs):
    """Refused, nothing written and the receipt not spent."""
    before = names(project)
    with pytest.raises(GovernedInputError, match=match):
        start(project, value, **kwargs)
    assert names(project) == before and consumed(gate) == 0


def test_a_signed_run_runs_what_was_admitted_and_records_the_admission(gate, project):
    value = signed_input(gate, project)
    sim = start(project, value)
    assert consumed(gate) == 1
    effective = rs.scenario_digest(sim.sc)  # what the engine is about to run, before it runs
    assert sim.run() == sim.sc.rounds
    assert sorted(s.name for s in sim.sc.segments) == sorted(MAPPING["personas"])
    stored = json.loads(provenance_bytes(project))["input_manifest"]
    record = stored["signed_admission"]
    assert record["purpose"] == "governed_run.v1" and record["release_attested"] is False
    assert record["subject"] == "op-1" and record["tenant"] == BASE["tenant"]
    assert record["release_id"] == BASE["release_id"]
    assert record["action"]["domain"] == rs.ACTION_DOMAIN
    assert record["action"]["effective_scenario_sha256"] == effective != record["action"]["base_scenario_sha256"]
    event = gate._audit.chain.db.execute(
        "SELECT event_id FROM audit_events WHERE event_id LIKE 'receipt-consume-%'").fetchone()[0]
    assert record["audit_event_id"] == event and record["receipt_sha256"].startswith("sha256:")
    assert stored["input_origin"] == "synthetic_demo" and agent_count(project) > 0


def test_changing_the_callers_objects_after_the_start_changes_nothing(gate, project):
    value = signed_input(gate, project)
    sim = start(project, value)
    value["package"]["instances"][0]["property_values"][ACT] += 0.3
    value["mapping"]["personas"]["senior_residents"] = "changed afterwards"
    sim.prepare()
    assert "changed afterwards" not in [s.persona for s in sim.sc.segments]


def _edit_scenario(project):
    path = project / "scenario.yaml"
    sc = scenario_mod.load(path)
    path.write_text(path.read_text(encoding="utf-8") + "\ncontext: edited after signing\n", encoding="utf-8")
    assert scenario_mod.load(path).context != sc.context


def _edit_rows(value):
    value["package"]["instances"][0]["property_values"][ACT] += 0.05


def _edit_mapping(value):
    value["mapping"]["personas"]["senior_residents"] = "another persona"


@pytest.mark.parametrize("change", ["scenario", "rows", "mapping"])
def test_a_receipt_for_different_inputs_admits_nothing_and_writes_nothing(gate, project, change):
    value = signed_input(gate, project)
    if change == "scenario":
        _edit_scenario(project)
    else:
        (_edit_rows if change == "rows" else _edit_mapping)(value)
    before = names(project)
    refused("SCOPE_MISMATCH", start, project, value)
    assert names(project) == before and consumed(gate) == 0


def test_a_spent_receipt_cannot_start_a_second_project(gate, tmp_path, project):
    value = signed_input(gate, project)
    start(project, value).run(rounds=1)
    twin = tmp_path / "again" / project.name
    twin.mkdir(parents=True)
    (twin / "scenario.yaml").write_bytes((project / "scenario.yaml").read_bytes())
    refused("REPLAY", start, twin, value)
    assert names(twin) == ["scenario.yaml"] and consumed(gate) == 1


# Written out, not read from the engine: dropping a name there must fail a test here.
UNBOUND = ["agora.db", "agora.db-wal", "agora.db-shm", "agora.db-journal", "llm_cache.db", "llm_cache.db-wal",
           "llm_cache.db-shm", "llm_cache.db-journal", "graph.db", "graph.db-wal", "graph.db-journal",
           "decisions.jsonl", "snapshots", "fork.json"]


def test_the_refused_names_are_the_expected_ones():
    assert sorted(engine._SIGNED_UNBOUND) == sorted(UNBOUND)


@pytest.mark.parametrize("name", UNBOUND)
def test_anything_the_receipt_does_not_name_is_refused_unspent(gate, project, name):
    value = signed_input(gate, project)
    (project / name).write_bytes(b"")
    refuse_before_admission(gate, project, value, "no earlier run")


def test_a_dangling_link_where_the_run_would_write_is_refused_unspent(gate, project, tmp_path):
    value = signed_input(gate, project)
    try:
        os.symlink(tmp_path / "elsewhere.db", project / "agora.db")
    except OSError:
        pytest.skip("symlinks are not available here")
    refuse_before_admission(gate, project, value, "no earlier run")
    assert not (tmp_path / "elsewhere.db").exists()


def test_a_model_override_is_refused_unspent(gate, project):
    refuse_before_admission(gate, project, signed_input(gate, project), "model override",
                            llm_override={"backend": "mock"})


def test_native_communication_is_refused_unspent(gate, project):
    path = project / "scenario.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\ncommunication: native\n", encoding="utf-8")
    refuse_before_admission(gate, project, signed_input(gate, project), "native communication")


def test_an_unusable_model_configuration_does_not_cost_a_receipt(gate, project, monkeypatch):
    value = signed_input(gate, project)

    def broken(cfg, cache_path=None):
        raise engine.LLMError("model cannot be built")

    monkeypatch.setattr(engine, "make_backend", broken)
    with pytest.raises(engine.LLMError):
        start(project, value)
    assert consumed(gate) == 0 and names(project) == ["scenario.yaml"]


@pytest.mark.parametrize("mutate, match", [
    (lambda v: v["package"].pop("synthetic_demo"), "not declared synthetic_demo"),
    (lambda v: v["package"].update(validated_prediction_enabled=True), "validated_prediction_enabled"),
    (lambda v: v["package"].update(instances=("not", "json")), "signed input refused"),
    (lambda v: v["package"].update(manifest=None), "manifest is incomplete"),
    (lambda v: v.pop("principal"), "exactly"),
    (lambda v: v.update(base_scenario="smuggled"), "exactly"),
])
def test_unacceptable_input_is_refused_unspent(gate, project, mutate, match):
    value = signed_input(gate, project)
    mutate(value)
    refuse_before_admission(gate, project, value, match)


def test_both_kinds_of_governed_input_at_once_are_refused(gate, project):
    refuse_before_admission(gate, project, signed_input(gate, project), "not both",
                            governed_input=gi(project_id=project.name))


def test_the_receipt_covers_one_run_call(gate, project):
    sim = start(project, signed_input(gate, project))
    assert sim.run(rounds=1) == 1
    with pytest.raises(GovernedInputError, match="one run call"):
        sim.run()
    assert sim.store.last_round() == 0


def test_preparing_a_begun_signed_run_again_is_refused(gate, project):
    sim = start(project, signed_input(gate, project))
    sim.prepare()
    with pytest.raises(GovernedInputError, match="cannot be resumed"):
        sim.prepare(force=True)


@pytest.mark.parametrize("how", ["signed", "in_process", "ungoverned"])
def test_a_begun_signed_run_cannot_be_resumed_by_any_route(gate, project, how):
    start(project, signed_input(gate, project)).run(rounds=1)
    stored = provenance_bytes(project)
    if how == "signed":
        with pytest.raises(GovernedInputError, match="no earlier run"):
            start(project, signed_input(gate, project, nonce=1))
        assert consumed(gate) == 1
    else:
        kwargs = {"governed_input": gi(project_id=project.name)} if how == "in_process" else {}
        with pytest.raises(GovernedInputError, match="does not match" if kwargs else "governed"):
            Simulation(project, **kwargs).run(force=True)
    assert provenance_bytes(project) == stored


def test_only_one_of_two_starts_that_both_pass_the_checks_runs(gate, project, monkeypatch):
    """The other start appears between the project check and the claim."""
    value = signed_input(gate, project)
    admit = rs.admit_governed_run

    def raced(*args, **kwargs):
        result = admit(*args, **kwargs)
        (project / "agora.db").write_bytes(b"other start")
        return result

    monkeypatch.setattr(rs, "admit_governed_run", raced)
    with pytest.raises(GovernedInputError, match="receipt is spent"):
        start(project, value)
    assert (project / "agora.db").read_bytes() == b"other start" and consumed(gate) == 1


def test_a_reply_cache_planted_during_admission_is_not_used(gate, project, monkeypatch):
    value = signed_input(gate, project)
    admit = rs.admit_governed_run

    def planted(*args, **kwargs):
        result = admit(*args, **kwargs)
        (project / "llm_cache.db").write_bytes(b"planted")
        return result

    monkeypatch.setattr(rs, "admit_governed_run", planted)
    with pytest.raises(GovernedInputError, match="llm_cache.db"):
        start(project, value)
    assert (project / "llm_cache.db").read_bytes() == b"planted"


def test_a_knowledge_graph_that_appears_after_the_check_is_not_read(gate, project, monkeypatch):
    value = signed_input(gate, project)
    admit = rs.admit_governed_run

    def planted(*args, **kwargs):
        result = admit(*args, **kwargs)
        (project / "graph.db").write_bytes(b"not even a database")
        return result

    monkeypatch.setattr(rs, "admit_governed_run", planted)
    sim = start(project, value)
    assert sim.facts is None


def test_an_event_added_during_a_signed_run_stops_it(gate, project):
    sim = start(project, signed_input(gate, project))
    sim.prepare()
    sim.store.db.execute("INSERT INTO injected (round, event) VALUES (?, ?)",
                         (1, json.dumps({"round": 1, "type": "news", "text": "added"})))
    sim.store.db.commit()
    with pytest.raises(GovernedInputError, match="added events"):
        sim.run()
    assert sim.store.last_round() == 0  # round 0 committed; nothing from the round with the added event


def test_a_signed_run_cannot_be_forked(gate, project, tmp_path):
    sim = start(project, signed_input(gate, project), snapshot_rounds=[0])
    sim.run(rounds=1)
    with pytest.raises(SnapshotError, match="governed"):
        Simulation.fork_from(project, 0, tmp_path / "fork")
    assert not (tmp_path / "fork").exists()

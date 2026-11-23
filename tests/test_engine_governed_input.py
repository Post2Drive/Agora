"""M3 slice 4.2: Simulation(governed_input=...) in agora/sim/engine.py (docs/M3_DESIGN.md sections 3 and 5).

Synthetic data and the mock LLM backend only: no model call, no network, no real data.
"""
from __future__ import annotations

import copy
import hashlib
import socket
import sqlite3

import pytest

from agora.scenario_inputs import recompute_scenario_hash
from agora.sim.engine import GovernedInputError, Simulation
from conftest import make_project

SEG, ACT = "x:segment", "x:activity"
NAMES = ["health_conscious_parents", "budget_homemakers", "young_professionals", "senior_residents"]
FIELDS = ["stance_mean", "stance_sd", "stubbornness", "activity", "influence", "openness"]
MAPPING = {"segment_property": SEG, "numeric": {f: ACT for f in FIELDS},
           "personas": {n: f"Synthetic persona {n}" for n in NAMES}}


def make_package(values=(0.2, 0.4, 0.5, 0.6), *, import_id="import-1"):
    rows = []
    for i, name in enumerate(NAMES):
        for k in range(2):
            rows.append({"row_id": f"{i}-{k}",
                         "property_values": {SEG: name, ACT: values[i] + 0.01 * k},
                         "property_sensitivity": {SEG: "public", ACT: "public"}})
    manifest = {"import_id": import_id, "snapshot_manifest_hash": "sha256:" + "11" * 32,
                "schema_fingerprint": "sha256:" + "22" * 32, "binding_fingerprint": "sha256:" + "33" * 32,
                "ontology_pack_fingerprint": "sha256:" + "44" * 32,
                "transformation_policy_fingerprint": None, "scenario_parameters": {}}
    manifest["scenario_hash"] = recompute_scenario_hash(manifest)
    return {"manifest": manifest, "scenario_hash": manifest["scenario_hash"], "instances": rows,
            "validated_prediction_enabled": False}


def gi(package=None, mapping=None):
    return {"package": package or make_package(), "mapping": mapping or copy.deepcopy(MAPPING)}


def provenance_bytes(project):
    if not (project / "agora.db").exists():
        return None
    db = sqlite3.connect(project / "agora.db")
    try:
        row = db.execute("SELECT value FROM meta WHERE key='input_provenance'").fetchone()
    except sqlite3.OperationalError:
        row = None
    db.close()
    return row[0] if row else None


def agent_count(project):
    if not (project / "agora.db").exists():
        return 0
    db = sqlite3.connect(project / "agora.db")
    try:
        n = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    db.close()
    return n


def prepare(project, governed):
    sim = Simulation(project, governed_input=governed)
    try:
        sim.prepare()
    finally:
        sim.close()


def test_governed_run_persists_envelope_and_uses_the_projected_segments(project):
    sim = Simulation(project, governed_input=gi())
    sim.prepare()
    sim.run(rounds=2)
    segments = {a.segment for a in sim.world.agents if a.kind != "account"}
    sim.close()
    assert segments <= set(NAMES)
    env = provenance_bytes(project)
    assert env and "projection_hash" in env and "base_scenario_hash" in env
    from agora.store import Store
    st = Store(project / "agora.db")
    prov = st.get_input_provenance()
    st.close()
    assert prov["provenance_status"] == "verified"
    assert prov["scenario_hash"] == make_package()["scenario_hash"]
    assert prov["input_manifest"]["projection"]["validated_prediction_enabled"] is False


def test_legacy_default_path_writes_no_provenance(project):
    sim = Simulation(project)
    sim.prepare()
    sim.close()
    assert provenance_bytes(project) is None


@pytest.mark.parametrize("mutate", [
    lambda g: g["package"]["manifest"].update(import_id="tampered"),            # manifest edited, hash stale
    lambda g: g["package"].update(scenario_hash="sha256:" + "00" * 32),         # package hash disagrees
    lambda g: g["package"].update(validated_prediction_enabled=True),
    lambda g: g.update(extra=1),                                               # unknown key
    lambda g: g["mapping"]["numeric"].pop("openness"),                         # projection refuses
])
def test_unverifiable_input_is_refused_before_any_store_write(project, mutate):
    g = gi()
    mutate(g)
    with pytest.raises(GovernedInputError):
        Simulation(project, governed_input=g)
    assert provenance_bytes(project) is None and agent_count(project) == 0


def test_crash_after_envelope_before_population_leaves_no_valid_run(project, monkeypatch):
    from agora.store import Store
    real = Store.write_population

    def boom(self, *a, **k):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(Store, "write_population", boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        prepare(project, gi())
    monkeypatch.setattr(Store, "write_population", real)
    assert provenance_bytes(project) is not None and agent_count(project) == 0  # envelope first, no population
    before = provenance_bytes(project)
    with pytest.raises(GovernedInputError):  # a different input cannot take over the stalled run
        prepare(project, gi(make_package(import_id="import-OTHER")))
    assert provenance_bytes(project) == before and agent_count(project) == 0
    prepare(project, gi())  # the identical input completes it
    assert agent_count(project) > 0 and provenance_bytes(project) == before


def test_identical_resume_is_accepted(project):
    prepare(project, gi())
    sim = Simulation(project, governed_input=gi())
    sim.prepare()
    sim.run(rounds=1)
    sim.close()


@pytest.mark.parametrize("change", ["package", "mapping", "scenario_yaml"])
def test_any_change_refuses_resume_even_with_force(project, change):
    prepare(project, gi())
    before = provenance_bytes(project)
    g = gi()
    if change == "package":
        g = gi(make_package(values=(0.3, 0.4, 0.5, 0.6)))
    elif change == "mapping":
        g["mapping"]["personas"][NAMES[0]] = "Changed persona"
    else:
        p = project / "scenario.yaml"
        p.write_text(p.read_text(encoding="utf-8").replace("seed:", "seed: 999 #", 1), encoding="utf-8")
    sim = Simulation(project, governed_input=g)
    try:
        with pytest.raises(GovernedInputError):
            sim.prepare(force=True)  # force must not bypass the envelope check
        with pytest.raises(GovernedInputError):
            sim.run(force=True)
    finally:
        sim.close()
    assert provenance_bytes(project) == before  # original envelope byte-identical


def test_legacy_run_is_not_silently_upgraded(project):
    sim = Simulation(project)
    sim.prepare()
    sim.close()
    with pytest.raises(GovernedInputError):
        prepare(project, gi())
    assert provenance_bytes(project) is None


def test_governed_run_cannot_be_resumed_without_its_governed_input(project):
    prepare(project, gi())
    for force in (False, True):
        sim = Simulation(project)
        try:
            with pytest.raises(GovernedInputError):
                sim.prepare(force=force)
        finally:
            sim.close()


def test_governed_run_opens_no_network_and_keeps_prediction_disabled(project, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket.socket, "connect", deny)
    sim = Simulation(project, governed_input=gi())
    sim.prepare()
    sim.run(rounds=1)
    sim.close()
    from agora.report import writer
    assert writer.VALIDATED_PREDICTION_ENABLED is False


@pytest.fixture()
def project(tmp_path):
    return make_project(tmp_path)

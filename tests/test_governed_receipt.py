"""M3 slice 4.7: Principal-bound authorization receipt (agora/principal.py, scenario_inputs.py, sim/engine.py).

Synthetic data only. Every refusal must leave no store, no provenance and no population behind."""
from __future__ import annotations

import copy
import pickle
from datetime import datetime, timedelta, timezone

import pytest

import agora.principal as principal_mod
from agora.principal import (AuthorizationReceipt, IdentityError, SyntheticFixtureAdapter, mint_simulation_receipt,
                             principal_policy, verify_simulation_receipt)
from agora.scenario_inputs import ScenarioInputError, build_scenario_input, manifest_hash, recompute_scenario_hash
from agora.sim.engine import GovernedInputError, Simulation
from conftest import make_project
from test_engine_governed_input import agent_count, gi, make_package, mint, provenance_bytes
from test_scenario_inputs import _binding, _import, _pack, _policy


@pytest.fixture()
def project(tmp_path):
    return make_project(tmp_path)


def _later():
    class _Meta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, datetime)

    class Later(metaclass=_Meta):
        @staticmethod
        def now(tz=None):
            return datetime.now(tz) + timedelta(minutes=5)

    return Later


def untouched(project):
    return provenance_bytes(project) is None and agent_count(project) == 0 and not (project / "agora.db").exists()


def refused(project, governed, match="authorization|governed_input"):
    with pytest.raises(GovernedInputError, match=match):
        Simulation(project, governed_input=governed)
    assert untouched(project)


def test_control_genuine_receipt_runs(project):
    sim = Simulation(project, governed_input=gi())
    sim.prepare()
    sim.close()
    assert agent_count(project) > 0


@pytest.mark.parametrize("bad", [None, {}, {"issuer": "synthetic-fixture-issuer"}, "receipt", 1])
def test_missing_or_plain_values_are_not_receipts(project, bad):
    g = gi()
    g["receipt"] = bad
    refused(project, g)


def test_envelope_without_receipt_key_refused(project):
    g = gi()
    del g["receipt"]
    refused(project, g, "exactly")


def test_plain_mapping_copy_of_genuine_receipt_refused(project):
    r = mint(make_package())
    g = gi()
    g["receipt"] = {k: getattr(r, k) for k in r.__slots__ if k != "_token"}
    refused(project, g)


def test_receipt_cannot_be_constructed_copied_or_pickled(project):
    r = mint(make_package())
    with pytest.raises(IdentityError):
        AuthorizationReceipt(object(), issuer="synthetic-fixture-issuer", subject_id="x", role="operator",
                             expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc), project_id="proj",
                             import_id="import-1", binding_id="binding-1", manifest_hash="m", scenario_hash="s")
    for fn in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError):
            fn(r)
    with pytest.raises(AttributeError):
        r.project_id = "other"


def test_subclass_of_receipt_refused(project):
    r = mint(make_package())
    sub = type("Fake", (AuthorizationReceipt,), {"__slots__": ()})
    fake = sub.__new__(sub)
    for name in r.__slots__:
        object.__setattr__(fake, name, getattr(r, name))
    g = gi()
    g["receipt"] = fake
    refused(project, g)


def test_wrong_project_refused(project):
    refused(project, gi(receipt=mint(make_package(), project_id="other-project",
                                     fixture={"project_ids": ["proj", "other-project"]})))


def test_wrong_import_refused(project):
    refused(project, gi(package=make_package(import_id="import-1"), receipt=mint(make_package(import_id="import-2"))))


def test_wrong_binding_refused(project):
    p = make_package()
    other = copy.deepcopy(p)
    other["manifest"]["binding_id"] = "binding-OTHER"
    refused(project, gi(package=p, receipt=mint(other)))


def test_package_changed_after_minting_refused(project):
    p = make_package()
    r = mint(p)
    p["manifest"]["created_at"] = "2026-01-01T00:00:00+00:00"  # outside scenario_hash payload, inside manifest hash
    refused(project, gi(package=p, receipt=r))


def test_different_scenario_hash_refused(project):
    a, b = make_package(), make_package()
    b["manifest"]["scenario_parameters"] = {"x": 1}
    b["manifest"]["scenario_hash"] = b["scenario_hash"] = recompute_scenario_hash(b["manifest"])
    refused(project, gi(package=a, receipt=mint(b)))


def test_denied_principal_cannot_mint():
    p = make_package()
    for fixture in ({"roles": ["reader"]}, {"project_ids": ["elsewhere"]}):
        with pytest.raises(IdentityError):
            mint(p, fixture=fixture)


def test_untrusted_issuer_receipt_refused(project, monkeypatch):
    r = mint(make_package())
    object.__setattr__(r, "issuer", "attacker")
    refused(project, gi(receipt=r))


def test_expired_receipt_refused_at_start_and_on_resume(project, monkeypatch):
    p = make_package()
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    r = mint(p, fixture={"expires_at": soon})
    sim = Simulation(project, governed_input=gi(package=p, receipt=r))
    sim.prepare()
    sim.close()
    before = provenance_bytes(project)

    monkeypatch.setattr(principal_mod, "datetime", _later())
    with pytest.raises(GovernedInputError, match="expired"):
        Simulation(project, governed_input=gi(package=p, receipt=r))
    assert provenance_bytes(project) == before


def test_receipt_expiring_between_init_and_prepare_writes_nothing(project, monkeypatch):
    p = make_package()
    r = mint(p, fixture={"expires_at": datetime.now(timezone.utc) + timedelta(seconds=30)})
    sim = Simulation(project, governed_input=gi(package=p, receipt=r))

    monkeypatch.setattr(principal_mod, "datetime", _later())
    with pytest.raises(GovernedInputError, match="expired"):
        sim.prepare()
    assert provenance_bytes(project) is None and agent_count(project) == 0
    sim.close()


def test_verify_requires_full_scope():
    r = mint(make_package())
    with pytest.raises(IdentityError):
        verify_simulation_receipt(r, project_id="proj")


def test_lambda_policy_cannot_mint():
    with pytest.raises(IdentityError):
        mint_simulation_receipt(lambda op, res: {"decision": "allow"}, resource={"project_id": "proj", "import_id": "i", "binding_id": "b",
                                                      "source_sensitivity": "public"},
                                manifest_hash="m", scenario_hash="s")


def test_builder_mints_only_for_bound_policy(tmp_path):
    imported = _import(tmp_path)
    allow = lambda op, res: {"decision": "allow", "reason": "policy_allow", "subject_id": "o", "policy_version": "t",
                             "resource_ids": [imported["import_id"], "scenario.customer.v1"]}
    plain = build_scenario_input(_binding(), _pack(), tmp_path, imported["import_id"],
                                 transformation_policy=_policy(), policy=allow)
    assert "authorization_receipt" not in plain
    fx = {"op": {"subject_id": "op-1", "tenant_id": "t1", "project_ids": [tmp_path.name], "roles": ["operator"],
                 "assurance": "HIGH", "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc)}}
    bound = principal_policy(SyntheticFixtureAdapter(fx).issue("op"))
    built = build_scenario_input(_binding(), _pack(), tmp_path, imported["import_id"],
                                 transformation_policy=_policy(), policy=bound)
    rec = built["authorization_receipt"]
    assert type(rec) is AuthorizationReceipt and rec.import_id == imported["import_id"]
    assert rec.manifest_hash == manifest_hash(built["manifest"]) and rec.scenario_hash == built["scenario_hash"]
    denied = principal_policy(SyntheticFixtureAdapter({"r": {**fx["op"], "roles": ["reader"]}}).issue("r"))
    with pytest.raises(ScenarioInputError):
        build_scenario_input(_binding(), _pack(), tmp_path, imported["import_id"],
                             transformation_policy=_policy(), policy=denied)

"""Adapter provenance: a hand-built Principal in the trusted issuer namespace must not authorize or mint a receipt.
Synthetic data only. Residual (documented): in-process Python can reach module-private sentinels; real
separation needs the production adapter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agora.principal import (Assurance, IdentityError, Principal, SyntheticFixtureAdapter, decide_principal,
                             mint_simulation_receipt, principal_policy)
from conftest import make_project
from test_engine_governed_input import gi, make_package, mint, agent_count, provenance_bytes
from agora.sim.engine import GovernedInputError, Simulation

LATER = datetime.now(timezone.utc) + timedelta(days=1)


def forged():
    return Principal("attacker", "t1", frozenset({"proj"}), frozenset({"operator"}), Assurance.HIGH,
                     SyntheticFixtureAdapter.ISSUER, LATER)


def test_hand_built_principal_with_trusted_issuer_is_denied():
    d, role = decide_principal(forged(), "simulation_input", {"project_id": "proj"})
    assert d["decision"] == "deny" and d["reason"] == "principal_not_adapter_issued" and role is None


def test_hand_built_principal_cannot_mint_receipt():
    package = make_package()
    m = package["manifest"]
    res = {"project_id": "proj", "resource_ids": [m["import_id"], m["binding_id"]], "import_id": m["import_id"],
           "binding_id": m["binding_id"], "source_role": "scenario_input", "source_sensitivity": "public",
           "target_sensitivity": "public"}
    with pytest.raises(IdentityError, match="did not allow"):
        mint_simulation_receipt(principal_policy(forged()), resource=res, manifest_hash="a", scenario_hash="b")


def test_hand_built_origin_none_or_wrong_object_is_denied():
    for origin in (None, object(), "issued"):
        p = Principal("a", "t1", frozenset({"proj"}), frozenset({"operator"}), Assurance.HIGH,
                      SyntheticFixtureAdapter.ISSUER, LATER, origin)
        assert decide_principal(p, "simulation_input", {"project_id": "proj"})[0]["reason"] == \
            "principal_not_adapter_issued"


def test_adapter_issued_principal_still_works():
    package = make_package()
    assert mint(package) is not None


def test_engine_refuses_forged_principal_receipt_path_leaves_no_write(tmp_path):
    project = make_project(tmp_path)
    package = make_package()
    m = package["manifest"]
    res = {"project_id": "proj", "resource_ids": [m["import_id"], m["binding_id"]], "import_id": m["import_id"],
           "binding_id": m["binding_id"], "source_role": "scenario_input", "source_sensitivity": "public",
           "target_sensitivity": "public"}
    with pytest.raises(IdentityError):
        mint_simulation_receipt(principal_policy(forged()), resource=res, manifest_hash="a", scenario_hash="b")
    with pytest.raises(GovernedInputError):
        g = gi(package=package)
        g["receipt"] = None
        Simulation(project, governed_input=g)
    assert provenance_bytes(project) is None and agent_count(project) == 0 and not (project / "agora.db").exists()

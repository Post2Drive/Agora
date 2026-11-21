from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

from agora.ontology import parse_domain_pack
from agora.audit_chain import AuditChainStore
from agora.ontology.binding import load_binding
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import ingest_csv


def _pack():
    return parse_domain_pack({
        "pack_id": "scenario-pack", "schema_version": "1.0.0",
        "object_types": [{"type_id": "scenario:Customer", "version": "1.0.0", "name": "Customer",
                          "description": "Synthetic customer", "properties": ["scenario:Customer.id", "scenario:Customer.email"],
                          "identity_strategy": "record_key"}],
        "property_types": [
            {"property_id": "scenario:Customer.id", "version": "1.0.0", "name": "ID", "data_type": "identifier", "required": True, "nullable": False, "sensitivity": "personal"},
            {"property_id": "scenario:Customer.email", "version": "1.0.0", "name": "Email", "data_type": "string", "required": True, "nullable": False, "sensitivity": "sensitive"},
        ],
        "link_types": [], "action_types": [],
    })


def _schema(version="1.0.0"):
    return {"schema_id": "scenario-customers", "schema_version": version, "dataset_name": "scenario_customers", "columns": [
        {"name": "customer_id", "type": "string", "nullable": False, "primary_key": True, "sensitivity": "personal", "purpose": "synthetic identity", "retention": "one day"},
        {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
    ]}


def _binding(version="1.0.0", binding_id="scenario.customer.v1"):
    return load_binding({"binding_id": binding_id, "binding_version": version, "object_type_id": "scenario:Customer", "object_type_version": "1.0.0",
                         "dataset_id": "scenario_customers", "schema_id": "scenario-customers", "schema_version": version,
                         "column_map": {"customer_id": "scenario:Customer.id", "email": "scenario:Customer.email"},
                         "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
                         "property_sensitivity": {"scenario:Customer.id": "personal", "scenario:Customer.email": "sensitive"}})


def _import(tmp_path, schema=None, content="C001,synthetic@example.test\n", data_role="context"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "customers.csv"
    source.write_text("customer_id,email\n" + content, encoding="utf-8")
    return ingest_csv(tmp_path, source, schema or _schema(), data_role=data_role)


def _policy():
    return {"policy_id": "test-transform-v1", "purpose": "synthetic test transformation", "retention": "one day",
            "reviewer": "governance-test", "approved_at": "2026-11-21T00:00:00Z", "audit_reference": "AUD-001",
            "permitted_sensitivities": ["personal", "sensitive"],
            "authorized_property_ids": ["scenario:Customer.id"]}


def test_explicit_import_id_required_and_latest_rejected(tmp_path):
    with pytest.raises(ScenarioInputError):
        build_scenario_input(_binding(), _pack(), tmp_path, "latest")
    with pytest.raises(ScenarioInputError):
        build_scenario_input(_binding(), _pack(), tmp_path, "")


def test_same_snapshot_and_binding_have_same_hash(tmp_path):
    result = _import(tmp_path)
    left = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    right = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert left["scenario_hash"] == right["scenario_hash"]


def test_different_snapshot_manifest_changes_hash(tmp_path):
    first = _import(tmp_path)
    source = tmp_path / "customers.csv"
    source.write_text("customer_id,email\nC001,changed@example.test\n", encoding="utf-8")
    second = ingest_csv(tmp_path, source, _schema(), data_role="scenario_input")
    left = build_scenario_input(_binding(), _pack(), tmp_path, first["import_id"], transformation_policy=_policy())
    right = build_scenario_input(_binding(), _pack(), tmp_path, second["import_id"], transformation_policy=_policy())
    assert left["scenario_hash"] != right["scenario_hash"]


def test_binding_fingerprint_change_changes_hash(tmp_path):
    result = _import(tmp_path)
    left = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    changed = _binding(binding_id="scenario.customer.v2")
    right = build_scenario_input(changed, _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert left["scenario_hash"] != right["scenario_hash"]


def test_sealed_holdout_is_rejected(tmp_path):
    result = _import(tmp_path, schema=_schema())
    source = tmp_path / "holdout.csv"
    source.write_text("customer_id,email\nC002,holdout@example.test\n", encoding="utf-8")
    holdout = ingest_csv(tmp_path, source, _schema(), data_role="sealed_holdout")
    with pytest.raises(ScenarioInputError, match="sealed_holdout"):
        build_scenario_input(_binding(), _pack(), tmp_path, holdout["import_id"], transformation_policy=_policy())


def test_role_mismatch_fails_closed(tmp_path):
    result = _import(tmp_path)
    db = tmp_path / "data" / "tabular.sqlite3"
    import sqlite3, json
    conn = sqlite3.connect(db)
    manifest = json.loads(conn.execute("SELECT manifest_json FROM imports WHERE import_id=?", (result["import_id"],)).fetchone()[0])
    manifest["data_role"] = "unsupported"
    conn.execute("UPDATE imports SET manifest_json=? WHERE import_id=?", (json.dumps(manifest), result["import_id"]))
    conn.commit(); conn.close()
    with pytest.raises(ScenarioInputError, match="data role"):
        build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())


def test_sensitive_values_require_explicit_policy(tmp_path):
    result = _import(tmp_path)
    with pytest.raises(ScenarioInputError, match="transformation policy"):
        build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"])
    built = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert built["manifest"]["transformation_policy_fingerprint"].startswith("sha256:")
    assert built["instances"][0]["property_values"]["scenario:Customer.email"] == "[REDACTED]"
    assert built["manifest"]["redactions"]
    serialized = json.dumps(built, sort_keys=True)
    assert "synthetic@example.test" not in serialized
    assert "value_hash" not in serialized


def test_calibration_and_validation_roles_are_rejected(tmp_path):
    for role in ("calibration", "validation"):
        result = _import(tmp_path / role, data_role=role)
        with pytest.raises(ScenarioInputError, match="data role"):
            build_scenario_input(_binding(), _pack(), tmp_path / role, result["import_id"], transformation_policy=_policy())


def test_listed_sensitive_property_is_preserved(tmp_path):
    result = _import(tmp_path)
    policy = _policy() | {"authorized_property_ids": ["scenario:Customer.id", "scenario:Customer.email"]}
    built = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=policy)
    assert built["instances"][0]["property_values"]["scenario:Customer.email"] == "synthetic@example.test"
    assert built["manifest"]["redactions"] == []


def test_unknown_or_non_sensitive_authorized_property_is_rejected(tmp_path):
    result = _import(tmp_path)
    policy = _policy() | {"authorized_property_ids": ["scenario:Customer.unknown"]}
    with pytest.raises(ScenarioInputError, match="unknown property"):
        build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=policy)


def test_run_record_contains_exact_provenance(tmp_path):
    result = _import(tmp_path)
    built = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert built["run_record"]["import_id"] == result["import_id"]
    assert built["run_record"]["scenario_hash"] == built["scenario_hash"]
    assert built["run_record"]["input_manifest"]["snapshot_manifest_hash"]
    assert built["manifest"]["run_provenance_reference"].endswith(built["scenario_hash"])


def test_snapshot_database_is_byte_identical_after_construction(tmp_path):
    result = _import(tmp_path)
    db = tmp_path / "data" / "tabular.sqlite3"
    before = db.read_bytes()
    build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert db.read_bytes() == before


def test_validated_prediction_stays_disabled_and_no_sim_import(tmp_path):
    result = _import(tmp_path)
    built = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert built["validated_prediction_enabled"] is False
    assert "agora.sim" not in Path("agora/scenario_inputs.py").read_text(encoding="utf-8")


def test_hash_payload_contains_snapshot_manifest_hash(tmp_path):
    result = _import(tmp_path)
    built = build_scenario_input(_binding(), _pack(), tmp_path, result["import_id"], transformation_policy=_policy())
    assert built["manifest"]["snapshot_manifest_hash"].startswith("sha256:")



def test_policy_denial_is_audited_before_snapshot_database_is_read(tmp_path):
    def deny(operation, resource):
        assert operation == "simulation_input"
        assert resource["import_id"] == "exact-import-1"
        return {
            "decision": "deny", "reason": "scope_missing",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": ["exact-import-1", "scenario.customer.v1"],
        }

    with pytest.raises(ScenarioInputError, match="Policy denied"):
        build_scenario_input(
            _binding(), _pack(), tmp_path / "missing-project",
            "exact-import-1", transformation_policy=_policy(), policy=deny,
        )
    audit = AuditChainStore(
        tmp_path / "missing-project" / "data" / "audit_chain.sqlite3"
    )
    try:
        assert audit.verify()["valid"] is True
        event = json.loads(
            audit.db.execute("SELECT event_json FROM audit_events").fetchone()[0]
        )
        assert event["operation"] == "simulation_input"
        assert event["decision"] == "deny"
        assert event["reason"] == "scope_missing"
        assert event["resource_ids"] == ["exact-import-1", "scenario.customer.v1"]
    finally:
        audit.close()


def test_policy_allow_preserves_scenario_input_construction(tmp_path):
    imported = _import(tmp_path)
    seen = {}

    def allow(operation, resource):
        seen["operation"] = operation
        seen["resource"] = dict(resource)
        return {
            "decision": "allow", "reason": "policy_allow",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": [imported["import_id"], "scenario.customer.v1"],
        }

    built = build_scenario_input(
        _binding(), _pack(), tmp_path, imported["import_id"],
        transformation_policy=_policy(), policy=allow,
    )
    assert built["scenario_hash"]
    assert seen["operation"] == "simulation_input"
    assert seen["resource"]["import_id"] == imported["import_id"]

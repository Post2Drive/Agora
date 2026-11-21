import copy
import csv

import pytest

from agora.ontology import OntologyError, parse_domain_pack
from agora.audit_chain import AuditChainStore
from agora.ontology.binding import load_binding, materialize_instances, validate_binding
from agora.tabular import ingest_csv


def pack(domain="commerce"):
    participant = f"{domain}:Customer"
    pid = f"{participant}.id"
    pe = f"{participant}.email"
    return parse_domain_pack({
        "pack_id": f"{domain}-pack",
        "schema_version": "1.0.0",
        "object_types": [{
            "type_id": participant, "version": "1.0.0", "name": "Customer",
            "description": "Customer", "properties": [pid, pe],
            "identity_strategy": "record_key",
        }],
        "property_types": [
            {"property_id": pid, "version": "1.0.0", "name": "id", "data_type": "identifier", "required": True, "nullable": False, "sensitivity": "personal"},
            {"property_id": pe, "version": "1.0.0", "name": "email", "data_type": "string", "required": True, "nullable": False, "sensitivity": "sensitive"},
        ],
        "link_types": [], "action_types": [],
    })


def binding(domain="commerce"):
    participant = f"{domain}:Customer"
    return load_binding({
        "binding_id": f"{domain}.customer.v1", "binding_version": "1.0.0",
        "object_type_id": participant, "object_type_version": "1.0.0",
        "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
        "column_map": {"customer_id": f"{participant}.id", "email": f"{participant}.email"},
        "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
        "property_sensitivity": {f"{participant}.id": "personal", f"{participant}.email": "sensitive"},
    })


def schema():
    return {
        "schema_id": "customers-v1", "schema_version": "1.0.0", "dataset_name": "customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False, "primary_key": True, "sensitivity": "personal", "purpose": "account support", "retention": "90 days"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
        ],
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["customer_id", "email"])
        writer.writerows(rows)


def test_binding_validates_and_materializes_read_only_instances(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    result = ingest_csv(tmp_path, source, schema(), data_role="context")
    current = binding()
    manifest = copy.deepcopy(result["manifest"])
    assert validate_binding(pack(), manifest, current) is current
    instances = materialize_instances(current, pack(), tmp_path, result["import_id"])
    assert instances[0]["record_key"].startswith("agora-record-v1:")
    assert instances[0]["property_values"]["commerce:Customer.id"] == "C-1"
    assert instances[0]["source_registry_id"]
    assert instances[0]["file_sha256"]


def test_cross_snapshot_record_key_is_stable_but_row_id_changes(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    first = ingest_csv(tmp_path, source, schema(), data_role="context")
    source.write_text("customer_id,email\nC-1,updated@example.test\n", encoding="utf-8")
    second = ingest_csv(tmp_path, source, schema(), data_role="context")
    left = materialize_instances(binding(), pack(), tmp_path, first["import_id"])[0]
    right = materialize_instances(binding(), pack(), tmp_path, second["import_id"])[0]
    assert left["record_key"] == right["record_key"]
    assert left["row_id"] != right["row_id"]


def test_sensitivity_downgrade_is_rejected():
    manifest = {
        "import_id": "import-1", "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
        "schema_fingerprint": "sha256:x", "column_sensitivity": {"customer_id": "personal", "email": "sensitive"},
        "column_types": {"customer_id": "string", "email": "string"},
        "column_policies": {"customer_id": {"purpose": "support", "retention": "90 days"}},
    }
    downgraded = binding().as_dict()
    downgraded["property_sensitivity"]["commerce:Customer.id"] = "internal"
    with pytest.raises(OntologyError, match="downgrade"):
        validate_binding(pack(), manifest, downgraded)


def test_type_mismatch_is_rejected():
    manifest = {
        "import_id": "import-1", "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
        "schema_fingerprint": "sha256:x", "column_sensitivity": {"customer_id": "personal", "email": "sensitive"},
        "column_types": {"customer_id": "integer", "email": "string"},
        "column_policies": {"customer_id": {"purpose": "support", "retention": "90 days"}},
        "column_types": {"customer_id": "integer", "email": "string"},
    }
    with pytest.raises(OntologyError, match="type mismatch"):
        validate_binding(pack(), manifest, binding())


def test_unknown_binding_key_fails_closed():
    value = binding().as_dict()
    value["unknown"] = True
    with pytest.raises(OntologyError):
        load_binding(value)


def test_incomplete_column_map_fails_closed():
    value = binding().as_dict()
    value["column_map"].pop("email")
    with pytest.raises(OntologyError):
        validate_binding(pack(), {
            "import_id": "import-1", "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
            "schema_fingerprint": "sha256:x", "column_sensitivity": {"customer_id": "personal"},
            "column_types": {"customer_id": "string"},
            "column_policies": {"customer_id": {"purpose": "support", "retention": "90 days"}},
        }, value)


def test_materialization_rejects_wrong_pack_and_missing_type_info(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    result = ingest_csv(tmp_path, source, schema(), data_role="context")
    with pytest.raises(OntologyError, match="does not resolve"):
        materialize_instances(binding(), parse_domain_pack({
            "pack_id": "civic-pack", "schema_version": "1.0.0", "object_types": [],
            "property_types": [], "link_types": [], "action_types": [],
        }), tmp_path, result["import_id"])
    manifest = result["manifest"].copy()
    manifest.pop("column_types")
    with pytest.raises(OntologyError, match="types"):
        validate_binding(pack(), manifest, binding())


def test_sealed_holdout_is_rejected_and_missing_db_is_not_created(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    result = ingest_csv(tmp_path, source, schema(), data_role="sealed_holdout")
    with pytest.raises(OntologyError, match="sealed_holdout"):
        materialize_instances(binding(), pack(), tmp_path, result["import_id"])
    missing = tmp_path / "absent"
    with pytest.raises(OntologyError, match="database"):
        materialize_instances(binding(), pack(), missing, "missing")
    assert not missing.exists()


def test_materialization_is_read_only_and_civic_pack_works(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    result = ingest_csv(tmp_path, source, schema(), data_role="context")
    database = tmp_path / "data" / "tabular.sqlite3"
    before = database.read_bytes()
    instances = materialize_instances(binding("civic"), pack("civic"), tmp_path, result["import_id"])
    assert instances[0]["property_sensitivity"]["civic:Customer.id"] == "personal"
    assert database.read_bytes() == before



def test_policy_denial_is_audited_before_snapshot_database_is_read(tmp_path):
    def deny(operation, resource):
        assert operation == "binding"
        assert resource["binding_id"] == "commerce.customer.v1"
        return {
            "decision": "deny", "reason": "cross_scope",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": ["commerce.customer.v1", "customers"],
        }

    with pytest.raises(OntologyError, match="Policy denied"):
        materialize_instances(binding(), pack(), tmp_path / "missing-project",
                              "missing-import", policy=deny)
    audit = AuditChainStore(
        tmp_path / "missing-project" / "data" / "audit_chain.sqlite3"
    )
    try:
        assert audit.verify()["valid"] is True
        event = audit.db.execute("SELECT event_json FROM audit_events").fetchone()[0]
        import json
        payload = json.loads(event)
        assert payload["operation"] == "binding"
        assert payload["decision"] == "deny"
        assert payload["reason"] == "cross_scope"
        assert payload["resource_ids"] == ["commerce.customer.v1", "customers"]
    finally:
        audit.close()


def test_policy_allow_preserves_read_only_materialization(tmp_path):
    source = tmp_path / "customers.csv"
    write_csv(source, [["C-1", "one@example.test"]])
    imported = ingest_csv(tmp_path, source, schema(), data_role="context")
    seen = {}

    def allow(operation, resource):
        seen["operation"] = operation
        seen["resource"] = dict(resource)
        return {
            "decision": "allow", "reason": "policy_allow",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": ["commerce.customer.v1", "customers"],
        }

    instances = materialize_instances(binding(), pack(), tmp_path,
                                      imported["import_id"], policy=allow)
    assert len(instances) == 1
    assert seen["operation"] == "binding"
    assert seen["resource"]["dataset_id"] == "customers"


def test_binding_policy_receives_declared_purpose_and_retention(tmp_path):
    seen = {}

    def spy(operation, resource):
        seen.update(resource)
        return {"decision": "allow", "reason": "policy_allow", "subject_id": "u", "policy_version": "t"}

    source = tmp_path / "customers.csv"
    source.write_text("customer_id,email\nC001,a@example.test\n", encoding="utf-8")
    imported = ingest_csv(tmp_path, source, schema(), data_role="context")
    materialize_instances(
        binding(), pack(), tmp_path, imported["import_id"], policy=spy,
        purpose="declared purpose", retention="declared retention",
    )
    assert seen["purpose"] == "declared purpose" and seen["retention"] == "declared retention"
    seen.clear()
    materialize_instances(binding(), pack(), tmp_path, imported["import_id"], policy=spy)
    assert seen["purpose"] is None and seen["retention"] is None

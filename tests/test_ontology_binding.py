import copy
import csv

import pytest

from agora.ontology import OntologyError, parse_domain_pack
from agora.ontology.binding import load_binding, materialize_instances, validate_binding
from agora.tabular import ingest_csv


def pack():
    return parse_domain_pack({
        "pack_id": "commerce-pack",
        "schema_version": "1.0.0",
        "object_types": [{
            "type_id": "commerce:Customer", "version": "1.0.0", "name": "Customer",
            "description": "Customer", "properties": ["commerce:Customer.id", "commerce:Customer.email"],
            "identity_strategy": "record_key",
        }],
        "property_types": [
            {"property_id": "commerce:Customer.id", "version": "1.0.0", "name": "id", "data_type": "identifier", "required": True, "nullable": False, "sensitivity": "personal"},
            {"property_id": "commerce:Customer.email", "version": "1.0.0", "name": "email", "data_type": "string", "required": True, "nullable": False, "sensitivity": "sensitive"},
        ],
        "link_types": [], "action_types": [],
    })


def binding():
    return load_binding({
        "binding_id": "commerce.customer.v1", "binding_version": "1.0.0",
        "object_type_id": "commerce:Customer", "object_type_version": "1.0.0",
        "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
        "column_map": {"customer_id": "commerce:Customer.id", "email": "commerce:Customer.email"},
        "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
        "property_sensitivity": {"commerce:Customer.id": "personal", "commerce:Customer.email": "sensitive"},
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
    manifest["column_types"] = {"customer_id": "string", "email": "string"}
    assert validate_binding(pack(), manifest, current) is current
    instances = materialize_instances(current, tmp_path, result["import_id"])
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
    left = materialize_instances(binding(), tmp_path, first["import_id"])[0]
    right = materialize_instances(binding(), tmp_path, second["import_id"])[0]
    assert left["record_key"] == right["record_key"]
    assert left["row_id"] != right["row_id"]


def test_sensitivity_downgrade_is_rejected():
    manifest = {
        "import_id": "import-1", "dataset_id": "customers", "schema_id": "customers-v1", "schema_version": "1.0.0",
        "schema_fingerprint": "sha256:x", "column_sensitivity": {"customer_id": "personal", "email": "sensitive"},
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
            "column_policies": {"customer_id": {"purpose": "support", "retention": "90 days"}},
        }, value)

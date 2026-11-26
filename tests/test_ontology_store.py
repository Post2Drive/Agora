"""Focused tests for the ontology object-store backup and dependency manifest."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil
from pathlib import Path

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, load_binding, parse_domain_pack
from agora.tabular import ingest_csv


def _pack():
    return parse_domain_pack({
        "pack_id": "backup-test-pack",
        "schema_version": "1.0.0",
        "object_types": [{
            "type_id": "backup:Customer",
            "version": "1.0.0",
            "name": "Customer",
            "description": "Customer",
            "properties": ["backup:Customer.id", "backup:Customer.email"],
            "identity_strategy": "record_key",
        }],
        "property_types": [
            {
                "property_id": "backup:Customer.id",
                "version": "1.0.0",
                "name": "id",
                "data_type": "identifier",
                "required": True,
                "nullable": False,
                "sensitivity": "personal",
            },
            {
                "property_id": "backup:Customer.email",
                "version": "1.0.0",
                "name": "email",
                "data_type": "string",
                "required": True,
                "nullable": False,
                "sensitivity": "sensitive",
            },
        ],
        "link_types": [],
        "action_types": [],
    })


def _binding():
    return load_binding({
        "binding_id": "backup.customer.v1",
        "binding_version": "1.0.0",
        "object_type_id": "backup:Customer",
        "object_type_version": "1.0.0",
        "dataset_id": "customers",
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "column_map": {
            "customer_id": "backup:Customer.id",
            "email": "backup:Customer.email",
        },
        "identity": {
            "strategy": "record_key",
            "primary_key_column": "customer_id",
        },
        "property_sensitivity": {
            "backup:Customer.id": "personal",
            "backup:Customer.email": "sensitive",
        },
    })


def _allow(operation, resource):
    return {
        "decision": "allow",
        "reason": "policy_allow",
        "subject_id": "ontology-test-operator",
        "policy_version": "ontology-test-v1",
        "resource_ids": list(resource["resource_ids"]),
    }


@pytest.fixture
def catalog(tmp_path):
    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    audit = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    store = OntologyObjectStore(project)
    pack = _pack()
    pack_fingerprint = store.register_pack(pack, policy=_allow, audit=audit)
    binding = _binding()
    binding_fingerprint = store.register_binding(
        pack_fingerprint, binding, policy=_allow, audit=audit,
    )
    try:
        yield project, store, audit, pack_fingerprint, binding_fingerprint
    finally:
        audit.close()


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )


def test_backup_is_project_local_and_passes_integrity(catalog):
    project, store, _audit, _pack_fingerprint, _binding_fingerprint = catalog
    destination = project / "data" / "ontology.backup.sqlite3"

    result = store.backup(destination, policy=_allow, audit=_audit)

    assert result == destination
    assert destination.is_file()
    report = store.verify_integrity(policy=_allow, audit=_audit)
    assert report["ok"] is True
    assert report["sqlite_integrity"] == "ok"
    assert report["foreign_keys"] == "ok"
    assert report["schema_version"] == 3


def test_backup_refuses_existing_or_out_of_project_destination(catalog, tmp_path):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    existing = project / "data" / "existing.sqlite3"
    existing.write_bytes(b"do not overwrite")
    with pytest.raises(OntologyError, match="already exists"):
        store.backup(existing, policy=_allow, audit=audit)
    assert existing.read_bytes() == b"do not overwrite"

    with pytest.raises(OntologyError, match="backup failed"):
        store.backup(tmp_path / "outside.sqlite3", policy=_allow, audit=audit)
    assert not (tmp_path / "outside.sqlite3").exists()


def test_dependency_manifest_binds_exact_backup_and_catalog_fingerprints(catalog):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    manifest = store.backup_dependency_manifest(
        backup_path, policy=_allow, audit=audit,
    )

    backup_bytes = backup_path.read_bytes()
    assert manifest["format"] == "agora-ontology-backup-dependencies/v1"
    assert manifest["project_id"] == project.name
    assert manifest["ontology_backup"] == {
        "file_name": backup_path.name,
        "bytes": len(backup_bytes),
        "sha256": hashlib.sha256(backup_bytes).hexdigest(),
    }
    assert manifest["packs"] == [{
        "fingerprint": pack_fingerprint,
        "pack_id": "backup-test-pack",
        "schema_version": "1.0.0",
    }]
    assert manifest["bindings"] == [{
        "pack_fingerprint": pack_fingerprint,
        "fingerprint": binding_fingerprint,
        "binding_id": "backup.customer.v1",
        "binding_version": "1.0.0",
    }]
    assert manifest["source_snapshot_files"] == []
    assert manifest["source_row_values_included"] is False
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    assert manifest["manifest_sha256"] == hashlib.sha256(_canonical(unsigned).encode()).hexdigest()


def test_dependency_manifest_rejects_corrupt_backup_metadata(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    conn = sqlite3.connect(backup_path)
    try:
        conn.execute("DROP TRIGGER ontology_packs_no_update")
        conn.execute("UPDATE ontology_packs SET content_json='not-json'")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(OntologyError):
        store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)


def test_dependency_manifest_requires_existing_project_local_backup(catalog, tmp_path):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog

    with pytest.raises(OntologyError, match="dependency manifest requires"):
        store.backup_dependency_manifest(
            project / "data" / "missing.sqlite3", policy=_allow, audit=audit,
        )
    with pytest.raises(OntologyError, match="unsafe or unavailable"):
        store.backup_dependency_manifest(
            tmp_path / "outside.sqlite3", policy=_allow, audit=audit,
        )


def test_dependency_manifest_records_exact_source_file_hash_without_row_values(catalog):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-SECRET-001,private-value@example.test\n",
        encoding="utf-8",
    )
    imported = ingest_csv(project, source, {
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "dataset_name": "customers",
        "columns": [
            {
                "name": "customer_id",
                "type": "string",
                "nullable": False,
                "primary_key": True,
                "sensitivity": "personal",
                "purpose": "account support",
                "retention": "90 days",
            },
            {
                "name": "email",
                "type": "string",
                "nullable": False,
                "sensitivity": "sensitive",
            },
        ],
    }, data_role="context", policy=_allow, audit=audit)
    assert store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    ) == 1

    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    manifest = store.backup_dependency_manifest(
        backup_path, policy=_allow, audit=audit,
    )

    assert len(manifest["source_snapshot_files"]) == 1
    dependency = manifest["source_snapshot_files"][0]
    assert dependency["import_id"] == imported["import_id"]
    assert dependency["dataset_id"] == "customers"
    assert dependency["schema_id"] == "customers-v1"
    assert dependency["schema_version"] == "1.0.0"
    assert dependency["source_registry_id"]
    assert len(dependency["file_sha256"]) == 64
    serialized = _canonical(manifest)
    assert "C-SECRET-001" not in serialized
    assert "private-value@example.test" not in serialized



def test_restore_publishes_verified_backup_into_empty_project(catalog, tmp_path):
    project, store, audit, pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    restored_project = tmp_path / "restored" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        result = restored_store.restore(
            restored_backup, policy=_allow, audit=restored_audit,
        )
        assert result == restored_project / "data" / "ontology.sqlite3"
        report = restored_store.verify_integrity(policy=_allow, audit=restored_audit)
        assert report["ok"] is True
        assert restored_store.get_pack(
            pack_fingerprint, policy=_allow, audit=restored_audit,
        ).pack_id == "backup-test-pack"
    finally:
        restored_audit.close()



def test_restore_requires_exact_source_snapshot_database(catalog, tmp_path):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-SECRET-001,private-value@example.test\n",
        encoding="utf-8",
    )
    imported = ingest_csv(project, source, {
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "dataset_name": "customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False,
             "primary_key": True, "sensitivity": "personal", "purpose": "account support",
             "retention": "90 days"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
        ],
    }, data_role="context", policy=_allow, audit=audit)
    assert store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    ) == 1
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    restored_project = tmp_path / "missing-source" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError, match="tabular source snapshot"):
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
    finally:
        restored_audit.close()



def test_restore_rejects_changed_source_import_hash(catalog, tmp_path):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-SECRET-001,private-value@example.test\n",
        encoding="utf-8",
    )
    imported = ingest_csv(project, source, {
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "dataset_name": "customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False,
             "primary_key": True, "sensitivity": "personal", "purpose": "account support",
             "retention": "90 days"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
        ],
    }, data_role="context", policy=_allow, audit=audit)
    assert store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    ) == 1
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    restored_project = tmp_path / "changed-source" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    tabular_copy = restored_data / "tabular.sqlite3"
    shutil.copyfile(project / "data" / "tabular.sqlite3", tabular_copy)
    changed = sqlite3.connect(tabular_copy)
    try:
        changed.execute(
            "UPDATE imports SET file_sha256=? WHERE import_id=?",
            ("0" * 64, imported["import_id"]),
        )
        changed.commit()
    finally:
        changed.close()
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError, match="does not match its stored provenance"):
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
    finally:
        restored_audit.close()


def test_restore_accepts_matching_source_snapshot_database(catalog, tmp_path):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-SECRET-001,private-value@example.test\n",
        encoding="utf-8",
    )
    imported = ingest_csv(project, source, {
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "dataset_name": "customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False,
             "primary_key": True, "sensitivity": "personal", "purpose": "account support",
             "retention": "90 days"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
        ],
    }, data_role="context", policy=_allow, audit=audit)
    assert store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    ) == 1
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    restored_project = tmp_path / "matching-source" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    shutil.copyfile(project / "data" / "tabular.sqlite3", restored_data / "tabular.sqlite3")
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert restored_store.verify_integrity(policy=_allow, audit=restored_audit)["ok"] is True
    finally:
        restored_audit.close()



def test_restore_rejects_changed_snapshot_row_locator(catalog, tmp_path):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-SECRET-001,private-value@example.test\n",
        encoding="utf-8",
    )
    imported = ingest_csv(project, source, {
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "dataset_name": "customers",
        "columns": [
            {"name": "customer_id", "type": "string", "nullable": False,
             "primary_key": True, "sensitivity": "personal", "purpose": "account support",
             "retention": "90 days"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
        ],
    }, data_role="context", policy=_allow, audit=audit)
    store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    )
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    restored_project = tmp_path / "changed-row-locator" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    tabular_copy = restored_data / "tabular.sqlite3"
    shutil.copyfile(project / "data" / "tabular.sqlite3", tabular_copy)
    changed = sqlite3.connect(tabular_copy)
    try:
        changed.execute(
            "UPDATE import_rows SET locator_json='{}' WHERE import_id=?",
            (imported["import_id"],),
        )
        changed.commit()
    finally:
        changed.close()
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError, match="row locator does not match"):
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
    finally:
        restored_audit.close()


def test_restore_refuses_existing_destination(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    with pytest.raises(OntologyError, match="destination already exists"):
        store.restore(backup_path, policy=_allow, audit=audit)



def test_restore_refuses_stale_sqlite_sidecars(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    original_database = store.path.read_bytes()
    sidecar = Path(str(store.path) + "-wal")
    sidecar.write_bytes(b"stale wal marker")

    with pytest.raises(OntologyError, match="SQLite sidecars"):
        store.restore(backup_path, policy=_allow, audit=audit)
    assert store.path.read_bytes() == original_database
    assert sidecar.read_bytes() == b"stale wal marker"


def test_restore_rejects_corrupt_backup_without_publishing(catalog):
    project, _store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    restored_project = project.parent / "restored-corrupt" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    corrupt_backup = restored_data / "corrupt.sqlite3"
    corrupt_backup.write_bytes(b"not a sqlite database")
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError):
            restored_store.restore(corrupt_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
    finally:
        restored_audit.close()


_SCHEMA = {
    "schema_id": "customers-v1",
    "schema_version": "1.0.0",
    "dataset_name": "customers",
    "columns": [
        {"name": "customer_id", "type": "string", "nullable": False,
         "primary_key": True, "sensitivity": "personal", "purpose": "account support",
         "retention": "90 days"},
        {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
    ],
}


def _materialized_backup(catalog, rows="customer_id,email\nC-SECRET-001,private-value@example.test\n"):
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    source = project / "customers.csv"
    source.write_text(rows, encoding="utf-8")
    imported = ingest_csv(project, source, _SCHEMA, data_role="context", policy=_allow, audit=audit)
    store.materialize_binding(
        pack_fingerprint, binding_fingerprint, imported["import_id"],
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    )
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    return imported["import_id"], backup_path


def _restore_with_tampered_snapshot(catalog, tmp_path, name, tamper, *, copy_snapshot=True):
    project = catalog[0]
    import_id, backup_path = _materialized_backup(catalog)
    restored_project = tmp_path / name / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    if copy_snapshot:
        tabular_copy = restored_data / "tabular.sqlite3"
        shutil.copyfile(project / "data" / "tabular.sqlite3", tabular_copy)
        connection = sqlite3.connect(tabular_copy)
        try:
            tamper(connection, import_id)
            connection.commit()
        finally:
            connection.close()
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError) as caught:
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
        return str(caught.value)
    finally:
        restored_audit.close()


def test_restore_rejects_missing_snapshot_database(catalog, tmp_path):
    message = _restore_with_tampered_snapshot(
        catalog, tmp_path, "no-snapshot", lambda c, i: None, copy_snapshot=False,
    )
    assert "required tabular source snapshot database is" in message


def test_restore_rejects_deleted_snapshot_row(catalog, tmp_path):
    message = _restore_with_tampered_snapshot(
        catalog, tmp_path, "deleted-row",
        lambda c, i: c.execute("DELETE FROM import_rows WHERE import_id=?", (i,)),
    )
    assert "snapshot row is missing" in message


def test_restore_rejects_uncommitted_source_import(catalog, tmp_path):
    message = _restore_with_tampered_snapshot(
        catalog, tmp_path, "uncommitted",
        lambda c, i: c.execute("UPDATE imports SET status='failed' WHERE import_id=?", (i,)),
    )
    assert "missing or not committed" in message


def test_restore_rejects_extra_snapshot_rows_for_import(catalog, tmp_path):
    def add_row(conn, import_id):
        conn.execute(
            "INSERT INTO import_rows(row_id, record_key, import_id, source_record_number,"
            " payload_json, locator_json) VALUES('extra-row','extra',?,99,'{}','{}')",
            (import_id,),
        )
    message = _restore_with_tampered_snapshot(catalog, tmp_path, "extra-row", add_row)
    assert "missing snapshot rows" in message


def test_restore_rejects_changed_import_schema_fingerprint(catalog, tmp_path):
    def change(conn, import_id):
        manifest = json.loads(conn.execute(
            "SELECT manifest_json FROM imports WHERE import_id=?", (import_id,)).fetchone()[0])
        manifest["schema_fingerprint"] = "0" * 64
        conn.execute("UPDATE imports SET manifest_json=? WHERE import_id=?",
                     (json.dumps(manifest), import_id))
    message = _restore_with_tampered_snapshot(catalog, tmp_path, "schema-fp", change)
    assert "does not match its stored provenance" in message


def test_restore_rejects_changed_import_dataset_id(catalog, tmp_path):
    def change(conn, import_id):
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO datasets SELECT 'other-dataset', schema_id, schema_version,"
                     " schema_fingerprint, created_at FROM datasets LIMIT 1")
        conn.execute("UPDATE imports SET dataset_id='other-dataset' WHERE import_id=?", (import_id,))
    message = _restore_with_tampered_snapshot(catalog, tmp_path, "dataset-id", change)
    assert "does not match its stored provenance" in message



def _linked_backup(catalog, conflicting=False):
    """Backup of a store with two customers and a link citing a second, object-free import."""
    from agora.identity import stable_record_key
    project, store, audit, _, _ = catalog
    pack_data = {
        "pack_id": "backup-link-pack", "schema_version": "1.0.0",
        "object_types": [{
            "type_id": "backup:Customer", "version": "1.0.0", "name": "Customer",
            "description": "Customer",
            "properties": ["backup:Customer.id", "backup:Customer.email"],
            "identity_strategy": "record_key",
        }],
        "property_types": [
            {"property_id": "backup:Customer.id", "version": "1.0.0", "name": "id",
             "data_type": "identifier", "required": True, "nullable": False,
             "sensitivity": "personal"},
            {"property_id": "backup:Customer.email", "version": "1.0.0", "name": "email",
             "data_type": "string", "required": True, "nullable": False,
             "sensitivity": "sensitive"},
        ],
        "link_types": [{
            "link_type_id": "backup:refers", "version": "1.0.0", "name": "refers",
            "source_type_id": "backup:Customer", "target_type_id": "backup:Customer",
            "predicate": "refers", "cardinality": "many_to_many",
        }],
        "action_types": [],
    }
    pack_fp = store.register_pack(parse_domain_pack(pack_data), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-1,one@example.test\nC-2,two@example.test\n", encoding="utf-8")
    imported = ingest_csv(project, source, _SCHEMA, data_role="context", policy=_allow, audit=audit)
    import_id = imported["import_id"]
    assert store.materialize_binding(
        pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
        purpose="account support", retention="90 days") == 2

    def endpoint(key):
        return {"project_id": store.project_id, "pack_fingerprint": pack_fp,
                "type_id": "backup:Customer", "type_version": "1.0.0",
                "import_id": import_id,
                "record_key": stable_record_key("customers", key)}

    other_source = project / "other.csv"
    other_source.write_text("customer_id,email\nC-9,nine@example.test\n", encoding="utf-8")
    other = ingest_csv(project, other_source, _SCHEMA, data_role="context", policy=_allow, audit=audit)
    other_id = other["import_id"]
    other_sha = hashlib.sha256(other_source.read_bytes()).hexdigest()
    refs = [{"import_id": other_id, "file_sha256": other_sha, "locator": "row:2"}]
    if conflicting:
        refs.append({"import_id": other_id, "file_sha256": "b" * 64, "locator": "row:2"})
    store.add_link(
        pack_fp, "backup:refers", "1.0.0", endpoint("C-1"), endpoint("C-2"),
        "2026-01-01T00:00:00+00:00", None, "referral",
        {"kind": "source", "source_refs": refs},
        policy=_allow, audit=audit)
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    return other_id, backup_path


def _restore_linked(catalog, tmp_path, name, tamper, *, expect_error, conflicting=False):
    project = catalog[0]
    import_id, backup_path = _linked_backup(catalog, conflicting)
    restored_project = tmp_path / name / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    tabular_copy = restored_data / "tabular.sqlite3"
    shutil.copyfile(project / "data" / "tabular.sqlite3", tabular_copy)
    connection = sqlite3.connect(tabular_copy)
    try:
        tamper(connection, import_id)
        connection.commit()
    finally:
        connection.close()
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        if expect_error is None:
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
            return restored_store, restored_backup, import_id
        with pytest.raises(OntologyError) as caught:
            restored_store.restore(restored_backup, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
        return str(caught.value)
    finally:
        restored_audit.close()


def test_restore_accepts_source_backed_link_with_matching_snapshot(catalog, tmp_path):
    _restore_linked(catalog, tmp_path, "link-ok", lambda c, i: None, expect_error=None)


def test_restore_rejects_source_backed_link_when_import_hash_changed(catalog, tmp_path):
    message = _restore_linked(
        catalog, tmp_path, "link-hash",
        lambda c, i: c.execute("UPDATE imports SET file_sha256=? WHERE import_id=?", ("a" * 64, i)),
        expect_error=True,
    )
    assert "source-backed link references a missing or changed import" in message


def test_restore_rejects_source_backed_link_import_with_extra_rows(catalog, tmp_path):
    def add_row(conn, import_id):
        conn.execute(
            "INSERT INTO import_rows(row_id, record_key, import_id, source_record_number,"
            " payload_json, locator_json) VALUES('extra-link-row','extra',?,99,'{}','{}')",
            (import_id,),
        )
    message = _restore_linked(catalog, tmp_path, "link-rows", add_row, expect_error=True)
    assert "source-backed link import is missing snapshot rows" in message


def test_restore_rejects_conflicting_hashes_for_one_link_import(catalog, tmp_path):
    message = _restore_linked(
        catalog, tmp_path, "link-conflict", lambda c, i: None,
        expect_error=True, conflicting=True,
    )
    assert "conflicting hashes for one source import" in message


_ATTEMPT_CACHE: dict = {}


def _restore_attempt(catalog, tmp_path, name, tamper, digest):
    """Restore the standard backup into a fresh project; return (store, error or None)."""
    project, store, audit = catalog[0], catalog[1], catalog[2]
    cached = _ATTEMPT_CACHE.get(str(project))
    if cached is None:
        import_id, backup_path = _materialized_backup(catalog)
        manifest = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
        cached = _ATTEMPT_CACHE[str(project)] = (import_id, backup_path, manifest)
    import_id, backup_path, manifest = cached
    restored_project = tmp_path / name / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    tabular_copy = restored_data / "tabular.sqlite3"
    shutil.copyfile(project / "data" / "tabular.sqlite3", tabular_copy)
    connection = sqlite3.connect(tabular_copy)
    try:
        tamper(connection, import_id)
        connection.commit()
    finally:
        connection.close()
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        chosen = manifest["source_snapshot_digest"] if digest == "manifest" else digest
        try:
            restored_store.restore(
                restored_backup, policy=_allow, audit=restored_audit,
                expected_source_snapshot_digest=chosen,
            )
            return restored_store, None
        except OntologyError as exc:
            assert not restored_store.path.exists()
            return restored_store, str(exc)
    finally:
        restored_audit.close()


def _tamper_payload(conn, import_id):
    conn.execute(
        "UPDATE import_rows SET payload_json=? WHERE import_id=?",
        ('{"customer_id":"C-SECRET-001","email":"attacker@example.test"}', import_id),
    )


def test_manifest_carries_source_snapshot_digest_without_row_values(catalog):
    project, store, audit, _, _ = catalog
    import_id, backup_path = _materialized_backup(catalog)
    first = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    second = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    digest = first["source_snapshot_digest"]
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert digest == second["source_snapshot_digest"]
    serialized = json.dumps(first)
    assert "private-value@example.test" not in serialized and "C-SECRET-001" not in serialized
    connection = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        _tamper_payload(connection, import_id)
        connection.commit()
    finally:
        connection.close()
    changed = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    assert changed["source_snapshot_digest"] != digest


def test_restore_with_matching_anchored_digest_succeeds(catalog, tmp_path):
    restored_store, error = _restore_attempt(
        catalog, tmp_path, "anchor-ok", lambda c, i: None, "manifest")
    assert error is None and restored_store.path.exists()


def test_anchored_digest_detects_payload_tampering_that_consistency_checks_miss(catalog, tmp_path):
    unanchored_store, unanchored_error = _restore_attempt(
        catalog, tmp_path, "tamper-unanchored", _tamper_payload, None)
    assert unanchored_error is None and unanchored_store.path.exists()
    anchored_store, anchored_error = _restore_attempt(
        catalog, tmp_path, "tamper-anchored", _tamper_payload, "manifest")
    assert anchored_error is not None
    assert "does not match the anchored digest" in anchored_error
    assert not anchored_store.path.exists()


def test_anchored_digest_must_be_a_sha256(catalog, tmp_path):
    for bad in ("short", "z" * 64, 12345):
        _, error = _restore_attempt(catalog, tmp_path, f"bad-{abs(hash(str(bad)))}", lambda c, i: None, bad)
        assert error is not None and "64-character SHA-256" in error


def test_anchored_digest_for_wrong_content_is_refused(catalog, tmp_path):
    _, error = _restore_attempt(catalog, tmp_path, "wrong-digest", lambda c, i: None, "0" * 64)
    assert error is not None and "does not match the anchored digest" in error


def test_anchored_digest_applies_to_backups_without_source_dependencies(catalog, tmp_path):
    project, store, audit, _, _ = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    manifest = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    assert manifest["source_snapshot_files"] == []
    for name, digest, ok in (("empty-ok", manifest["source_snapshot_digest"], True),
                             ("empty-bad", "1" * 64, False)):
        restored_project = tmp_path / name / project.name
        restored_data = restored_project / "data"
        restored_data.mkdir(parents=True)
        restored_backup = restored_data / backup_path.name
        shutil.copyfile(backup_path, restored_backup)
        restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
        restored_store = OntologyObjectStore(restored_project)
        try:
            if ok:
                restored_store.restore(
                    restored_backup, policy=_allow, audit=restored_audit,
                    expected_source_snapshot_digest=digest)
            else:
                with pytest.raises(OntologyError, match="does not match the anchored digest"):
                    restored_store.restore(
                        restored_backup, policy=_allow, audit=restored_audit,
                        expected_source_snapshot_digest=digest)
        finally:
            restored_audit.close()


@pytest.mark.parametrize("statement", [
    "UPDATE import_rows SET locator_json='{\"x\":1}' WHERE import_id=?",
    "UPDATE import_rows SET record_key='other-key' WHERE import_id=?",
    "UPDATE import_rows SET row_id='renamed-row' WHERE import_id=?",
    "UPDATE import_rows SET source_record_number=source_record_number+100 WHERE import_id=?",
    "UPDATE imports SET status='failed' WHERE import_id=?",
    "UPDATE imports SET source_registry_id='other-registry' WHERE import_id=?",
    "UPDATE imports SET manifest_json=json_set(manifest_json, '$.extra_field', 1) WHERE import_id=?",
])
def test_every_snapshot_field_is_bound_by_the_digest(catalog, statement):
    project, store, audit, _, _ = catalog
    import_id, backup_path = _materialized_backup(catalog)
    before = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    connection = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(statement, (import_id,))
        connection.commit()
    finally:
        connection.close()
    after = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    assert after["source_snapshot_digest"] != before["source_snapshot_digest"]


def test_anchored_digest_accepts_uppercase_hex(catalog, tmp_path):
    import_id, backup_path = _materialized_backup(catalog)
    project, store, audit = catalog[0], catalog[1], catalog[2]
    digest = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)["source_snapshot_digest"]
    restored_project = tmp_path / "upper" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    shutil.copyfile(project / "data" / "tabular.sqlite3", restored_data / "tabular.sqlite3")
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    try:
        OntologyObjectStore(restored_project).restore(
            restored_backup, policy=_allow, audit=restored_audit,
            expected_source_snapshot_digest=digest.upper())
    finally:
        restored_audit.close()

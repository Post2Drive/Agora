"""Focused tests for the ontology object-store backup and dependency manifest."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import shutil

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


def test_restore_refuses_existing_destination(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)

    with pytest.raises(OntologyError, match="destination already exists"):
        store.restore(backup_path, policy=_allow, audit=audit)


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

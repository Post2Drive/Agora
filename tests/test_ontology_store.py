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
        "link_types": [{
            "link_type_id": "backup:knows",
            "version": "1.0.0",
            "name": "knows",
            "source_type_id": "backup:Customer",
            "target_type_id": "backup:Customer",
            "predicate": "knows",
            "cardinality": "many_to_many",
        }],
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


def _attested(store, backup_path, audit):
    """Manifest plus the digest an operator would retain separately."""
    manifest = store.backup_dependency_manifest(backup_path, policy=_allow, audit=audit)
    return {"dependency_manifest": manifest,
            "expected_manifest_sha256": manifest["manifest_sha256"]}


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
    assert report["schema_version"] == 4


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
    assert manifest["format"] == "agora-ontology-backup-dependencies/v2"
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
    attested = _attested(store, backup_path, audit)

    restored_project = tmp_path / "restored" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        result = restored_store.restore(
            restored_backup, **attested, policy=_allow, audit=restored_audit,
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
    attested = _attested(store, backup_path, audit)

    restored_project = tmp_path / "missing-source" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError, match="tabular source snapshot"):
            restored_store.restore(restored_backup, **attested, policy=_allow, audit=restored_audit)
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
    attested = _attested(store, backup_path, audit)

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
            restored_store.restore(restored_backup, **attested, policy=_allow, audit=restored_audit)
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
    attested = _attested(store, backup_path, audit)

    restored_project = tmp_path / "matching-source" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    restored_backup = restored_data / backup_path.name
    shutil.copyfile(backup_path, restored_backup)
    shutil.copyfile(project / "data" / "tabular.sqlite3", restored_data / "tabular.sqlite3")
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        restored_store.restore(restored_backup, **attested, policy=_allow, audit=restored_audit)
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
    attested = _attested(store, backup_path, audit)

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
            restored_store.restore(restored_backup, **attested, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
    finally:
        restored_audit.close()


def test_restore_refuses_existing_destination(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    attested = _attested(store, backup_path, audit)

    with pytest.raises(OntologyError, match="destination already exists"):
        store.restore(backup_path, **attested, policy=_allow, audit=audit)



def test_restore_refuses_stale_sqlite_sidecars(catalog):
    project, store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    attested = _attested(store, backup_path, audit)
    original_database = store.path.read_bytes()
    sidecar = Path(str(store.path) + "-wal")
    sidecar.write_bytes(b"stale wal marker")

    with pytest.raises(OntologyError, match="SQLite sidecars"):
        store.restore(backup_path, **attested, policy=_allow, audit=audit)
    assert store.path.read_bytes() == original_database
    assert sidecar.read_bytes() == b"stale wal marker"


def test_restore_rejects_corrupt_backup_without_publishing(catalog):
    project, _store, audit, _pack_fingerprint, _binding_fingerprint = catalog
    restored_project = project.parent / "restored-corrupt" / project.name
    restored_data = restored_project / "data"
    restored_data.mkdir(parents=True)
    corrupt_backup = restored_data / "corrupt.sqlite3"
    corrupt_backup.write_bytes(b"not a sqlite database")
    # Even a digest that matches the corrupt bytes must not get them published.
    manifest = {
        "format": "agora-ontology-backup-dependencies/v2",
        "project_id": project.name,
        "ontology_backup": {
            "bytes": corrupt_backup.stat().st_size,
            "sha256": hashlib.sha256(corrupt_backup.read_bytes()).hexdigest(),
        },
        "source_import_attestations": [],
    }
    attested = _resealed(manifest)
    restored_audit = AuditChainStore(restored_data / "audit_chain.sqlite3")
    restored_store = OntologyObjectStore(restored_project)
    try:
        with pytest.raises(OntologyError):
            restored_store.restore(corrupt_backup, **attested, policy=_allow, audit=restored_audit)
        assert not restored_store.path.exists()
        assert list(restored_data.glob("*.tmp*")) == []
    finally:
        restored_audit.close()


def _resealed(manifest):
    """A manifest whose embedded digest is self-consistent (attacker-capable)."""
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    digest = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    return {"dependency_manifest": {**body, "manifest_sha256": digest},
            "expected_manifest_sha256": digest}


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


def _import(project, audit, name, body):
    source = project / name
    source.write_text("customer_id,email\n" + body, encoding="utf-8")
    return ingest_csv(project, source, _SCHEMA, data_role="context",
                      policy=_allow, audit=audit)["import_id"]


@pytest.fixture
def recovery(catalog, tmp_path):
    """A backed-up, attested source-backed store and an empty restore target."""
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    import_id = _import(project, audit, "customers.csv",
                        "C-1,one@example.test\nC-2,two@example.test\n")
    store.materialize_binding(
        pack_fingerprint, binding_fingerprint, import_id,
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    )
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    attested = _attested(store, backup_path, audit)
    target_data = tmp_path / "target" / project.name / "data"
    target_data.mkdir(parents=True)
    shutil.copyfile(backup_path, target_data / backup_path.name)
    shutil.copyfile(project / "data" / "tabular.sqlite3", target_data / "tabular.sqlite3")
    target_audit = AuditChainStore(target_data / "audit_chain.sqlite3")
    try:
        yield {
            "project": project, "store": store, "audit": audit, "import_id": import_id,
            "backup": backup_path, "attested": attested, "data": target_data,
            "target_backup": target_data / backup_path.name,
            "target": OntologyObjectStore(target_data.parent),
            "target_audit": target_audit,
        }
    finally:
        target_audit.close()


def _sql(path, statement, parameters=()):
    conn = sqlite3.connect(path)
    try:
        conn.execute(statement, parameters)
        conn.commit()
    finally:
        conn.close()


def _restore(r, attested=None, policy=_allow):
    return r["target"].restore(
        r["target_backup"], **(attested or r["attested"]),
        policy=policy, audit=r["target_audit"],
    )


def _assert_refused(r, match, **kwargs):
    with pytest.raises(OntologyError, match=match):
        _restore(r, **kwargs)
    assert not r["target"].path.exists()
    assert list(r["data"].glob("*.tmp*")) == []


def test_attestation_covers_referenced_imports_without_row_values(recovery):
    manifest = recovery["attested"]["dependency_manifest"]
    (entry,) = manifest["source_import_attestations"]
    assert entry["import_id"] == recovery["import_id"]
    assert entry["algorithm"] == "agora-import-content-sha256/v1"
    assert entry["row_count"] == 2
    assert len(entry["content_sha256"]) == 64
    assert "one@example.test" not in _canonical(manifest)
    assert list((recovery["project"] / "data").glob("*.tmp*")) == []


@pytest.mark.parametrize("statement", [
    "UPDATE import_rows SET payload_json=replace(payload_json,'one@','evil@')",
    "UPDATE import_rows SET record_key='forged' WHERE source_record_number="
    "(SELECT MIN(source_record_number) FROM import_rows)",
    "UPDATE imports SET manifest_json=replace(manifest_json,'\"sensitive\"','\"public\"')",
    "UPDATE imports SET created_at='1999-01-01T00:00:00Z'",
])
def test_restore_rejects_tampered_content_that_keeps_metadata(recovery, statement):
    tabular = recovery["data"] / "tabular.sqlite3"
    before = sqlite3.connect(tabular)
    dump_before = list(before.iterdump())
    before.close()
    _sql(tabular, statement)
    after = sqlite3.connect(tabular)
    assert list(after.iterdump()) != dump_before
    after.close()
    _assert_refused(recovery, "content does not match")


def test_later_unrelated_import_does_not_break_restore(recovery):
    target_project = recovery["data"].parent
    _import(target_project, recovery["target_audit"], "later.csv", "C-9,nine@example.test\n")
    assert _restore(recovery).is_file()
    assert list(recovery["data"].glob("*.tmp*")) == []


def test_restore_rejects_manifest_rewritten_to_match_tampering(recovery):
    _sql(recovery["data"] / "tabular.sqlite3",
         "UPDATE import_rows SET payload_json=replace(payload_json,'one@','evil@')")
    # The attacker regenerates a fully consistent manifest from tampered data.
    shutil.copyfile(recovery["data"] / "tabular.sqlite3",
                    recovery["project"] / "data" / "tabular.sqlite3")
    forged = _attested(recovery["store"], recovery["backup"], recovery["audit"])
    retained = recovery["attested"]["expected_manifest_sha256"]
    _assert_refused(
        recovery, "retained manifest SHA-256",
        attested={"dependency_manifest": forged["dependency_manifest"],
                  "expected_manifest_sha256": retained},
    )


def test_restore_rejects_edited_manifest_body(recovery):
    manifest = dict(recovery["attested"]["dependency_manifest"])
    manifest["source_import_attestations"] = []
    _assert_refused(recovery, "retained manifest SHA-256", attested={
        "dependency_manifest": manifest,
        "expected_manifest_sha256": recovery["attested"]["expected_manifest_sha256"],
    })


def test_restore_rejects_wrong_embedded_digest(recovery):
    manifest = {**recovery["attested"]["dependency_manifest"], "manifest_sha256": "0" * 64}
    _assert_refused(recovery, "retained manifest SHA-256", attested={
        "dependency_manifest": manifest,
        "expected_manifest_sha256": recovery["attested"]["expected_manifest_sha256"],
    })


@pytest.mark.parametrize("retained", [None, "", "A" * 64, "0" * 63])
def test_restore_requires_a_retained_digest(recovery, retained):
    _assert_refused(recovery, "separately retained", attested={
        "dependency_manifest": recovery["attested"]["dependency_manifest"],
        "expected_manifest_sha256": retained,
    })


@pytest.mark.parametrize("field,value", [
    ("format", "agora-ontology-backup-dependencies/v1"),
    ("project_id", "another-project"),
])
def test_restore_rejects_other_format_or_project(recovery, field, value):
    manifest = {**recovery["attested"]["dependency_manifest"], field: value}
    _assert_refused(recovery, "format or project", attested=_resealed(manifest))


def test_restore_rejects_attestation_list_missing_an_import(recovery):
    manifest = {**recovery["attested"]["dependency_manifest"], "source_import_attestations": []}
    _assert_refused(recovery, "content does not match", attested=_resealed(manifest))


def test_restore_rejects_backup_bytes_other_than_attested(recovery):
    # Still a perfectly valid ontology database, just not the attested one.
    _sql(recovery["target_backup"], "PRAGMA user_version = 7")
    _assert_refused(recovery, "backup bytes do not match")


def test_pending_wal_beside_backup_is_refused(recovery):
    for path, call in (
        (recovery["target_backup"], lambda: _restore(recovery)),
        (recovery["backup"], lambda: recovery["store"].backup_dependency_manifest(
            recovery["backup"], policy=_allow, audit=recovery["audit"])),
    ):
        sidecar = Path(str(path) + "-wal")
        sidecar.write_bytes(b"pending frames the file hash cannot cover")
        with pytest.raises(OntologyError, match="pending SQLite journal"):
            call()
        sidecar.unlink()
    assert not recovery["target"].path.exists()


def test_restore_publishes_the_bytes_it_verified(recovery, monkeypatch):
    from agora.ontology import store as store_module
    real = store_module._stage_private_copy

    def swap_source_after_copy(source, destination):
        result = real(source, destination)
        source.write_bytes(b"replaced while restore was verifying")
        return result

    monkeypatch.setattr(store_module, "_stage_private_copy", swap_source_after_copy)
    published = _restore(recovery)
    expected = recovery["attested"]["dependency_manifest"]["ontology_backup"]["sha256"]
    assert hashlib.sha256(published.read_bytes()).hexdigest() == expected


def test_denied_source_content_read_happens_before_any_digest(recovery, monkeypatch):
    from agora import protection
    from agora.ontology import store as store_module
    monkeypatch.setattr(protection, "POLICY_REQUIRED", True)
    read = []
    monkeypatch.setattr(store_module, "_import_content_attestation",
                        lambda *args: read.append(args))
    seen = []

    def deny_content(operation, resource):
        if "store_source_attestation" in resource["resource_ids"]:
            seen.append((operation, resource["source_sensitivity"]))
            return {"decision": "deny", "reason": "not_cleared"}
        return _allow(operation, resource)

    _assert_refused(recovery, "policy denied", policy=deny_content)
    with pytest.raises(OntologyError, match="policy denied"):
        recovery["store"].backup_dependency_manifest(
            recovery["backup"], policy=deny_content, audit=recovery["audit"])
    assert seen == [("ontology_write", "sensitive")] * 2
    assert read == []


def test_restore_refuses_orphan_sidecar_when_destination_is_absent(recovery):
    sidecar = Path(str(recovery["target"].path) + "-wal")
    sidecar.write_bytes(b"stale wal marker")
    _assert_refused(recovery, "SQLite sidecars")
    assert sidecar.read_bytes() == b"stale wal marker"


def test_restore_rejects_records_belonging_to_another_project(recovery, tmp_path):
    other_data = tmp_path / "elsewhere" / "renamed-project" / "data"
    other_data.mkdir(parents=True)
    for name in (recovery["backup"].name, "tabular.sqlite3"):
        shutil.copyfile(recovery["data"] / name, other_data / name)
    manifest = {**recovery["attested"]["dependency_manifest"], "project_id": "renamed-project"}
    other_audit = AuditChainStore(other_data / "audit_chain.sqlite3")
    other = OntologyObjectStore(other_data.parent)
    try:
        with pytest.raises(OntologyError, match="different project"):
            other.restore(other_data / recovery["backup"].name, **_resealed(manifest),
                          policy=_allow, audit=other_audit)
        assert not other.path.exists()
    finally:
        other_audit.close()


@pytest.mark.parametrize("statement,match", [
    ("UPDATE imports SET status='failed'", "missing or not committed"),
    ("INSERT INTO import_rows SELECT 'extra-row', record_key, import_id, 999, payload_json, "
     "locator_json FROM import_rows LIMIT 1", "missing snapshot rows"),
])
def test_restore_names_metadata_damage_before_reading_content(recovery, statement, match):
    _sql(recovery["data"] / "tabular.sqlite3", statement)
    _assert_refused(recovery, match)


@pytest.fixture
def linked(catalog, tmp_path):
    """Objects from one import, joined by a link that cites a second, link-only import."""
    project, store, audit, pack_fingerprint, binding_fingerprint = catalog
    objects = _import(project, audit, "customers.csv",
                      "C-1,one@example.test\nC-2,two@example.test\n")
    store.materialize_binding(
        pack_fingerprint, binding_fingerprint, objects,
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    )
    evidence = _import(project, audit, "evidence.csv", "E-1,evidence@example.test\n")
    ontology = sqlite3.connect(store.path)
    keys = [row[0] for row in ontology.execute(
        "SELECT record_key FROM ontology_object_refs ORDER BY record_key")]
    ontology.close()
    tabular = sqlite3.connect(project / "data" / "tabular.sqlite3")
    digest = tabular.execute(
        "SELECT file_sha256 FROM imports WHERE import_id=?", (evidence,)).fetchone()[0]
    tabular.close()
    endpoint = lambda key: {
        "project_id": project.name, "pack_fingerprint": pack_fingerprint,
        "type_id": "backup:Customer", "type_version": "1.0.0",
        "import_id": objects, "record_key": key,
    }

    def link(source, target, sha):
        return store.add_link(
            pack_fingerprint, "backup:knows", "1.0.0", endpoint(keys[source]),
            endpoint(keys[target]), "2026-01-01T00:00:00Z", None, "fixture link",
            {"kind": "source", "source_refs": [
                {"import_id": evidence, "file_sha256": sha, "locator": "row:2"}]},
            policy=_allow, audit=audit,
        )

    link(0, 1, digest)
    return {"project": project, "store": store, "audit": audit, "evidence": evidence,
            "digest": digest, "link": link, "tmp": tmp_path}


def _backup_and_target(linked):
    project, store, audit = linked["project"], linked["store"], linked["audit"]
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    attested = _attested(store, backup_path, audit)
    data = linked["tmp"] / "linked-target" / project.name / "data"
    data.mkdir(parents=True)
    for name in (backup_path.name, "tabular.sqlite3"):
        shutil.copyfile(project / "data" / name, data / name)
    return backup_path, attested, data


def test_link_only_import_is_attested_and_its_content_protected(linked):
    backup_path, attested, data = _backup_and_target(linked)
    entries = attested["dependency_manifest"]["source_import_attestations"]
    assert linked["evidence"] in {entry["import_id"] for entry in entries}
    assert len(entries) == 2
    _sql(data / "tabular.sqlite3",
         "UPDATE import_rows SET payload_json=replace(payload_json,'evidence@','forged@')")
    target = OntologyObjectStore(data.parent)
    target_audit = AuditChainStore(data / "audit_chain.sqlite3")
    try:
        with pytest.raises(OntologyError, match="content does not match"):
            target.restore(data / backup_path.name, **attested,
                           policy=_allow, audit=target_audit)
        assert not target.path.exists()
        shutil.copyfile(linked["project"] / "data" / "tabular.sqlite3", data / "tabular.sqlite3")
        _sql(data / "tabular.sqlite3",
             "UPDATE imports SET file_sha256=? WHERE import_id=?", ("0" * 64, linked["evidence"]))
        with pytest.raises(OntologyError, match="missing or changed import"):
            target.restore(data / backup_path.name, **attested,
                           policy=_allow, audit=target_audit)
        assert not target.path.exists()
    finally:
        target_audit.close()


def test_conflicting_link_hashes_for_one_import_block_attestation(linked, monkeypatch):
    # Writes now refuse this; simulate a link stored before that check existed.
    monkeypatch.setattr(linked["store"], "_verify_link_source_refs", lambda refs: None)
    linked["link"](1, 0, "f" * 64)
    with pytest.raises(OntologyError, match="conflicting hashes"):
        _backup_and_target(linked)


def test_integrity_rejects_malformed_link_source_hash(linked):
    store, audit = linked["store"], linked["audit"]
    columns = ("project_id, pack_fingerprint, link_type_id, link_type_version, source_type_id, "
               "source_type_version, source_import_id, source_record_key, target_type_id, "
               "target_type_version, target_import_id, target_record_key, valid_from, valid_to, "
               "created_at, actor_id, reason")
    _sql(store.path,
         f"INSERT INTO ontology_links(link_id, {columns}, provenance_json) "
         f"SELECT 'link-forged', {columns}, replace(provenance_json, ?, 'not-a-sha') "
         "FROM ontology_links LIMIT 1", (linked["digest"],))
    with pytest.raises(OntologyError, match="invalid SHA-256"):
        store.verify_integrity(policy=_allow, audit=audit)


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
    attested = _attested(catalog[1], backup_path, catalog[2])
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
            restored_store.restore(
                restored_backup, **attested, policy=_allow, audit=restored_audit)
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
    with pytest.MonkeyPatch.context() as patch:
        if conflicting:
            # Writes now refuse this; simulate a link stored before that check existed.
            patch.setattr(store, "_verify_link_source_refs", lambda refs: None)
        store.add_link(
            pack_fp, "backup:refers", "1.0.0", endpoint("C-1"), endpoint("C-2"),
            "2026-01-01T00:00:00+00:00", None, "referral",
            {"kind": "source", "source_refs": refs},
            policy=_allow, audit=audit)
    backup_path = project / "data" / "ontology.backup.sqlite3"
    store.backup(backup_path, policy=_allow, audit=audit)
    return other_id, backup_path


def _restore_linked(catalog, tmp_path, name, tamper, *, expect_error):
    project = catalog[0]
    import_id, backup_path = _linked_backup(catalog)
    attested = _attested(catalog[1], backup_path, catalog[2])
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
            restored_store.restore(
                restored_backup, **attested, policy=_allow, audit=restored_audit)
            return restored_store, restored_backup, import_id
        with pytest.raises(OntologyError) as caught:
            restored_store.restore(
                restored_backup, **attested, policy=_allow, audit=restored_audit)
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


def test_manifest_refuses_conflicting_hashes_within_one_link(catalog):
    _, backup_path = _linked_backup(catalog, True)
    with pytest.raises(OntologyError, match="conflicting hashes for one source import"):
        _attested(catalog[1], backup_path, catalog[2])


@pytest.mark.parametrize("statement", [
    "UPDATE import_rows SET payload_json='{}' WHERE import_id=?",
    "UPDATE import_rows SET locator_json='{\"x\":1}' WHERE import_id=?",
    "UPDATE import_rows SET record_key='other-key' WHERE import_id=?",
    "UPDATE import_rows SET row_id='renamed-row' WHERE import_id=?",
    "UPDATE import_rows SET source_record_number=source_record_number+100 WHERE import_id=?",
    "UPDATE imports SET idempotency_key='other' WHERE import_id=?",
    "UPDATE imports SET dataset_id='other-dataset' WHERE import_id=?",
    "UPDATE imports SET source_registry_id='other-registry' WHERE import_id=?",
    "UPDATE imports SET file_sha256='other' WHERE import_id=?",
    "UPDATE imports SET status='failed' WHERE import_id=?",
    "UPDATE imports SET manifest_json=json_set(manifest_json, '$.extra_field', 1) WHERE import_id=?",
    "UPDATE imports SET created_at='1999-01-01T00:00:00Z' WHERE import_id=?",
])
def test_every_stored_import_field_is_bound_by_the_content_digest(catalog, statement):
    from agora.ontology.store import _import_content_attestation
    import_id, _ = _materialized_backup(catalog)
    connection = sqlite3.connect(catalog[0] / "data" / "tabular.sqlite3")
    try:
        before = _import_content_attestation(connection, import_id)
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(statement, (import_id,))
        after = _import_content_attestation(connection, import_id)
    finally:
        connection.close()
    assert after["content_sha256"] != before["content_sha256"]

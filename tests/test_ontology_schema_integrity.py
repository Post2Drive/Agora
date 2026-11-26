"""Integrity checks must verify real schema objects, not only migration rows."""

from __future__ import annotations

import sqlite3

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, load_binding, parse_domain_pack


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
    pack = parse_domain_pack({
        "pack_id": "schema-test-pack",
        "schema_version": "1.0.0",
        "object_types": [{
            "type_id": "schema:Item", "version": "1.0.0", "name": "Item",
            "description": "Item", "properties": ["schema:Item.id"],
            "identity_strategy": "record_key",
        }],
        "property_types": [{
            "property_id": "schema:Item.id", "version": "1.0.0", "name": "id",
            "data_type": "identifier", "required": True, "nullable": False,
            "sensitivity": "internal",
        }],
        "link_types": [],
        "action_types": [],
    })
    pack_fingerprint = store.register_pack(pack, policy=_allow, audit=audit)
    store.register_binding(pack_fingerprint, load_binding({
        "binding_id": "schema.item.v1",
        "binding_version": "1.0.0",
        "object_type_id": "schema:Item",
        "object_type_version": "1.0.0",
        "dataset_id": "items",
        "schema_id": "items-v1",
        "schema_version": "1.0.0",
        "column_map": {"item_id": "schema:Item.id"},
        "identity": {"strategy": "record_key", "primary_key_column": "item_id"},
        "property_sensitivity": {"schema:Item.id": "internal"},
    }), policy=_allow, audit=audit)
    try:
        yield project, store, audit
    finally:
        audit.close()


def _alter(store, *statements):
    conn = sqlite3.connect(store.path)
    try:
        for statement in statements:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def test_untouched_store_and_its_backup_still_verify(catalog):
    project, store, audit = catalog
    assert store.verify_integrity(policy=_allow, audit=audit)["ok"] is True
    backup = store.backup(project / "data" / "ok.sqlite3", policy=_allow, audit=audit)
    assert backup.is_file()


def test_sqlite_statistics_tables_are_not_treated_as_tampering(catalog):
    _project, store, audit = catalog
    _alter(store, "ANALYZE")
    assert store.verify_integrity(policy=_allow, audit=audit)["ok"] is True


@pytest.mark.parametrize("statements", [
    ("DROP TRIGGER ontology_packs_no_delete",),
    ("DROP TRIGGER ontology_links_no_update",),
    ("CREATE TRIGGER injected AFTER INSERT ON bindings BEGIN DELETE FROM bindings; END",),
    (
        "DROP TRIGGER ontology_packs_no_update",
        "CREATE TRIGGER ontology_packs_no_update BEFORE UPDATE ON ontology_packs "
        "BEGIN SELECT 1; END",
    ),
    ("CREATE VIEW injected_view AS SELECT * FROM bindings",),
    ("CREATE TABLE injected_table (value TEXT)",),
    ("DROP INDEX ontology_links_successor_idx",),
    ("ALTER TABLE bindings ADD COLUMN injected TEXT",),
], ids=[
    "dropped-pack-trigger", "dropped-link-trigger", "added-trigger", "hollowed-trigger",
    "added-view", "added-table", "dropped-unique-index", "added-column",
])
def test_altered_schema_objects_are_refused_by_verify_and_backup(catalog, statements):
    project, store, audit = catalog
    _alter(store, *statements)

    with pytest.raises(OntologyError, match="schema objects do not match"):
        store.verify_integrity(policy=_allow, audit=audit)

    destination = project / "data" / "refused.sqlite3"
    with pytest.raises(OntologyError, match="schema objects do not match"):
        store.backup(destination, policy=_allow, audit=audit)
    assert not destination.exists()


@pytest.mark.parametrize("column,value", [("binding_id", "forged.id"), ("binding_version", "9.9.9")])
def test_forged_binding_metadata_is_refused(catalog, column, value):
    _project, store, audit = catalog
    conn = sqlite3.connect(store.path)
    try:
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='ontology_bindings_no_update'"
        ).fetchone()[0]
    finally:
        conn.close()
    # Put the exact trigger back, so only the row metadata differs.
    _alter(
        store,
        "DROP TRIGGER ontology_bindings_no_update",
        f"UPDATE bindings SET {column}='{value}'",
        trigger_sql,
    )

    with pytest.raises(OntologyError, match="binding metadata does not match"):
        store.verify_integrity(policy=_allow, audit=audit)

"""Ontology reads must refuse stored snapshot content that disagrees with its IDs."""

from __future__ import annotations

import json
import sqlite3

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore
from agora.ontology.binding import materialize_instances
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import (
    SnapshotIntegrityError, _import_identity, _row_id, _source_registry_id, ingest_csv,
    verify_snapshot_manifest, verify_snapshot_row,
)
from test_ontology_binding import binding, pack, schema, write_csv
from test_ontology_store import _allow, _binding, _pack

ROWS = [["C-1", "one@example.test"], ["C-2", "two@example.test"]]


def _ingest(project, role="context"):
    project.mkdir(exist_ok=True)
    write_csv(project / "customers.csv", ROWS)
    return ingest_csv(project, project / "customers.csv", schema(), data_role=role)["import_id"]


def _sql(project, statement, parameters=()):
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        changed = conn.execute(statement, parameters).rowcount
        conn.commit()
    finally:
        conn.close()
    assert changed >= 1, "the tamper statement changed nothing"


def _edit_manifest(project, **changes):
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        manifest = json.loads(conn.execute("SELECT manifest_json FROM imports").fetchone()[0])
    finally:
        conn.close()
    manifest.update(changes)
    _sql(project, "UPDATE imports SET manifest_json=?", (json.dumps(manifest),))


def _materialize(project, import_id):
    return materialize_instances(binding(), pack(), project, import_id)


SECOND = " WHERE source_record_number=3"


@pytest.mark.parametrize("statement, match", [
    ("UPDATE import_rows SET payload_json=replace(payload_json,'two@','evil@')" + SECOND,
     "does not match its row ID"),
    ("UPDATE import_rows SET payload_json=json_set(payload_json,'$.extra','x')" + SECOND,
     "does not match its row ID"),
    ("UPDATE import_rows SET source_record_number=30" + SECOND, "does not match its row ID"),
    ("UPDATE import_rows SET row_id='renamed'" + SECOND, "does not match its row ID"),
    ("UPDATE import_rows SET locator_json=json_set(locator_json,'$.source_registry_id','x')"
     + SECOND, "locator does not match"),
    ("UPDATE import_rows SET locator_json=json_set(locator_json,'$.note','x')" + SECOND,
     "locator does not match"),
    ("UPDATE import_rows SET payload_json='{not json'" + SECOND, "integrity check failed"),
    ("DELETE FROM import_rows" + SECOND, "row count differs"),
])
def test_materialization_refuses_a_changed_row(tmp_path, statement, match):
    import_id = _ingest(tmp_path)
    assert len(_materialize(tmp_path, import_id)) == 2
    _sql(tmp_path, statement)
    with pytest.raises(OntologyError, match=match):
        _materialize(tmp_path, import_id)


@pytest.mark.parametrize("changes", [
    {"data_role": "scenario_input"},
    {"dataset_id": "other"},
    {"file_sha256": "0" * 64},
    {"schema_fingerprint": "0" * 64},
    {"parser_version": "other"},
    {"source_registry_id": "tabular-" + "0" * 32},
    {"import_id": "0" * 64},
    {"data_role": None},
])
def test_materialization_refuses_a_changed_import_identity(tmp_path, changes):
    import_id = _ingest(tmp_path)
    _edit_manifest(tmp_path, **changes)
    with pytest.raises(OntologyError, match="snapshot integrity check failed"):
        _materialize(tmp_path, import_id)


def test_sealed_holdout_cannot_be_relabelled(tmp_path):
    import_id = _ingest(tmp_path, role="sealed_holdout")
    with pytest.raises(OntologyError, match="sealed_holdout"):
        _materialize(tmp_path, import_id)
    _edit_manifest(tmp_path, data_role="context")
    with pytest.raises(OntologyError, match="does not match its import ID"):
        _materialize(tmp_path, import_id)
    with pytest.raises(ScenarioInputError, match="does not match its import ID"):
        build_scenario_input(
            binding(), pack(), tmp_path, import_id,
            transformation_policy=None,
        )


def test_a_fully_rewritten_manifest_identity_is_still_refused(tmp_path):
    """Recomputing every stored identity field cannot keep the pinned import ID."""
    import_id = _ingest(tmp_path, role="sealed_holdout")
    conn = sqlite3.connect(tmp_path / "data" / "tabular.sqlite3")
    manifest = json.loads(conn.execute("SELECT manifest_json FROM imports").fetchone()[0])
    conn.close()
    key, _new_id = _import_identity(
        dataset_id=manifest["dataset_id"], file_sha256=manifest["file_sha256"],
        schema_fingerprint=manifest["schema_fingerprint"],
        parser_version=manifest["parser_version"], data_role="context",
    )
    _edit_manifest(
        tmp_path, data_role="context", idempotency_key=key,
        source_registry_id=_source_registry_id(
            manifest["dataset_id"], manifest["file_sha256"], "context"))
    with pytest.raises(OntologyError, match="does not match its import ID"):
        _materialize(tmp_path, import_id)


@pytest.fixture
def indexed(tmp_path):
    project = tmp_path / "project"
    import_id = _ingest(project)
    audit = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    store = OntologyObjectStore(project)
    pack_fp = store.register_pack(_pack(), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    privacy = {"purpose": "account support", "retention": "90 days"}

    def index():
        return store.materialize_binding(
            pack_fp, binding_fp, import_id, policy=_allow, audit=audit, **privacy)

    def refs():
        conn = sqlite3.connect(store.path)
        try:
            return conn.execute(
                "SELECT record_key, snapshot_row_id FROM ontology_object_refs "
                "ORDER BY snapshot_row_id").fetchall()
        finally:
            conn.close()

    def get(record_key):
        return store.get_object(
            pack_fp, "backup:Customer", "1.0.0", record_key, import_id,
            policy=_allow, audit=audit, **privacy)

    try:
        yield project, index, refs, get
    finally:
        audit.close()


def test_indexing_a_changed_row_stores_no_references(indexed):
    project, index, refs, _get = indexed
    _sql(project, "UPDATE import_rows SET payload_json=replace(payload_json,'two@','evil@')"
         + SECOND)
    with pytest.raises(OntologyError, match="does not match its row ID"):
        index()
    assert refs() == []


def _row(project, number):
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        return conn.execute(
            "SELECT row_id, payload_json FROM import_rows WHERE source_record_number=?",
            (number,)).fetchone()
    finally:
        conn.close()


def test_get_object_refuses_a_row_edited_after_indexing(indexed):
    project, index, refs, get = indexed
    index()
    row_id, _payload = _row(project, 3)
    record_key = next(key for key, pinned in refs() if pinned == row_id)
    assert get(record_key)["property_values"]["backup:Customer.email"] == "two@example.test"
    _sql(project, "UPDATE import_rows SET payload_json=replace(payload_json,'two@','evil@')"
         + SECOND)
    with pytest.raises(OntologyError, match="does not match its row ID"):
        get(record_key)


def _forge_consistent_row(project, number, old, new):
    """What a writer with database access and the algorithm can do."""
    row_id, payload_json = _row(project, number)
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    manifest = json.loads(conn.execute("SELECT manifest_json FROM imports").fetchone()[0])
    conn.close()
    payload = json.loads(payload_json.replace(old, new))
    forged = _row_id(
        dataset_id=manifest["dataset_id"], source_registry_id=manifest["source_registry_id"],
        file_sha256=manifest["file_sha256"],
        schema_fingerprint=manifest["schema_fingerprint"],
        payload=payload, source_record_number=number)
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "UPDATE import_rows SET row_id=?, payload_json=? WHERE row_id=?",
        (forged, json.dumps(payload), row_id))
    conn.commit()
    conn.close()
    return row_id


def test_pinned_row_id_refuses_a_self_consistent_forgery(indexed):
    project, index, refs, get = indexed
    index()
    old_row_id = _forge_consistent_row(project, 3, "two@", "evil@")
    record_key = next(key for key, pinned in refs() if pinned == old_row_id)
    with pytest.raises(OntologyError, match="was not found"):
        get(record_key)


def test_known_limit_forgery_before_any_pin_is_not_detected(tmp_path):
    """Row IDs are unkeyed. This records the limit so no one claims more than it does."""
    import_id = _ingest(tmp_path)
    _forge_consistent_row(tmp_path, 3, "two@", "evil@")
    values = [i["property_values"]["commerce:Customer.email"]
              for i in _materialize(tmp_path, import_id)]
    assert "evil@example.test" in values


def _manifest_for(**overrides):
    """A manifest that is self-consistent for whatever identity values it is given."""
    identity = {"dataset_id": "d", "file_sha256": "a" * 64, "schema_fingerprint": "b" * 64,
                "parser_version": "p", "data_role": "context", **overrides}
    _key, import_id = _import_identity(**identity)
    return {**identity, "import_id": import_id, "source_registry_id": _source_registry_id(
        identity["dataset_id"], identity["file_sha256"], identity["data_role"])}, import_id


def test_manifest_check_accepts_a_consistent_manifest():
    manifest, import_id = _manifest_for()
    verify_snapshot_manifest(manifest, import_id)


@pytest.mark.parametrize("field", ["import_id", "source_registry_id"])
def test_manifest_check_refuses_each_altered_binding_field_on_its_own(field):
    manifest, import_id = _manifest_for()
    manifest[field] = "other"
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot_manifest(manifest, import_id)


def test_manifest_check_refuses_a_non_text_identity_value():
    manifest, import_id = _manifest_for(parser_version=1)
    with pytest.raises(SnapshotIntegrityError, match="missing identity fields"):
        verify_snapshot_manifest(manifest, import_id)


@pytest.mark.parametrize("number", ["2", True, 2.0, None])
def test_row_check_refuses_a_non_integer_record_number(number):
    manifest, import_id = _manifest_for()
    facts = {key: manifest[key] for key in (
        "dataset_id", "source_registry_id", "file_sha256", "schema_fingerprint")}
    row = {
        "values": {"v": 1}, "source_record_number": number,
        "row_id": _row_id(**facts, payload={"v": 1}, source_record_number=number),
        "source_locator": {
            "source_registry_id": manifest["source_registry_id"],
            "file_sha256": manifest["file_sha256"], "source_record_number": number,
            "dataset_id": "d", "import_id": import_id},
    }
    with pytest.raises(SnapshotIntegrityError, match="record number"):
        verify_snapshot_row(row, manifest)

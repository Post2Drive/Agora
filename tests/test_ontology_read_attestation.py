"""Object reads and link source references require the import's ingest record."""

from __future__ import annotations

import hashlib
import json

import pytest

from agora import protection
from agora.identity import stable_record_key
from agora.ontology import OntologyError, OntologyObjectStore, parse_domain_pack
from agora.ontology import store as store_module
from agora.ontology.binding import load_binding
from agora.ontology.registry import pack_document
from agora.tabular import ingest_csv
from test_import_attestation import _import, _query, anchored  # noqa: F401
from test_ontology_binding import schema, write_csv
from test_ontology_store import _allow, _binding, _pack
from test_snapshot_row_integrity import ROWS, SECOND, _forge_consistent_row, _sql

PRIVACY = {"purpose": "customer-support", "retention": "30d"}
TYPE = ("backup:Customer", "1.0.0")
NO_RECORD = "no matching ingest record"


class World:
    def __init__(self, project, audit, pack=None, binding=None):
        self.project, self.audit = project, audit
        self.store = OntologyObjectStore(project)
        self.pack_fp = self.store.register_pack(pack or _pack(), policy=_allow, audit=audit)
        self.binding_fp = self.store.register_binding(
            self.pack_fp, binding or _binding(), policy=_allow, audit=audit)

    def index(self, import_id):
        return self.store.materialize_binding(
            self.pack_fp, self.binding_fp, import_id, policy=_allow, audit=self.audit, **PRIVACY)

    def get(self, import_id, key="C-1"):
        return self.store.get_object(
            self.pack_fp, *TYPE, stable_record_key("customers", key), import_id,
            policy=_allow, audit=self.audit, **PRIVACY)

    def query(self, import_id, filters=None, page_size=10):
        return self.store.query_objects(
            self.pack_fp, *TYPE, import_id, filters or {}, page_size, None,
            policy=_allow, audit=self.audit, **PRIVACY)

    def endpoint(self, import_id, key):
        return {"project_id": self.store.project_id, "pack_fingerprint": self.pack_fp,
                "type_id": TYPE[0], "type_version": TYPE[1], "import_id": import_id,
                "record_key": stable_record_key("customers", key)}

    def link(self, import_id, *cited):
        return self.store.add_link(
            self.pack_fp, "backup:knows", "1.0.0",
            self.endpoint(import_id, "C-1"), self.endpoint(import_id, "C-2"),
            "2026-01-01T00:00:00+00:00", None, "referral",
            {"kind": "source", "source_refs": list(cited)},
            policy=_allow, audit=self.audit)


def _cite(project, import_id):
    [(digest,)] = _query(
        project, "tabular.sqlite3",
        "SELECT file_sha256 FROM imports WHERE import_id=?", (import_id,))
    return {"import_id": import_id, "file_sha256": digest, "locator": "row:2"}


def _link_count(project):
    return _query(project, "ontology.sqlite3", "SELECT COUNT(*) FROM ontology_links")[0][0]


def _unrecorded_import(project, audit, monkeypatch, name="customers.csv"):
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    try:
        return ingest_csv(project, project / name, schema(), data_role="context")["import_id"]
    finally:
        monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)


@pytest.fixture
def indexed(anchored):  # noqa: F811
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    world = World(project, audit)
    assert world.index(import_id) == 2
    return world, import_id


def test_a_recorded_import_can_be_read_queried_and_cited(indexed):
    world, import_id = indexed
    assert world.get(import_id)["property_values"]["backup:Customer.email"] == ROWS[0][1]
    assert len(world.query(import_id)["objects"]) == 2
    assert world.link(import_id, _cite(world.project, import_id)).startswith("link-")


def test_references_pinned_from_an_unrecorded_import_cannot_be_read(
        anchored, monkeypatch):  # noqa: F811
    project, audit = anchored
    import_id = _unrecorded_import(project, audit, monkeypatch)
    world = World(project, audit)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    world.index(import_id)
    assert world.get(import_id)["record_key"]
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.get(import_id)
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.query(import_id)


# Neither change touches C-1's row ID, so only the whole-import digest sees it.
CHANGES = [
    "UPDATE imports SET created_at='2000-01-01T00:00:00+00:00'",
    "UPDATE import_rows SET record_key='forged'" + SECOND,
]


@pytest.mark.parametrize("statement", CHANGES)
def test_content_changed_after_indexing_stops_reads(indexed, statement):
    world, import_id = indexed
    _sql(world.project, statement)
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.get(import_id)
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.query(import_id)


def test_a_cited_import_without_a_record_cannot_support_a_link(indexed, monkeypatch):
    """The endpoints come from a recorded import; only the citation does not."""
    world, import_id = indexed
    # Citations are checked in import ID order, so make the unrecorded one sort last.
    for number in range(64):
        write_csv(world.project / "other.csv", [[f"C-{number + 9}", "nine@example.test"]])
        other = _unrecorded_import(world.project, world.audit, monkeypatch, "other.csv")
        if other > import_id:
            break
    assert other > import_id
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.link(import_id, _cite(world.project, other))
    # Every cited import is checked, not only the first.
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.link(import_id, _cite(world.project, import_id), _cite(world.project, other))
    assert _link_count(world.project) == 0


def test_a_cited_import_changed_after_ingest_cannot_support_a_link(indexed):
    world, import_id = indexed
    original = world.link(import_id, _cite(world.project, import_id))
    _forge_consistent_row(world.project, 3, "two@", "evil@")
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.link(import_id, _cite(world.project, import_id))
    with pytest.raises(OntologyError, match=NO_RECORD):
        world.store.supersede_link(
            world.pack_fp, original, world.endpoint(import_id, "C-1"),
            world.endpoint(import_id, "C-2"), "2026-02-01T00:00:00+00:00", None,
            "correction", {"kind": "source", "source_refs": [_cite(world.project, import_id)]},
            policy=_allow, audit=world.audit)
    assert _link_count(world.project) == 1


@pytest.mark.parametrize("read", [
    lambda world, import_id: world.get(import_id, "C-2"),
    lambda world, import_id: world.query(import_id),
    # The swapped row does not match, so it is never returned, but it decided that.
    lambda world, import_id: world.query(
        import_id, {"backup:Customer.email": {"op": "eq", "value": ROWS[0][1]}}),
], ids=["get", "query", "query-excluding-the-row"])
def test_a_row_swapped_in_only_while_reading_is_refused(indexed, monkeypatch, read):
    """Assumes the ontology store was also rewritten to pin the forged row ID."""
    world, import_id = indexed
    saved = _query(world.project, "tabular.sqlite3",
                   "SELECT row_id,payload_json FROM import_rows" + SECOND)[0]
    old_id = _forge_consistent_row(world.project, 3, "two@", "evil@")
    [(forged_id, forged_payload)] = _query(
        world.project, "tabular.sqlite3",
        "SELECT row_id,payload_json FROM import_rows" + SECOND)

    def put(values):
        _sql_unchecked(world.project, values)

    put(saved)
    _sql_ontology(world.project, forged_id, old_id)
    real = store_module.materialize_source_object

    def swapped(*args, **kwargs):
        if args[4] != forged_id:
            return real(*args, **kwargs)
        put((forged_id, forged_payload))
        try:
            return real(*args, **kwargs)
        finally:
            put(saved)

    monkeypatch.setattr(store_module, "materialize_source_object", swapped)
    with pytest.raises(OntologyError, match="rows changed between reading and verification"):
        read(world, import_id)


def _sql_unchecked(project, values):
    import sqlite3
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        assert conn.execute(
            "UPDATE import_rows SET row_id=?, payload_json=?" + SECOND, values).rowcount == 1
        conn.commit()
    finally:
        conn.close()


def _sql_ontology(project, new_id, old_id):
    import sqlite3
    conn = sqlite3.connect(project / "data" / "ontology.sqlite3")
    try:
        # What someone who can rewrite the ontology store would do: lift its guard.
        for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='ontology_object_refs'").fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        assert conn.execute(
            "UPDATE ontology_object_refs SET snapshot_row_id=? WHERE snapshot_row_id=?",
            (new_id, old_id)).rowcount == 1
        conn.commit()
    finally:
        conn.close()


def test_reads_validate_the_binding_against_the_recorded_manifest(
        anchored, monkeypatch):  # noqa: F811
    """The recorded manifest forbids this binding; one swapped in while reading allows it."""
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    weaker = json.loads(json.dumps(pack_document(_pack())))
    weaker.pop("fingerprint", None)
    for prop in weaker["property_types"]:
        if prop["property_id"] == "backup:Customer.email":
            prop["sensitivity"] = "internal"
    document = _binding().as_dict()
    document.pop("fingerprint", None)
    document["property_sensitivity"]["backup:Customer.email"] = "internal"
    world = World(project, audit, parse_domain_pack(weaker), load_binding(document))
    [(original,)] = _query(project, "tabular.sqlite3", "SELECT manifest_json FROM imports")
    changed = json.loads(original)
    changed["column_sensitivity"]["email"] = "internal"

    def swap(text):
        _sql(project, "UPDATE imports SET manifest_json=?", (text,))

    # References pinned without the check, as a rewritten ontology store could hold.
    swap(json.dumps(changed))
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    world.index(import_id)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    swap(original)
    real = store_module.materialize_source_object

    def swapped(*args, **kwargs):
        swap(json.dumps(changed))
        try:
            return real(*args, **kwargs)
        finally:
            swap(original)

    monkeypatch.setattr(store_module, "materialize_source_object", swapped)
    with pytest.raises(OntologyError, match="sensitivity downgrade"):
        world.get(import_id)
    with pytest.raises(OntologyError, match="sensitivity downgrade"):
        world.query(import_id)


def test_a_query_checks_the_ingest_record_once_per_page(indexed, monkeypatch):
    world, import_id = indexed
    calls = []
    real = store_module._import_content_attestation

    def counted(conn, wanted):
        calls.append(wanted)
        return real(conn, wanted)

    monkeypatch.setattr(store_module, "_import_content_attestation", counted)
    assert len(world.query(import_id)["objects"]) == 2
    assert calls == [import_id]


def test_several_citations_of_one_import_hash_it_once(indexed, monkeypatch):
    world, import_id = indexed
    calls = []
    real = store_module._import_content_attestation

    def counted(conn, wanted):
        calls.append(wanted)
        return real(conn, wanted)

    monkeypatch.setattr(store_module, "_import_content_attestation", counted)
    cite = _cite(world.project, import_id)
    world.link(import_id, cite, {**cite, "locator": "row:3"})
    assert calls == [import_id]

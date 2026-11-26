"""A source-backed link may only cite records that exist in the project's snapshots."""
import hashlib
import json
import sqlite3

import pytest

from agora.ontology import OntologyError
from agora.tabular import ingest_csv
from agora.identity import stable_record_key

from test_ontology_store import _SCHEMA, _allow, _binding, catalog  # noqa: F401
from agora.ontology import parse_domain_pack


def _pack_data():
    return {
        "pack_id": "ref-link-pack", "schema_version": "1.0.0",
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


@pytest.fixture
def linkable(catalog):  # noqa: F811
    project, store, audit, _, _ = catalog
    pack_fp = store.register_pack(parse_domain_pack(_pack_data()), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    source = project / "customers.csv"
    source.write_text(
        "customer_id,email\nC-1,one@example.test\nC-2,two@example.test\n", encoding="utf-8")
    import_id = ingest_csv(
        project, source, _SCHEMA, data_role="context", policy=_allow, audit=audit)["import_id"]
    store.materialize_binding(
        pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
        purpose="account support", retention="90 days")

    def endpoint(key):
        return {"project_id": store.project_id, "pack_fingerprint": pack_fp,
                "type_id": "backup:Customer", "type_version": "1.0.0",
                "import_id": import_id,
                "record_key": stable_record_key("customers", key)}

    def link(provenance, policy=_allow):
        return store.add_link(
            pack_fp, "backup:refers", "1.0.0", endpoint("C-1"), endpoint("C-2"),
            "2026-01-01T00:00:00+00:00", None, "referral", provenance,
            policy=policy, audit=audit)

    ref = {"import_id": import_id,
           "file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
           "locator": "row:2"}
    return project, store, pack_fp, ref, link, endpoint, audit


def _link_count(store):
    conn = sqlite3.connect(store.path)
    try:
        return conn.execute("SELECT COUNT(*) FROM ontology_links").fetchone()[0]
    finally:
        conn.close()


def _source(*refs):
    return {"kind": "source", "source_refs": list(refs)}


def _refused(linkable, provenance, message):
    store, link = linkable[1], linkable[4]
    before = _link_count(store)
    with pytest.raises(OntologyError, match=message):
        link(provenance)
    assert _link_count(store) == before


def _tamper(project, sql, params=()):
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def test_matching_source_ref_is_accepted(linkable):
    ref = linkable[3]
    assert linkable[4](_source(ref, {**ref, "locator": "row:3"})).startswith("link-")


def test_uppercase_hash_is_accepted(linkable):
    ref = linkable[3]
    assert linkable[4](_source({**ref, "file_sha256": ref["file_sha256"].upper()}))


def test_unknown_import_is_refused(linkable):
    _refused(linkable, _source({**linkable[3], "import_id": "import-never-ran"}),
             "missing or uncommitted import")


def test_wrong_hash_is_refused(linkable):
    _refused(linkable, _source({**linkable[3], "file_sha256": "a" * 64}),
             "does not match the cited import")


def test_every_ref_is_checked_not_only_the_first(linkable):
    ref = linkable[3]
    _refused(linkable, _source(ref, {**ref, "file_sha256": "a" * 64}),
             "does not match the cited import")


def test_uncommitted_import_is_refused(linkable):
    _tamper(linkable[0], "UPDATE imports SET status='failed' WHERE import_id=?",
            (linkable[3]["import_id"],))
    _refused(linkable, _source(linkable[3]), "missing or uncommitted import")


@pytest.mark.parametrize("locator", ["row:1", "row:4", "row:999999"])
def test_locator_outside_the_snapshot_is_refused(linkable, locator):
    _refused(linkable, _source({**linkable[3], "locator": locator}),
             "does not resolve to an accepted source record")


@pytest.mark.parametrize("locator", [
    "page 4", "row:0", "row:02", "row:-2", "row:2.0", "row: 2", "row:2\n",
    "ROW:2", "row:" + "9" * 30,
])
def test_malformed_locator_is_refused(linkable, locator):
    _refused(linkable, _source({**linkable[3], "locator": locator}), "must have the form row:")


@pytest.mark.parametrize("import_id", ["latest", " padded "])
def test_inexact_import_id_is_refused(linkable, import_id):
    _refused(linkable, _source({**linkable[3], "import_id": import_id}),
             "exact import identifier")


def test_incomplete_snapshot_is_refused(linkable):
    _tamper(linkable[0],
            "INSERT INTO import_rows(row_id, record_key, import_id, source_record_number,"
            " payload_json, locator_json) VALUES('extra','extra',?,99,'{}','{}')",
            (linkable[3]["import_id"],))
    _refused(linkable, _source(linkable[3]), "incomplete import snapshot")


@pytest.mark.parametrize("manifest", ["not json", "[]", json.dumps({"accepted_records": "2"})])
def test_invalid_import_manifest_is_refused(linkable, manifest):
    _tamper(linkable[0], "UPDATE imports SET manifest_json=? WHERE import_id=?",
            (manifest, linkable[3]["import_id"]))
    _refused(linkable, _source(linkable[3]), "source_ref")


def test_missing_snapshot_database_is_refused(linkable):
    (linkable[0] / "data" / "tabular.sqlite3").unlink()
    _refused(linkable, _source(linkable[3]), "require the project tabular snapshot database")
    assert not (linkable[0] / "data" / "tabular.sqlite3").exists()


def test_too_many_refs_are_refused(linkable):
    _refused(linkable, _source(*[linkable[3]] * 101), "at most 100")


@pytest.mark.parametrize("kind", ["manual_assertion", "derived"])
def test_non_source_provenance_cannot_carry_source_refs(linkable, kind):
    _refused(linkable, {"kind": kind, "source_refs": [linkable[3]]},
             "only source provenance may carry source_refs")


def test_superseding_link_is_checked_too(linkable):
    _, store, pack_fp, ref, link, endpoint, audit = linkable
    original = link(_source(ref))
    with pytest.raises(OntologyError, match="does not match the cited import"):
        store.supersede_link(
            pack_fp, original, endpoint("C-1"), endpoint("C-2"),
            "2026-02-01T00:00:00+00:00", None, "correction",
            _source({**ref, "file_sha256": "a" * 64}), policy=_allow, audit=audit)
    assert _link_count(store) == 1


def test_policy_sees_the_cited_import(linkable):
    seen = []

    def policy(operation, resource):
        seen.append((operation, list(resource.get("resource_ids", []))))
        return _allow(operation, resource)

    ref = linkable[3]
    linkable[4](_source(ref), policy=policy)
    writes = [ids for operation, ids in seen if operation == "ontology_write"]
    # link endpoints already name this import once each; the citation adds one more
    assert writes and all(ids.count(ref["import_id"]) == 3 for ids in writes)


def test_denied_writer_learns_nothing_about_imports(linkable):
    def deny_writes(operation, resource):
        decision = _allow(operation, resource)
        return {**decision, "decision": "deny"} if operation == "ontology_write" else decision

    messages = []
    for import_id in (linkable[3]["import_id"], "import-never-ran"):
        with pytest.raises(OntologyError) as caught:
            linkable[4](_source({**linkable[3], "import_id": import_id}), policy=deny_writes)
        messages.append(str(caught.value))
    assert messages[0] == messages[1] == "policy denied ontology catalog access"

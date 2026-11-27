"""Object references may only be indexed from content recorded at ingest."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

import pytest

from agora import protection, tabular
from agora.audit_anchor import AnchorStore, bootstrap_anchor, open_anchored_audit
from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, parse_domain_pack
from agora.ontology import store as store_module
from agora.ontology.binding import load_binding
from agora.ontology.registry import pack_document
from agora.pilot import default_identities
from agora.principal import SyntheticFixtureAdapter, principal_policy
from agora import scenario_inputs
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import (
    TabularIngestError, import_attestation_event_id,
    import_content_attestation, ingest_csv,
)
from test_ontology_binding import schema, write_csv
from test_ontology_store import _allow, _binding, _pack
from test_snapshot_row_integrity import ROWS, SECOND, _forge_consistent_row, _sql

CHAIN_ID = "attestation-test-chain"


@pytest.fixture
def anchored(tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    project = tmp_path / "project"
    project.mkdir()
    write_csv(project / "customers.csv", ROWS)
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    try:
        bootstrap_anchor(chain, AnchorStore(tmp_path / "anchor.jsonl", CHAIN_ID),
                         performed_by="test-maintainer")
    finally:
        chain.close()
    with open_anchored_audit(tmp_path / "chain.sqlite3", tmp_path / "anchor.jsonl", CHAIN_ID) as audit:
        yield project, audit


def _import(project, audit, **extra):
    return ingest_csv(project, project / "customers.csv", schema(), data_role="context",
                      audit=audit, **extra)


def _indexer(project, audit):
    store = OntologyObjectStore(project)
    pack_fp = store.register_pack(_pack(), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)

    def index(import_id):
        return store.materialize_binding(
            pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
            purpose="customer-support", retention="30d")

    return index


def _query(project, database, sql, parameters=()):
    conn = sqlite3.connect(project / "data" / database)
    try:
        return conn.execute(sql, parameters).fetchall()
    finally:
        conn.close()


def _refs(project):
    return _query(project, "ontology.sqlite3", "SELECT record_key FROM ontology_object_refs")


def _statuses(project):
    return [row[0] for row in _query(project, "tabular.sqlite3", "SELECT status FROM imports")]


def _attestation(project, import_id):
    conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
    try:
        return import_content_attestation(conn, import_id)
    finally:
        conn.close()


def _events(audit):
    rows = audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq").fetchall()
    return [e for e in (json.loads(r[0]) for r in rows)
            if e["event_type"] == "tabular_import_attested"]


def test_ingest_records_the_digest_and_indexing_accepts_it(anchored):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    current = _attestation(project, import_id)
    [event] = _events(audit)
    assert event["content_hash"] == current["content_sha256"]
    assert event["count"] == 2
    assert event["resource_ids"] == ["customers", import_id]
    assert audit.find_event(
        import_attestation_event_id(import_id, current["content_sha256"])) is not None
    assert _indexer(project, audit)(import_id) == 2
    assert len(_refs(project)) == 2


def test_forgery_before_any_reference_is_pinned_is_now_refused(anchored):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    index = _indexer(project, audit)
    _forge_consistent_row(project, 3, "two@", "evil@")
    with pytest.raises(OntologyError, match="no matching ingest record"):
        index(import_id)
    assert _refs(project) == []


@pytest.mark.parametrize("statement", [
    "UPDATE imports SET manifest_json=json_set(manifest_json,'$.column_sensitivity.email','public')",
    "UPDATE imports SET created_at='2000-01-01T00:00:00+00:00'",
    "UPDATE import_rows SET record_key='forged'" + SECOND,
])
def test_changed_content_that_row_ids_do_not_cover_is_refused(anchored, statement):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    index = _indexer(project, audit)
    _sql(project, statement)
    with pytest.raises(OntologyError, match="no matching ingest record"):
        index(import_id)
    assert _refs(project) == []


def test_an_import_made_without_a_record_cannot_be_indexed(anchored, monkeypatch):
    project, audit = anchored
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    import_id = ingest_csv(project, project / "customers.csv", schema(),
                           data_role="context")["import_id"]
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    # Re-importing the same bytes must not bless whatever is stored now.
    assert _import(project, audit)["idempotent"] is True
    assert _events(audit) == []
    with pytest.raises(OntologyError, match="no matching ingest record"):
        _indexer(project, audit)(import_id)
    assert _refs(project) == []


@pytest.mark.parametrize("change", [
    {"event_type": "ontology_operation_authorized"},
    {"content_hash": "0" * 64},
])
def test_a_record_of_the_wrong_kind_or_digest_is_refused(anchored, monkeypatch, change):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    index = _indexer(project, audit)
    real = audit.find_event
    monkeypatch.setattr(audit, "find_event", lambda event_id: {**real(event_id), **change})
    with pytest.raises(OntologyError, match="no matching ingest record"):
        index(import_id)
    assert _refs(project) == []


def test_an_unanchored_tail_is_refused_at_indexing(anchored, monkeypatch):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    index = _indexer(project, audit)
    real = store_module._import_content_attestation

    def attest_then_break(conn, wanted):
        audit.chain.append({"event_id": "unanchored", "event_type": "x"})
        return real(conn, wanted)

    monkeypatch.setattr(store_module, "_import_content_attestation", attest_then_break)
    with pytest.raises(OntologyError, match="could not be verified"):
        index(import_id)
    assert _refs(project) == []


def _swap_around_indexing(monkeypatch, mutate, restore):
    """Change the database for the indexing read only, then restore it."""
    real = store_module.iter_source_object_refs

    def swapped(*args, **kwargs):
        def generate():
            mutate()
            try:
                yield from real(*args, **kwargs)
            finally:
                restore()
        return generate()

    monkeypatch.setattr(store_module, "iter_source_object_refs", swapped)


def test_rows_swapped_in_only_while_indexing_are_refused(anchored, monkeypatch):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    index = _indexer(project, audit)
    saved = _query(project, "tabular.sqlite3",
                   "SELECT row_id,payload_json FROM import_rows" + SECOND)[0]

    def restore():
        conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE import_rows SET row_id=?, payload_json=?" + SECOND, saved)
        conn.commit()
        conn.close()

    _swap_around_indexing(monkeypatch,
                          lambda: _forge_consistent_row(project, 3, "two@", "evil@"), restore)
    with pytest.raises(OntologyError, match="rows changed between reading and verification"):
        index(import_id)
    assert _refs(project) == []


def test_a_manifest_swapped_in_only_while_indexing_is_refused(anchored, monkeypatch):
    """The recorded manifest forbids this binding; a temporary one would allow it."""
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
    store = OntologyObjectStore(project)
    pack_fp = store.register_pack(
        parse_domain_pack(weaker), policy=_allow, audit=audit)
    binding_fp = store.register_binding(
        pack_fp, load_binding(document), policy=_allow, audit=audit)

    def index():
        return store.materialize_binding(
            pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
            purpose="customer-support", retention="30d")

    with pytest.raises(OntologyError, match="sensitivity downgrade"):
        index()
    [(original,)] = _query(project, "tabular.sqlite3", "SELECT manifest_json FROM imports")
    changed = json.loads(original)
    changed["column_sensitivity"]["email"] = "internal"
    _swap_around_indexing(
        monkeypatch,
        lambda: _sql(project, "UPDATE imports SET manifest_json=?", (json.dumps(changed),)),
        lambda: _sql(project, "UPDATE imports SET manifest_json=?", (original,)))
    with pytest.raises(OntologyError, match="sensitivity downgrade"):
        index()
    assert _refs(project) == []


@pytest.mark.parametrize("make_audit", [lambda audit: None, lambda audit: audit.chain])
def test_protected_ingest_requires_an_anchored_writer_before_reading(anchored, make_audit):
    project, audit = anchored
    with pytest.raises(TabularIngestError) as caught:
        ingest_csv(project, project / "does-not-exist.csv", schema(), data_role="context",
                   audit=make_audit(audit))
    assert caught.value.code == "AUDIT_REQUIRED"
    assert not (project / "data" / "tabular.sqlite3").exists()


class _FailingAudit:
    def append(self, event):
        raise OSError("disk full")


def test_a_failed_record_imports_nothing_and_a_retry_succeeds(anchored, monkeypatch):
    project, audit = anchored
    real = audit.append
    monkeypatch.setattr(audit, "append", _FailingAudit().append)
    with pytest.raises(TabularIngestError) as caught:
        _import(project, audit)
    assert caught.value.code == "IMPORT_ATTESTATION_FAILED"
    assert _statuses(project) == ["failed"]
    assert _query(project, "tabular.sqlite3", "SELECT 1 FROM import_rows") == []
    monkeypatch.setattr(audit, "append", real)
    result = _import(project, audit)
    assert result["idempotent"] is False
    assert _indexer(project, audit)(result["import_id"]) == 2


def test_a_trigger_that_rewrites_inserted_rows_is_not_attested(anchored):
    project, audit = anchored
    (project / "data").mkdir()
    conn = tabular._db(project)
    tabular._init_db(conn)
    conn.executescript(
        "CREATE TRIGGER rewrite AFTER INSERT ON import_rows BEGIN "
        "UPDATE import_rows SET payload_json=replace(payload_json,'two@','evil@') "
        "WHERE row_id=NEW.row_id; END;")
    conn.close()
    with pytest.raises(TabularIngestError) as caught:
        _import(project, audit)
    assert caught.value.code == "SNAPSHOT_WRITE_MISMATCH"
    assert _events(audit) == []
    assert _statuses(project) == ["failed"]


def test_unprotected_ingest_with_a_plain_writer_still_records(tmp_path):
    write_csv(tmp_path / "customers.csv", ROWS)
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    try:
        import_id = ingest_csv(tmp_path, tmp_path / "customers.csv", schema(),
                               data_role="context", audit=chain)["import_id"]
        current = _attestation(tmp_path, import_id)
        assert chain.find_event(
            import_attestation_event_id(import_id, current["content_sha256"])) is not None
    finally:
        chain.close()


def test_known_limit_a_writer_of_both_stores_can_still_forge(anchored):
    """The chain is local and unsigned: whoever can append to it can attest a forgery."""
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    _forge_consistent_row(project, 3, "two@", "evil@")
    forged = _attestation(project, import_id)
    audit.append(tabular.import_attestation_event(
        "customers", import_id, forged["content_sha256"], forged["row_count"]))
    assert _indexer(project, audit)(import_id) == 2


def _transformation_policy():
    return {"policy_id": "attestation-transform", "purpose": "customer-support", "retention": "30d",
            "reviewer": "governance-test", "approved_at": "2026-11-27T00:00:00Z",
            "audit_reference": "AUD-1", "authorized_property_ids": []}


def _scenario(project, import_id, audit, policy=_allow):
    return build_scenario_input(
        _binding(), _pack(), project, import_id, policy=policy, audit=audit,
        transformation_policy=_transformation_policy())


def test_scenario_input_is_built_from_a_recorded_import(anchored):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    built = _scenario(project, import_id, audit)
    assert len(built["instances"]) == 2
    assert built["manifest"]["import_id"] == import_id


def test_scenario_input_refuses_a_consistently_forged_row(anchored):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    _forge_consistent_row(project, 3, "two@", "evil@")
    with pytest.raises(ScenarioInputError, match="no matching ingest record"):
        _scenario(project, import_id, audit)


def test_scenario_input_refuses_an_import_made_without_a_record(anchored, monkeypatch):
    project, audit = anchored
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    import_id = ingest_csv(project, project / "customers.csv", schema(),
                           data_role="context")["import_id"]
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    with pytest.raises(ScenarioInputError, match="no matching ingest record"):
        _scenario(project, import_id, audit)


@pytest.mark.parametrize("make_audit", [lambda audit: None, lambda audit: audit.chain])
def test_protected_scenario_input_requires_an_anchored_writer_before_reading(anchored, make_audit):
    project, audit = anchored
    # No snapshot database exists, so any read would report that instead.
    with pytest.raises(ScenarioInputError, match="requires an anchored audit writer"):
        _scenario(project, "import-never-made", make_audit(audit))


def test_scenario_input_refuses_rows_swapped_in_only_while_reading(anchored, monkeypatch):
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    saved = _query(project, "tabular.sqlite3",
                   "SELECT row_id,payload_json FROM import_rows" + SECOND)[0]
    real = scenario_inputs.materialize_instances

    def swapped(*args, **kwargs):
        _forge_consistent_row(project, 3, "two@", "evil@")
        try:
            return real(*args, **kwargs)
        finally:
            conn = sqlite3.connect(project / "data" / "tabular.sqlite3")
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("UPDATE import_rows SET row_id=?, payload_json=?" + SECOND, saved)
            conn.commit()
            conn.close()

    monkeypatch.setattr(scenario_inputs, "materialize_instances", swapped)
    with pytest.raises(ScenarioInputError, match="rows changed between reading and verification"):
        _scenario(project, import_id, audit)


def test_scenario_input_refuses_a_manifest_swapped_in_for_its_first_read(anchored, monkeypatch):
    """The package takes its data role from that read, so it must be the recorded one."""
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    [(original,)] = _query(project, "tabular.sqlite3", "SELECT manifest_json FROM imports")
    changed = json.loads(original)
    changed["data_role"] = "scenario_input"
    real = scenario_inputs._read_snapshot_metadata

    def swapped(*args):
        _sql(project, "UPDATE imports SET manifest_json=?", (json.dumps(changed),))
        try:
            return real(*args)
        finally:
            _sql(project, "UPDATE imports SET manifest_json=?", (original,))

    monkeypatch.setattr(scenario_inputs, "_read_snapshot_metadata", swapped)
    with pytest.raises(ScenarioInputError, match="manifest changed between reading"):
        _scenario(project, import_id, audit)


@pytest.mark.protected_defaults
def test_with_production_protections_an_operator_can_import_and_index(tmp_path):
    now = datetime.now(timezone.utc)
    identities = default_identities(now)
    operator = principal_policy(
        SyntheticFixtureAdapter(identities).issue("operator"),
        required_role="operator", now=now)
    project = tmp_path / identities["operator"]["project_ids"][0]
    project.mkdir()
    write_csv(project / "customers.csv", ROWS)
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    try:
        bootstrap_anchor(chain, AnchorStore(tmp_path / "anchor.jsonl", CHAIN_ID),
                         performed_by="test-maintainer")
    finally:
        chain.close()
    with open_anchored_audit(
        tmp_path / "chain.sqlite3", tmp_path / "anchor.jsonl", CHAIN_ID
    ) as audit:
        import_id = ingest_csv(project, project / "customers.csv", schema(),
                               data_role="context", policy=operator, audit=audit)["import_id"]
        store = OntologyObjectStore(project)
        pack_fp = store.register_pack(_pack(), policy=operator, audit=audit)
        binding_fp = store.register_binding(pack_fp, _binding(), policy=operator, audit=audit)
        assert store.materialize_binding(
            pack_fp, binding_fp, import_id, policy=operator, audit=audit,
            purpose="customer-support", retention="30d") == 2
        built = _scenario(project, import_id, audit, policy=operator)
        assert len(built["instances"]) == 2

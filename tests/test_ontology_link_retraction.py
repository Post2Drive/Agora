"""A link can be withdrawn without inventing a replacement, and nothing is rewritten."""
import hashlib
import shutil
import sqlite3

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore
from agora.tabular import ingest_csv

from test_ontology_link_cardinality import _JAN, _MAR, graph  # noqa: F401
from test_ontology_link_source_refs import linkable  # noqa: F401
from test_ontology_store import _SCHEMA, _allow, _attested, catalog  # noqa: F401

_MANUAL = {"kind": "manual_assertion"}


def _retract(graph, link_id, policy=_allow, reason="entered in error", provenance=_MANUAL):
    store, audit = graph[0], graph[5]
    return store.retract_link(
        _pack_of(store), link_id, reason, provenance, policy=policy, audit=audit)


def _pack_of(store):
    return _query(store, "SELECT pack_fingerprint FROM ontology_links LIMIT 1")[0][0]


def _query(store, statement, parameters=()):
    conn = sqlite3.connect(store.path)
    try:
        return conn.execute(statement, parameters).fetchall()
    finally:
        conn.close()


def _links(graph, name, **options):
    store, audit = graph[0], graph[5]
    return store.get_links(
        _pack_of(store), f"backup:{name}", "1.0.0", policy=_allow, audit=audit, **options)


def _raw(store, *statements, drop=()):
    """Edit the database directly, restoring any trigger dropped to do it."""
    conn = sqlite3.connect(store.path)
    try:
        saved = [conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
                 for name in drop]
        for name in drop:
            conn.execute(f"DROP TRIGGER {name}")
        for statement in statements:
            conn.execute(statement)
        for sql in saved:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _insert_retraction(link_id, at="2026-05-01T00:00:00.000000Z", actor="someone",
                       reason="why", provenance='{"kind":"manual_assertion"}'):
    return ("INSERT INTO ontology_link_retractions VALUES "
            f"('{link_id}', '{at}', '{actor}', '{reason}', '{provenance}')")


def test_retracted_link_leaves_the_active_set_but_stays_on_record(graph):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    before = _query(graph[0], "SELECT * FROM ontology_links")
    assert [(x["status"], x["retraction"]) for x in _links(graph, "many_to_many")] == [("active", None)]

    _retract(graph, link, reason="  entered in error  ")

    assert _links(graph, "many_to_many") == []
    [record] = _links(graph, "many_to_many", include_superseded=True)
    assert record["link_id"] == link and record["status"] == "retracted"
    assert record["retraction"]["reason"] == "entered in error"
    assert record["retraction"]["actor_id"] == "ontology-test-operator"
    assert record["retraction"]["provenance"] == _MANUAL
    assert record["retraction"]["retracted_at"] >= record["created_at"]
    assert _query(graph[0], "SELECT * FROM ontology_links") == before
    assert graph[3]()["ok"] is True


@pytest.mark.parametrize("name", ("one_to_one", "one_to_many"))
def test_retraction_frees_the_cardinality_slot(graph, name):
    link = graph[1](name, (1, "C-1"), (1, "C-3"))
    with pytest.raises(OntologyError, match="cardinality"):
        graph[1](name, (1, "C-2"), (1, "C-3"))
    _retract(graph, link)
    graph[1](name, (1, "C-2"), (1, "C-3"))
    assert len(_links(graph, name)) == 1


def test_retraction_clears_a_stored_conflict_that_had_no_truthful_replacement(graph):
    store = graph[0]
    first = graph[1]("one_to_many", (1, "C-1"), (1, "C-3"))
    # A conflict stored before cardinality followed the stable object.
    columns = [row[1] for row in _query(store, "PRAGMA table_info(ontology_links)")]
    selected = ", ".join("'link-legacy'" if c == "link_id" else c for c in columns)
    _raw(store, f"INSERT INTO ontology_links({', '.join(columns)}) "
                f"SELECT {selected} FROM ontology_links WHERE link_id='{first}'")
    assert graph[3]()["link_cardinality_conflict_count"] == 2

    _retract(graph, "link-legacy")

    report = graph[3]()
    assert report["link_cardinality"] == "ok"
    assert report["link_cardinality_conflict_count"] == 0


def test_a_retracted_link_cannot_be_retracted_again_or_superseded(graph):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    _retract(graph, link)
    with pytest.raises(OntologyError, match="already retracted"):
        _retract(graph, link)
    with pytest.raises(OntologyError, match="retracted link cannot be superseded"):
        graph[2](link, (1, "C-1"), (1, "C-3"))
    assert _query(graph[0], "SELECT COUNT(*) FROM ontology_links") == [(1,)]
    assert _query(graph[0], "SELECT COUNT(*) FROM ontology_link_retractions") == [(1,)]


def test_a_superseded_link_cannot_be_retracted_and_stays_dead_after_its_successor_is(graph):
    old = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    new = graph[2](old, (1, "C-1"), (1, "C-4"))
    with pytest.raises(OntologyError, match="superseded link cannot be retracted"):
        _retract(graph, old)
    _retract(graph, new)
    assert _links(graph, "many_to_many") == []
    history = {x["link_id"]: x["status"]
               for x in _links(graph, "many_to_many", include_superseded=True)}
    assert history == {old: "superseded", new: "retracted"}


@pytest.mark.parametrize("name", ("ontology_link_retractions_no_update",
                                  "ontology_link_retractions_no_delete"))
def test_the_database_keeps_retractions_immutable(graph, name):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    _retract(graph, link)
    statement = ("UPDATE ontology_link_retractions SET reason='x'" if name.endswith("update")
                 else "DELETE FROM ontology_link_retractions")
    with pytest.raises(sqlite3.IntegrityError, match="retractions are immutable"):
        _raw(graph[0], statement)


def test_the_database_itself_refuses_both_mixed_states(graph):
    store = graph[0]
    old = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    new = graph[2](old, (1, "C-1"), (1, "C-4"))
    with pytest.raises(sqlite3.IntegrityError, match="superseded ontology link cannot be retracted"):
        _raw(store, _insert_retraction(old))
    _retract(graph, new)
    columns = [row[1] for row in _query(store, "PRAGMA table_info(ontology_links)")]
    replaced = {"link_id": "'link-late'", "supersedes_link_id": f"'{new}'"}
    selected = ", ".join(replaced.get(c, c) for c in columns)
    with pytest.raises(sqlite3.IntegrityError, match="retracted ontology link cannot be superseded"):
        _raw(store, f"INSERT INTO ontology_links({', '.join(columns)}) "
                    f"SELECT {selected} FROM ontology_links WHERE link_id='{new}'")


@pytest.mark.parametrize("bad,message", [
    ({"at": "not-a-time"}, "retracted_at"),
    ({"actor": " "}, "no actor identity"),
    ({"reason": " "}, "retraction has no reason"),
    ({"provenance": "{"}, "not valid JSON"),
    ({"provenance": '{"kind":"rumour"}'}, "kind is invalid"),
    ({"provenance": '{"kind":"source"}'}, "no source references"),
])
def test_verification_refuses_a_malformed_stored_retraction(graph, bad, message):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    _raw(graph[0], _insert_retraction(link, **bad))
    with pytest.raises(OntologyError, match=message):
        graph[3]()


def test_verification_refuses_a_link_that_is_both_retracted_and_superseded(graph):
    old = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    graph[2](old, (1, "C-1"), (1, "C-4"))
    _raw(graph[0], _insert_retraction(old), drop=("ontology_link_retractions_active_only",))
    with pytest.raises(OntologyError, match="both retracted and superseded"):
        graph[3]()


@pytest.mark.parametrize("reason,provenance,message", [
    ("", _MANUAL, "reason and provenance"),
    ("why", {}, "reason and provenance"),
    ("why", {"kind": "rumour"}, "provenance kind"),
    ("why", {"kind": "manual_assertion", "source_refs": []}, "only source provenance"),
    ("why", {"kind": "source"}, "exact source_refs"),
])
def test_retraction_needs_a_reason_and_valid_provenance(graph, reason, provenance, message):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    with pytest.raises(OntologyError, match=message):
        _retract(graph, link, reason=reason, provenance=provenance)
    assert [x["status"] for x in _links(graph, "many_to_many")] == ["active"]


def test_unknown_link_and_wrong_pack_are_refused(graph):
    store, audit = graph[0], graph[5]
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    with pytest.raises(OntologyError, match="link to retract was not found"):
        _retract(graph, "link-missing")
    with pytest.raises(OntologyError, match="link to retract was not found"):
        store.retract_link("0" * 64, link, "why", _MANUAL, policy=_allow, audit=audit)
    with pytest.raises(OntologyError, match="canonical string"):
        _retract(graph, f" {link}")


def _recording(decide):
    seen = []

    def policy(operation, resource):
        seen.append((operation, resource["source_sensitivity"], list(resource["resource_ids"])))
        return decide(operation, resource, len(seen))

    return policy, seen


def test_a_denied_caller_cannot_probe_which_links_exist(graph):
    graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    deny, _ = _recording(lambda o, r, n: {**_allow(o, r), "decision": "deny"})
    with pytest.raises(OntologyError, match="policy denied"):
        _retract(graph, "link-missing", policy=deny)


def test_retraction_is_authorized_at_the_endpoints_sensitivity(graph):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    deny_classified, seen = _recording(
        lambda o, r, n: _allow(o, r) if r["source_sensitivity"] == "internal"
        else {**_allow(o, r), "decision": "deny"})
    with pytest.raises(OntologyError, match="policy denied"):
        _retract(graph, link, policy=deny_classified)
    last = seen[-1]
    assert last[0] == "ontology_write" and last[1] in {"personal", "sensitive"}
    assert link in last[2] and "backup:many_to_many" in last[2]
    assert [x["status"] for x in _links(graph, "many_to_many")] == ["active"]


def test_retraction_needs_a_named_actor(graph):
    link = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))

    def anonymous(operation, resource):
        return {**_allow(operation, resource), "subject_id": "unknown"}

    with pytest.raises(OntologyError, match="principal-bound"):
        _retract(graph, link, policy=anonymous)
    assert [x["status"] for x in _links(graph, "many_to_many")] == ["active"]


def test_traversal_labels_each_link_as_of_the_first_page(graph):
    store, audit = graph[0], graph[5]
    ids = sorted(graph[1]("many_to_many", (1, "C-1"), (1, f"C-{n}")) for n in (2, 3, 4))
    source = _links(graph, "many_to_many")[0]["source"]

    def page(cursor):
        return store.traverse_links(
            _pack_of(store), "backup:many_to_many", "1.0.0", source, source["import_id"],
            1, cursor, direction="out", policy=_allow, audit=audit)

    _retract(graph, ids[0])
    first = page(None)
    assert [(x["link_id"], x["status"]) for x in first["links"]] == [(ids[0], "retracted")]
    assert first["links"][0]["retraction"]["reason"] == "entered in error"
    _retract(graph, ids[1])
    second = page(first["next_cursor"])
    # Retracted after the first page: the later page keeps the same point in time.
    assert [(x["link_id"], x["status"], x["retraction"]) for x in second["links"]] == [
        (ids[1], "active", None)]
    assert page(None)["links"][0]["status"] == "retracted"


def test_traversal_labels_superseded_links_as_of_the_first_page(graph):
    store, audit = graph[0], graph[5]
    ids = sorted(graph[1]("many_to_many", (1, "C-1"), (1, f"C-{n}")) for n in (2, 3))
    source = _links(graph, "many_to_many")[0]["source"]

    def page(cursor):
        return store.traverse_links(
            _pack_of(store), "backup:many_to_many", "1.0.0", source, source["import_id"],
            1, cursor, direction="out", policy=_allow, audit=audit)

    first = page(None)
    graph[2](ids[1], (1, "C-1"), (1, "C-4"), start=_MAR)
    assert [(x["link_id"], x["status"]) for x in page(first["next_cursor"])["links"]] == [
        (ids[1], "active")]
    found, cursor = {}, None
    while True:
        current = page(cursor)
        found.update({x["link_id"]: x["status"] for x in current["links"]})
        cursor = current["next_cursor"]
        if cursor is None:
            break
    assert len(found) == 3 and found[ids[1]] == "superseded" and found[ids[0]] == "active"
    [old] = [x for x in _links(graph, "many_to_many", include_superseded=True)
             if x["link_id"] == ids[1]]
    assert old["status"] == "superseded"


def _source_retraction(linkable):  # noqa: F811
    """A manual link retracted on the evidence of a second import nothing else cites."""
    project, store, pack_fp, _, link, _, audit = linkable
    link_id = link(_MANUAL)
    evidence = project / "evidence.csv"
    evidence.write_text("customer_id,email\nC-7,proof@example.test\n", encoding="utf-8")
    import_id = ingest_csv(
        project, evidence, _SCHEMA, data_role="context", policy=_allow, audit=audit)["import_id"]
    ref = {"import_id": import_id,
           "file_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(), "locator": "row:2"}

    def retract(source_ref, policy=_allow):
        store.retract_link(
            pack_fp, link_id, "record shows otherwise",
            {"kind": "source", "source_refs": [source_ref]}, policy=policy, audit=audit)

    return project, store, audit, ref, retract


@pytest.mark.parametrize("change,message", [
    ({"import_id": "import-missing"}, "missing or uncommitted"),
    ({"file_sha256": "0" * 64}, "does not match the cited import"),
    ({"locator": "row:99"}, "does not resolve"),
])
def test_a_source_backed_retraction_checks_its_citations(linkable, change, message):
    _, store, _, ref, retract = _source_retraction(linkable)
    with pytest.raises(OntologyError, match=message):
        retract({**ref, **change})
    assert _query(store, "SELECT COUNT(*) FROM ontology_link_retractions") == [(0,)]


def test_the_cited_import_is_part_of_what_the_policy_decides_on(linkable):
    _, _, _, ref, retract = _source_retraction(linkable)
    policy, seen = _recording(lambda o, r, n: _allow(o, r))
    retract(ref, policy=policy)
    writes = [ids for operation, _, ids in seen if operation == "ontology_write"]
    assert len(writes) == 2 and all(ref["import_id"] in ids for ids in writes)


def _copy_for_restore(project, backup, tmp_path, name):
    target = tmp_path / name / project.name
    (target / "data").mkdir(parents=True)
    for item in (backup, project / "data" / "tabular.sqlite3"):
        shutil.copyfile(item, target / "data" / item.name)
    return target


def _restore(target, backup, attested):
    audit = AuditChainStore(target / "data" / "audit_chain.sqlite3")
    try:
        store = OntologyObjectStore(target)
        store.restore(target / "data" / backup.name, **attested, policy=_allow, audit=audit)
        return store, store.verify_integrity(policy=_allow, audit=audit)
    finally:
        audit.close()


def test_backup_attests_the_evidence_a_retraction_cites(linkable, tmp_path):
    project, store, audit, ref, retract = _source_retraction(linkable)
    retract(ref)
    backup = project / "data" / "retracted.backup.sqlite3"
    store.backup(backup, policy=_allow, audit=audit)
    attested = _attested(store, backup, audit)
    manifest = attested["dependency_manifest"]
    assert manifest["ontology_schema_version"] == 4
    assert ref["import_id"] in {x["import_id"] for x in manifest["source_import_attestations"]}
    assert ref["import_id"] in {x["import_id"] for x in manifest["link_source_references"]}

    tampered = _copy_for_restore(project, backup, tmp_path, "tampered")
    conn = sqlite3.connect(tampered / "data" / "tabular.sqlite3")
    conn.execute("UPDATE import_rows SET payload_json=replace(payload_json,'proof@','forged@')")
    conn.commit()
    conn.close()
    with pytest.raises(OntologyError, match="content does not match"):
        _restore(tampered, backup, attested)
    assert not (tampered / "data" / "ontology.sqlite3").exists()

    restored, report = _restore(
        _copy_for_restore(project, backup, tmp_path, "clean"), backup, attested)
    assert report["ok"] is True
    assert _query(restored, "SELECT COUNT(*) FROM ontology_link_retractions") == [(1,)]


def _as_version_3(path, keep=3):
    """Turn a copy without retractions into the layout the previous release wrote."""
    conn = sqlite3.connect(path)
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND "
        "(tbl_name='ontology_link_retractions' OR name='ontology_links_no_successor_of_retracted')"
    ).fetchall():
        conn.execute(f"DROP TRIGGER {name}")
    conn.execute("DROP TABLE ontology_link_retractions")
    conn.execute("DELETE FROM schema_migrations WHERE version>?", (keep,))
    conn.commit()
    conn.close()


def test_a_version_3_backup_still_restores_and_then_migrates(graph, tmp_path):
    store, audit, project = graph[0], graph[5], graph[4]
    link = graph[1]("one_to_one", (1, "C-1"), (1, "C-3"))
    backup = project / "data" / "old.backup.sqlite3"
    store.backup(backup, policy=_allow, audit=audit)
    _as_version_3(backup)
    attested = _attested(store, backup, audit)
    assert attested["dependency_manifest"]["ontology_schema_version"] == 3

    target = _copy_for_restore(project, backup, tmp_path, "old")
    restored, report = _restore(target, backup, attested)

    # verify_integrity opened the restored store, which applies the new migration.
    assert report["schema_version"] == 4 and report["link_cardinality"] == "ok"
    assert _query(restored, "SELECT link_id FROM ontology_links") == [(link,)]


def test_a_backup_older_than_the_oldest_verifiable_version_is_refused(graph):
    store, audit, project = graph[0], graph[5], graph[4]
    backup = project / "data" / "too-old.backup.sqlite3"
    store.backup(backup, policy=_allow, audit=audit)
    _as_version_3(backup, keep=2)
    with pytest.raises(OntologyError, match="migration history"):
        store.backup_dependency_manifest(backup, policy=_allow, audit=audit)


def test_opening_a_version_3_store_adds_retraction_without_touching_links(graph):
    store = graph[0]
    link = graph[1]("one_to_one", (1, "C-1"), (1, "C-3"))
    before = _query(store, "SELECT * FROM ontology_links")
    _as_version_3(store.path)
    assert graph[3]()["schema_version"] == 4
    assert _query(store, "SELECT * FROM ontology_links") == before
    _retract(graph, link)
    assert _links(graph, "one_to_one") == []

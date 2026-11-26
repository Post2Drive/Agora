"""Cardinality follows the stable object, not the import it was read from."""
import copy
import itertools
import sqlite3

import pytest

from agora.identity import stable_record_key
from agora.ontology import OntologyError, parse_domain_pack
from agora.tabular import ingest_csv

from test_ontology_link_source_refs import _pack_data
from test_ontology_store import _SCHEMA, _allow, _attested, _binding, catalog  # noqa: F401

_CONSTRAINED = ("one_to_one", "one_to_many")
_JAN, _FEB, _MAR, _APR = (f"2026-0{month}-01T00:00:00+00:00" for month in range(1, 5))


@pytest.fixture
def graph(catalog):  # noqa: F811
    project, store, audit, _, _ = catalog
    data = copy.deepcopy(_pack_data())
    data["pack_id"] = "cardinality-pack"
    template = data["link_types"][0]
    data["link_types"] = [
        {**template, "link_type_id": f"backup:{name}", "name": name, "predicate": name,
         "cardinality": name}
        for name in (*_CONSTRAINED, "many_to_many")
    ]
    pack_fp = store.register_pack(parse_domain_pack(data), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    imports = []
    for number in (1, 2):
        source = project / f"customers{number}.csv"
        rows = "".join(f"C-{i},v{number}-{i}@example.test\n" for i in range(1, 5))
        source.write_text("customer_id,email\n" + rows, encoding="utf-8")
        import_id = ingest_csv(
            project, source, _SCHEMA, data_role="context", policy=_allow, audit=audit)["import_id"]
        store.materialize_binding(
            pack_fp, binding_fp, import_id, policy=_allow, audit=audit,
            purpose="account support", retention="90 days")
        imports.append(import_id)
    assert imports[0] != imports[1]

    def end(number, key):
        return {"project_id": store.project_id, "pack_fingerprint": pack_fp,
                "type_id": "backup:Customer", "type_version": "1.0.0",
                "import_id": imports[number - 1],
                "record_key": stable_record_key("customers", key)}

    def add(name, source, target, start=_JAN, stop=None):
        return store.add_link(
            pack_fp, f"backup:{name}", "1.0.0", end(*source), end(*target), start, stop,
            "assertion", {"kind": "manual_assertion"}, policy=_allow, audit=audit)

    def supersede(link_id, source, target, start=_JAN, stop=None):
        return store.supersede_link(
            pack_fp, link_id, end(*source), end(*target), start, stop, "restated",
            {"kind": "manual_assertion"}, policy=_allow, audit=audit)

    def report():
        return store.verify_integrity(policy=_allow, audit=audit)

    return store, add, supersede, report, project, audit


def _count(store):
    conn = sqlite3.connect(store.path)
    try:
        return conn.execute("SELECT COUNT(*) FROM ontology_links").fetchone()[0]
    finally:
        conn.close()


def _refused(graph, call, name):
    before = _count(graph[0])
    with pytest.raises(OntologyError, match=f"violates {name} cardinality"):
        call()
    assert _count(graph[0]) == before


@pytest.mark.parametrize("name", _CONSTRAINED)
def test_same_target_from_another_import_cannot_gain_a_second_source(graph, name):
    graph[1](name, (1, "C-1"), (1, "C-3"))
    _refused(graph, lambda: graph[1](name, (1, "C-2"), (2, "C-3")), name)


def test_same_source_from_another_import_cannot_gain_a_second_target(graph):
    graph[1]("one_to_one", (1, "C-1"), (1, "C-3"))
    _refused(graph, lambda: graph[1]("one_to_one", (2, "C-1"), (1, "C-4")), "one_to_one")


@pytest.mark.parametrize("name", _CONSTRAINED)
def test_restating_the_same_pair_with_add_link_is_refused(graph, name):
    graph[1](name, (1, "C-1"), (1, "C-3"))
    _refused(graph, lambda: graph[1](name, (2, "C-1"), (2, "C-3")), name)


@pytest.mark.parametrize("name", _CONSTRAINED)
def test_supersede_restates_a_relationship_from_a_newer_import(graph, name):
    first = graph[1](name, (1, "C-1"), (1, "C-3"))
    assert graph[2](first, (2, "C-1"), (2, "C-3")).startswith("link-")
    assert graph[3]()["link_cardinality"] == "ok"


def test_supersede_still_checks_other_active_links(graph):
    graph[1]("one_to_many", (1, "C-1"), (1, "C-3"))
    other = graph[1]("one_to_many", (1, "C-2"), (1, "C-4"))
    _refused(graph, lambda: graph[2](other, (1, "C-2"), (2, "C-3")), "one_to_many")


@pytest.mark.parametrize("name", _CONSTRAINED)
def test_adjacent_valid_time_across_imports_is_allowed(graph, name):
    graph[1](name, (1, "C-1"), (1, "C-3"), _JAN, _FEB)
    assert graph[1](name, (2, "C-2"), (2, "C-3"), _FEB, None)


def test_one_to_many_still_lets_a_source_have_many_targets(graph):
    graph[1]("one_to_many", (1, "C-1"), (1, "C-3"))
    assert graph[1]("one_to_many", (2, "C-1"), (2, "C-4"))
    assert graph[3]()["link_cardinality"] == "ok"


def test_many_to_many_is_unrestricted_and_never_reported(graph):
    graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    graph[1]("many_to_many", (2, "C-1"), (2, "C-3"))
    report = graph[3]()
    assert report["link_cardinality"] == "ok"
    assert report["link_cardinality_conflict_count"] == 0
    assert report["link_cardinality_conflict_ids"] == []


def _legacy(graph, monkeypatch):
    """Write links as the earlier exact-endpoint comparison would have allowed."""
    from agora.ontology import store as module

    monkeypatch.setattr(
        module, "_cardinality_key", lambda type_id, import_id, key: (type_id, import_id, key))


def test_stored_violations_are_reported_not_rewritten_and_can_be_superseded(graph, monkeypatch):
    store, add, supersede, report = graph[:4]
    with monkeypatch.context() as patch:
        _legacy(graph, patch)
        first = add("one_to_many", (1, "C-1"), (1, "C-3"), _MAR, None)
        second = add("one_to_many", (1, "C-2"), (2, "C-3"), _MAR, None)
    clean = add("one_to_many", (1, "C-1"), (1, "C-4"))
    found = report()
    assert found["ok"] is True
    assert found["link_cardinality"] == "conflicts"
    assert found["link_cardinality_conflict_count"] == 2
    assert found["link_cardinality_conflict_ids"] == sorted([first, second])
    assert clean not in found["link_cardinality_conflict_ids"]
    assert _count(store) == 3
    supersede(second, (1, "C-2"), (2, "C-3"), _JAN, _MAR)
    assert report()["link_cardinality"] == "ok"


def test_sweep_reports_every_link_inside_a_longer_one(graph, monkeypatch):
    add, report = graph[1], graph[3]
    with monkeypatch.context() as patch:
        _legacy(graph, patch)
        long = add("one_to_many", (1, "C-1"), (1, "C-4"), _JAN, None)
        early = add("one_to_many", (1, "C-2"), (2, "C-4"), _FEB, _MAR)
    with monkeypatch.context() as patch:
        # Every comparison differs, so the write check lets this overlap through too.
        fresh = itertools.count()
        patch.setattr(
            "agora.ontology.store._cardinality_key", lambda *parts: (*parts, next(fresh)))
        late = add("one_to_many", (1, "C-3"), (1, "C-4"), _APR, None)
    assert report()["link_cardinality_conflict_ids"] == sorted([long, early, late])


def test_stored_one_to_one_source_side_violation_is_reported(graph, monkeypatch):
    add, report = graph[1], graph[3]
    with monkeypatch.context() as patch:
        _legacy(graph, patch)
        pair = [add("one_to_one", (1, "C-1"), (1, "C-3")),
                add("one_to_one", (2, "C-1"), (1, "C-4"))]
    assert report()["link_cardinality_conflict_ids"] == sorted(pair)


def test_reported_ids_are_capped_but_the_count_is_not(graph, monkeypatch):
    from agora.ontology import store as module

    monkeypatch.setattr(module, "_MAX_REPORTED_CONFLICTS", 1)
    with monkeypatch.context() as patch:
        _legacy(graph, patch)
        graph[1]("one_to_many", (1, "C-1"), (1, "C-3"))
        graph[1]("one_to_many", (1, "C-2"), (2, "C-3"))
    found = graph[3]()
    assert found["link_cardinality_conflict_count"] == 2
    assert len(found["link_cardinality_conflict_ids"]) == 1


def test_a_store_with_stored_violations_can_still_be_backed_up_and_restored(graph, monkeypatch):
    store, project, audit = graph[0], graph[4], graph[5]
    with monkeypatch.context() as patch:
        _legacy(graph, patch)
        graph[1]("one_to_many", (1, "C-1"), (1, "C-3"))
        graph[1]("one_to_many", (1, "C-2"), (2, "C-3"))
    backup = store.backup(project / "data" / "legacy.backup.sqlite3", policy=_allow, audit=audit)
    attested = _attested(store, backup, audit)
    assert attested["expected_manifest_sha256"]


def test_a_stored_link_whose_type_is_not_in_its_pack_is_refused(graph):
    store = graph[0]
    graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    conn = sqlite3.connect(store.path)
    try:
        trigger = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='ontology_links_no_update'").fetchone()[0]
        conn.execute("DROP TRIGGER ontology_links_no_update")
        conn.execute("UPDATE ontology_links SET link_type_id='backup:unknown'")
        conn.execute(trigger)
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(OntologyError, match="does not resolve to a link type"):
        graph[3]()

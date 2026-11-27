"""Replacing a link needs authority over the link being replaced, checked before it is looked up."""
import pytest

from agora.ontology import OntologyError

from test_ontology_link_cardinality import _JAN, graph  # noqa: F401
from test_ontology_link_retraction import _links, _pack_of, _query, _raw, _recording
from test_ontology_store import _allow, catalog  # noqa: F401

_MANUAL = {"kind": "manual_assertion"}


def _deny(operation, resource):
    return {**_allow(operation, resource), "decision": "deny"}


def _ends(graph, link_id):
    """The two stored endpoints of a link, as exact references."""
    store = graph[0]
    [row] = _query(
        store,
        """SELECT pack_fingerprint, source_type_id, source_type_version, source_import_id,
                  source_record_key, target_type_id, target_type_version, target_import_id,
                  target_record_key FROM ontology_links WHERE link_id=?""", (link_id,))
    return [
        {"project_id": store.project_id, "pack_fingerprint": row[0], "type_id": row[i],
         "type_version": row[i + 1], "import_id": row[i + 2], "record_key": row[i + 3]}
        for i in (1, 5)
    ]


def _supersede(graph, link_id, source, target, policy):
    store, audit = graph[0], graph[5]
    return store.supersede_link(
        _pack_of(store), link_id, source, target, _JAN, None, "restated", _MANUAL,
        policy=policy, audit=audit)


def _old_and_replacement(graph):
    """A stored link, and endpoints for a replacement that points somewhere else."""
    old = graph[1]("many_to_many", (1, "C-1"), (1, "C-3"))
    other = graph[1]("many_to_many", (1, "C-1"), (1, "C-4"))
    source, old_target = _ends(graph, old)
    _, new_target = _ends(graph, other)
    return old, source, old_target, new_target


def _statuses(graph):
    return {x["link_id"]: x["status"]
            for x in _links(graph, "many_to_many", include_superseded=True)}


@pytest.mark.parametrize("link_id", ["link-missing", None])
def test_a_denied_caller_cannot_probe_which_links_can_be_superseded(graph, link_id):
    old, source, _, new_target = _old_and_replacement(graph)
    with pytest.raises(OntologyError, match="policy denied"):
        _supersede(graph, link_id or old, source, new_target, _deny)


def test_the_first_decision_is_taken_before_the_lookup_and_names_the_link(graph):
    _, source, _, new_target = _old_and_replacement(graph)
    policy, seen = _recording(lambda o, r, n: _allow(o, r))
    with pytest.raises(OntologyError, match="link to supersede was not found"):
        _supersede(graph, "link-missing", source, new_target, policy)
    assert [(x[0], x[2]) for x in seen] == [("ontology_write", [_pack_of(graph[0]), "link-missing"])]


@pytest.mark.parametrize("link_id", ["", " link-x", 7])
def test_a_malformed_link_id_is_refused(graph, link_id):
    _, source, _, new_target = _old_and_replacement(graph)
    with pytest.raises(OntologyError, match="canonical string"):
        _supersede(graph, link_id, source, new_target, _allow)


def test_a_caller_without_authority_over_the_old_endpoint_cannot_replace_the_link(graph):
    old, source, old_target, new_target = _old_and_replacement(graph)
    policy, _ = _recording(
        lambda o, r, n: _deny(o, r) if o == "ontology_write"
        and old_target["record_key"] in r["resource_ids"] else _allow(o, r))
    before = _statuses(graph)
    with pytest.raises(OntologyError, match="policy denied"):
        _supersede(graph, old, source, new_target, policy)
    assert _statuses(graph) == before


def test_replacement_is_authorized_at_the_old_endpoints_sensitivity(graph):
    old, source, old_target, new_target = _old_and_replacement(graph)
    # Only the object the old link points at stays classified.
    _raw(graph[0],
         "UPDATE ontology_object_refs SET property_sensitivity_json='{}' "
         f"WHERE record_key<>'{old_target['record_key']}'",
         drop=_triggers(graph[0], "ontology_object_refs"))
    deny_classified, seen = _recording(
        lambda o, r, n: _allow(o, r) if r["source_sensitivity"] == "internal" else _deny(o, r))
    before = _statuses(graph)
    with pytest.raises(OntologyError, match="policy denied"):
        _supersede(graph, old, source, new_target, deny_classified)
    assert seen[-1][0] == "ontology_write" and seen[-1][1] in {"personal", "sensitive"}
    assert _statuses(graph) == before


def _triggers(store, table):
    return [row[0] for row in _query(
        store, "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,))]


def test_the_write_decision_names_the_replaced_link_and_both_pairs_of_endpoints(graph):
    old, source, old_target, new_target = _old_and_replacement(graph)
    policy, seen = _recording(lambda o, r, n: _allow(o, r))
    successor = _supersede(graph, old, source, new_target, policy)
    final = [x for x in seen if x[0] == "ontology_write"][-1][2]
    for expected in (old, old_target["record_key"], new_target["record_key"], source["record_key"]):
        assert expected in final
    assert _statuses(graph)[old] == "superseded"
    assert _statuses(graph)[successor] == "active"


def test_link_set_size_is_not_disclosed_without_authority_over_the_link_type(graph, monkeypatch):
    store, audit = graph[0], graph[5]
    for number in (2, 3, 4):
        graph[1]("many_to_many", (1, "C-1"), (1, f"C-{number}"))
    policy, _ = _recording(
        lambda o, r, n: _deny(o, r) if "backup:many_to_many" in r["resource_ids"] else _allow(o, r))
    queried = []
    real = store._connect

    def connect():
        conn = real()
        conn.set_trace_callback(queried.append)
        return conn

    pack = _pack_of(store)
    monkeypatch.setattr(store, "_connect", connect)
    with pytest.raises(OntologyError, match="policy denied"):
        store.get_links(pack, "backup:many_to_many", "1.0.0", policy=policy, audit=audit)
    assert not [q for q in queried if "FROM ontology_links" in q]

"""The seed edge plan: reads active ontology links, counts what it skips, writes nothing."""
from types import SimpleNamespace

import pytest

from agora.ontology import OntologyError
from agora.society import SeedError, SocietyStore, parse_seed
from agora.society.seed import SEED_FORMAT
from agora.society.seed_plan import plan_seed_edges
from test_ontology_store import _allow, catalog, linked  # noqa: F401

FP = "ab" * 32
IMPORT = "imp-1"


def _seed(*, direction="both", trust=0.6, familiarity=0.3, link_types=None, records=None):
    return parse_seed({
        "format": SEED_FORMAT, "pack_fingerprint": FP, "import_id": IMPORT,
        "link_types": link_types or [{"link_type_id": "knows", "direction": direction,
                                      "trust": trust, "familiarity": familiarity}],
        "records": records or [{"record_key": "A", "agent": 1}, {"record_key": "B", "agent": 2},
                               {"record_key": "C", "agent": 3}],
    })


def _link(link_id, a, b, *, status="active", imp=IMPORT, imp_b=None):
    return {"link_id": link_id, "status": status,
            "source": {"import_id": imp, "record_key": a}, "target": {"import_id": imp_b or imp, "record_key": b}}


class FakeStore:
    def __init__(self, links, versions=("1.0.0",), link_type="knows"):
        self.links = links
        self.pack = SimpleNamespace(link_types=[SimpleNamespace(link_type_id=link_type, version=v) for v in versions])
        self.calls = []

    def get_pack(self, fingerprint, *, policy, audit):
        self.calls.append(("pack", fingerprint, policy, audit))
        return self.pack

    def get_links(self, fingerprint, link_type_id, version, *, policy, audit):
        self.calls.append(("links", fingerprint, link_type_id, version, policy, audit))
        return self.links.get(link_type_id, [])


def _plan(links, seed=None, **kw):
    return plan_seed_edges(FakeStore(links, **kw), seed or _seed(), policy="P", audit="A")


def test_both_direction_gives_two_edges_with_declared_values():
    plan = _plan({"knows": [_link("L1", "A", "B")]})
    assert [(e.source, e.target, e.trust, e.familiarity, e.link_ids) for e in plan.edges] == [
        (1, 2, 0.6, 0.3, ("L1",)), (2, 1, 0.6, 0.3, ("L1",))]
    assert (plan.counts.links_read, plan.counts.links_used) == (1, 1)
    assert plan.seed_hash == _seed().seed_hash and plan.pack_fingerprint == FP


def test_source_to_target_gives_one_edge():
    plan = _plan({"knows": [_link("L1", "A", "B")]}, _seed(direction="source_to_target"))
    assert [(e.source, e.target) for e in plan.edges] == [(1, 2)]
    plan = _plan({"knows": [_link("L1", "B", "A")]}, _seed(direction="source_to_target"))
    assert [(e.source, e.target) for e in plan.edges] == [(2, 1)]


def test_edges_are_sorted_and_deterministic():
    links = {"knows": [_link("L2", "C", "A"), _link("L1", "A", "B")]}
    first = _plan(links)
    assert [(e.source, e.target) for e in first.edges] == [(1, 2), (1, 3), (2, 1), (3, 1)]
    assert _plan({"knows": list(reversed(links["knows"]))}) == first


def test_inactive_other_import_unmapped_and_self_links_are_counted_not_used():
    links = {"knows": [
        _link("L1", "A", "B", status="retracted"),
        _link("L2", "A", "B", status="superseded"),
        _link("L3", "A", "B", imp="other"),
        _link("L4", "A", "B", imp_b="other"),
        _link("L5", "A", "Z"),
        _link("L6", "Z", "A"),
        _link("L7", "A", "A"),
        _link("L8", "B", "C"),
    ]}
    plan = _plan(links)
    assert plan.counts == type(plan.counts)(links_read=8, links_used=1, other_import=2, not_mapped=2,
                                            same_agent=1, not_active=2)
    assert {e.link_ids for e in plan.edges} == {("L8",)}


def test_several_links_on_one_pair_take_the_largest_values_and_list_every_link():
    seed = _seed(link_types=[
        {"link_type_id": "knows", "direction": "both", "trust": 0.8, "familiarity": 0.9},
        {"link_type_id": "reports_to", "direction": "source_to_target", "trust": 0.4, "familiarity": 0.1}])
    extra = [_link(f"M{i}", "A", "B") for i in range(12)]
    store = FakeStore({"knows": [_link("L1", "A", "B")], "reports_to": [_link("L2", "A", "B"), _link("L3", "A", "B")] + extra})
    store.pack.link_types.append(SimpleNamespace(link_type_id="reports_to", version="2.0.0"))
    plan = plan_seed_edges(store, seed, policy=None, audit=None)
    forward = next(e for e in plan.edges if (e.source, e.target) == (1, 2))
    assert (forward.trust, forward.familiarity, forward.link_ids) == (
        0.8, 0.9, tuple(sorted(["L1", "L2", "L3"] + [f"M{i}" for i in range(12)])))
    back = next(e for e in plan.edges if (e.source, e.target) == (2, 1))
    assert (back.trust, back.familiarity, back.link_ids) == (0.8, 0.9, ("L1",))


def test_pack_and_policy_are_passed_through_with_the_pack_version():
    store = FakeStore({"knows": []}, versions=("3.1.0",))
    plan_seed_edges(store, _seed(), policy="POLICY", audit="AUDIT")
    assert store.calls == [("pack", FP, "POLICY", "AUDIT"), ("links", FP, "knows", "3.1.0", "POLICY", "AUDIT")]


def test_unknown_or_ambiguous_link_type_is_refused():
    with pytest.raises(SeedError, match="not in the ontology pack"):
        _plan({}, link_type="friends")
    with pytest.raises(SeedError, match="more than one version"):
        _plan({}, versions=("1.0.0", "2.0.0"))


def test_a_full_page_of_links_is_refused_not_truncated():
    many = [_link(f"L{i}", "A", "B") for i in range(99)]
    assert _plan({"knows": many}).counts.links_read == 99
    with pytest.raises(SeedError, match="100 or more"):
        _plan({"knows": many + [_link("L99", "A", "B")]})


def test_no_links_gives_an_empty_plan():
    plan = _plan({})
    assert plan.edges == () and plan.counts.links_read == 0


def test_planning_changes_no_society_store():
    soc = SocietyStore(":memory:")
    before = soc.digest()
    _plan({"knows": [_link("L1", "A", "B")]})
    assert soc.digest() == before


# --- against the real ontology store ---------------------------------------------------
def test_real_store_active_links_only(linked):
    store, audit = linked["store"], linked["audit"]
    import sqlite3
    db = sqlite3.connect(store.path)
    fingerprint = db.execute("SELECT fingerprint FROM ontology_packs").fetchone()[0]
    row = db.execute("SELECT link_id, source_import_id, source_record_key, target_record_key FROM ontology_links").fetchone()
    db.close()
    link_id, import_id, a, b = row
    seed = parse_seed({
        "format": SEED_FORMAT, "pack_fingerprint": fingerprint, "import_id": import_id,
        "link_types": [{"link_type_id": "backup:knows", "direction": "both", "trust": 0.7, "familiarity": 0.2}],
        "records": [{"record_key": a, "agent": 5}, {"record_key": b, "agent": 8}]})
    plan = plan_seed_edges(store, seed, policy=_allow, audit=audit)
    assert [(e.source, e.target, e.trust, e.link_ids) for e in plan.edges] == [
        (5, 8, 0.7, (link_id,)), (8, 5, 0.7, (link_id,))]
    store.retract_link(fingerprint, link_id, "no longer true",
                       {"kind": "source", "source_refs": [
                           {"import_id": linked["evidence"], "file_sha256": linked["digest"], "locator": "row:2"}]},
                       policy=_allow, audit=audit)
    after = plan_seed_edges(store, seed, policy=_allow, audit=audit)
    assert after.edges == () and after.counts.links_read == 0
    with pytest.raises((PermissionError, OntologyError)):
        plan_seed_edges(store, seed, policy=lambda op, res: {"decision": "deny", "reason": "no", "subject_id": "x",
                                                             "policy_version": "v", "resource_ids": []}, audit=audit)

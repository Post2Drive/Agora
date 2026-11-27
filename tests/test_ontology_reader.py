"""The versioned typed read interface. All data is synthetic."""

from __future__ import annotations

import dataclasses
import json
import sys
import types

import pytest

from agora import protection
from agora.identity import stable_record_key
from agora.ontology import OntologyError, OntologyObjectStore
from agora.ontology.reader import READ_API_VERSION, ObjectRef, OntologyReader
from agora.ontology.registry import pack_document, parse_domain_pack
from agora.ontology.typed import generate_python_types
from test_import_attestation import _import, anchored  # noqa: F401
from test_ontology_read_attestation import PRIVACY, World, _cite, _unrecorded_import
from test_ontology_store import _allow, _pack
from test_snapshot_row_integrity import ROWS


def _module(pack, name="reader_types"):
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(generate_python_types(pack), f"<{name}>", "exec"), module.__dict__)
    finally:
        del sys.modules[name]
    return module


def _other_pack():
    """Same type IDs and versions as ``_pack``, another fingerprint."""
    document = json.loads(json.dumps(pack_document(_pack())))
    document["schema_version"] = "1.0.1"
    return parse_domain_pack(document)


def _key(code):
    return stable_record_key("customers", code)


def _deny(operation, resource):
    return {"decision": "deny", "reason": "policy_deny", "subject_id": "reader-test",
            "policy_version": "reader-test-v1", "resource_ids": list(resource["resource_ids"])}


@pytest.fixture
def world(anchored):  # noqa: F811
    project, audit = anchored
    import_id = _import(project, audit)["import_id"]
    result = World(project, audit)
    result.index(import_id)
    result.import_id = import_id
    result.types = _module(_pack())
    return result


def _reader(world, **changes):
    options = {"api_version": READ_API_VERSION, "policy": _allow, "audit": world.audit,
               **PRIVACY, **changes}
    module = options.pop("types", world.types)
    return OntologyReader(world.store, module, **options)


def test_get_and_query_return_the_generated_type(world):
    reader = _reader(world)
    assert reader.pack_fingerprint == world.pack_fp
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    assert type(one) is world.types.Customer
    assert (one.id, one.email) == (ROWS[0][0], ROWS[0][1])
    page = reader.query(world.types.Customer, world.import_id)
    assert page.next_cursor is None
    assert sorted(item.id for item in page.objects) == sorted(row[0] for row in ROWS)


def test_query_passes_filters_and_pages_through(world):
    reader = _reader(world)
    only = reader.query(world.types.Customer, world.import_id,
                        {"backup:Customer.id": {"op": "eq", "value": ROWS[1][0]}})
    assert [item.id for item in only.objects] == [ROWS[1][0]]
    seen, cursor = [], None
    for _ in range(len(ROWS) + 2):  # bounded, so a dropped cursor fails instead of hanging
        page = reader.query(world.types.Customer, world.import_id, page_size=1, cursor=cursor)
        seen += [item.id for item in page.objects]
        cursor = page.next_cursor
        if cursor is None:
            break
    assert cursor is None
    assert sorted(seen) == sorted(row[0] for row in ROWS)


def test_links_are_typed_and_their_ends_resolve(world):
    link_id = world.link(world.import_id, _cite_of(world))
    reader = _reader(world)
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    page = reader.links("backup:knows", "1.0.0", one, direction="out")
    assert page.next_cursor is None
    [link] = page.links
    assert (link.link_id, link.status, link.retraction) == (link_id, "active", None)
    assert link.source == ObjectRef("backup:Customer", "1.0.0", world.import_id, _key("C-1"))
    assert reader.resolve(link.target).id == ROWS[1][0]
    assert reader.links("backup:knows", "1.0.0", one, direction="in").links == ()
    assert hash(link) is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        link.status = "retracted"


def _cite_of(world):
    return _cite(world.project, world.import_id)


def test_a_retracted_link_is_returned_and_says_so(world):
    link_id = world.link(world.import_id, _cite_of(world))
    world.store.retract_link(
        world.pack_fp, link_id, "entered in error",
        {"kind": "source", "source_refs": [_cite_of(world)]}, policy=_allow, audit=world.audit)
    reader = _reader(world)
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    [link] = reader.links("backup:knows", "1.0.0", one).links
    assert link.status == "retracted"
    assert link.retraction["reason"] == "entered in error"


def test_repr_shows_no_record_key_reason_or_actor(world):
    world.link(world.import_id, _cite_of(world))
    reader = _reader(world)
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    [link] = reader.links("backup:knows", "1.0.0", one).links
    shown = repr(link)
    for value in (_key("C-1"), _key("C-2"), "referral", link.actor_id):
        assert value not in shown


@pytest.mark.parametrize("version", ["2", "", 1, None])
def test_another_interface_version_is_refused(world, version):
    with pytest.raises(OntologyError, match="unsupported read interface version"):
        _reader(world, api_version=version)


def test_a_module_from_another_generator_version_is_refused(world):
    world.types.GENERATOR_VERSION = "0"
    with pytest.raises(OntologyError, match="another generator version"):
        _reader(world)


@pytest.mark.parametrize("name, value", [
    ("PACK_FINGERPRINT", None), ("PACK_FINGERPRINT", ""), ("OBJECT_TYPES", {}),
    ("OBJECT_TYPES", None), ("InstanceError", None), ("InstanceError", KeyError),
])
def test_something_that_is_not_a_generated_module_is_refused(world, name, value):
    setattr(world.types, name, value)
    with pytest.raises(OntologyError, match="not a generated type module"):
        _reader(world)


def test_a_class_from_another_pack_is_refused_before_any_read(world):
    other = _module(_other_pack(), "other_types")
    assert other.PACK_FINGERPRINT != world.types.PACK_FINGERPRINT
    reader = _reader(world, policy=lambda *_: pytest.fail("the store was reached"))
    with pytest.raises(OntologyError, match="not an object type of this reader"):
        reader.get(other.Customer, _key("C-1"), world.import_id)
    with pytest.raises(OntologyError, match="not an object type of this reader"):
        reader.query(other.Customer, world.import_id)


def test_an_object_from_another_pack_cannot_start_a_traversal(world):
    other = _module(_other_pack(), "other_types")
    one = _reader(world).get(world.types.Customer, _key("C-1"), world.import_id)
    foreign = other.Customer(provenance=one.provenance, id=one.id, email=one.email)
    reader = _reader(world, policy=lambda *_: pytest.fail("the store was reached"))
    with pytest.raises(OntologyError, match="not an object type of this reader"):
        reader.links("backup:knows", "1.0.0", foreign)


def test_a_reader_for_a_pack_the_store_lacks_reads_nothing(world):
    other = _module(_other_pack(), "other_types")
    reader = _reader(world, types=other)
    with pytest.raises(OntologyError):
        reader.get(other.Customer, _key("C-1"), world.import_id)
    with pytest.raises(OntologyError, match="unknown ontology pack fingerprint"):
        reader.query(other.Customer, world.import_id)


def test_changing_the_module_later_does_not_change_the_reader(world):
    other = _module(_other_pack(), "other_types")
    reader = _reader(world)
    world.types.OBJECT_TYPES[("backup:Customer", "1.0.0")] = other.Customer
    world.types.PACK_FINGERPRINT = other.PACK_FINGERPRINT
    assert reader.pack_fingerprint == world.pack_fp
    with pytest.raises(OntologyError, match="not an object type of this reader"):
        reader.get(other.Customer, _key("C-1"), world.import_id)


def test_every_read_uses_the_readers_policy(world):
    reader = _reader(world, policy=_deny)
    with pytest.raises(OntologyError, match="policy denied"):
        reader.get(world.types.Customer, _key("C-1"), world.import_id)
    with pytest.raises(OntologyError, match="policy denied"):
        reader.query(world.types.Customer, world.import_id)
    one = _reader(world).get(world.types.Customer, _key("C-1"), world.import_id)
    with pytest.raises(OntologyError, match="policy denied"):
        reader.links("backup:knows", "1.0.0", one)


def test_the_readers_purpose_and_retention_reach_the_policy(world):
    seen = []

    def record(operation, resource):
        if operation == "binding":
            seen.append((resource["purpose"], resource["retention"]))
        return _allow(operation, resource)

    reader = _reader(world, policy=record, purpose="reader-purpose", retention="7d")
    reader.get(world.types.Customer, _key("C-1"), world.import_id)
    reader.query(world.types.Customer, world.import_id)
    assert len(seen) >= 3
    assert set(seen) == {("reader-purpose", "7d")}


def test_the_ingest_record_is_still_required(anchored, monkeypatch):  # noqa: F811
    project, audit = anchored
    import_id = _unrecorded_import(project, audit, monkeypatch)
    result = World(project, audit)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    result.index(import_id)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    result.types = _module(_pack())
    with pytest.raises(OntologyError, match="no matching ingest record"):
        _reader(result).query(result.types.Customer, import_id)


def test_one_row_that_does_not_fit_fails_the_whole_page_without_values(world, monkeypatch):
    real = OntologyObjectStore.query_objects

    def tampered(self, *args, **kwargs):
        page = real(self, *args, **kwargs)
        page["objects"][-1]["property_values"]["backup:Customer.email"] = 12345678
        return page

    monkeypatch.setattr(OntologyObjectStore, "query_objects", tampered)
    with pytest.raises(OntologyError, match="backup:Customer.email does not have") as caught:
        _reader(world).query(world.types.Customer, world.import_id)
    assert "12345678" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_an_unknown_link_status_is_refused(world, monkeypatch):
    world.link(world.import_id, _cite_of(world))
    reader = _reader(world)
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    real = OntologyObjectStore.traverse_links

    def changed(self, *args, **kwargs):
        page = real(self, *args, **kwargs)
        page["links"][0]["status"] = "disputed"
        return page

    monkeypatch.setattr(OntologyObjectStore, "traverse_links", changed)
    with pytest.raises(OntologyError, match="status this interface version does not know"):
        reader.links("backup:knows", "1.0.0", one)


@pytest.mark.parametrize("ref", [
    None, {"type_id": "backup:Customer"},
])
def test_resolve_refuses_something_else(world, ref):
    with pytest.raises(OntologyError, match="resolve needs an ObjectRef"):
        _reader(world).resolve(ref)


def test_resolve_refuses_an_unknown_type(world):
    with pytest.raises(OntologyError, match="no such object type and version"):
        _reader(world).resolve(ObjectRef("backup:Customer", "9.0.0", world.import_id, _key("C-1")))

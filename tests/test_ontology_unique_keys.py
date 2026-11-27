"""Pack-declared unique keys for non-identity properties. All data is synthetic."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, load_domain_pack, parse_domain_pack
from agora.ontology.binding import (
    _comparable, iter_source_object_refs, load_binding, materialize_instances,
)
from agora.ontology.compat import compare_packs
from agora.ontology.registry import pack_document
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import ingest_csv

CID = "uk:Customer.id"
EMAIL = "uk:Customer.email"
CODE = "uk:Customer.code"
REPO = Path(__file__).resolve().parents[1]


def _pack_data(unique_keys=None, *, code_type="string", code_nullable=False, version="1.0.0"):
    def prop(pid, data_type, nullable=False):
        return {"property_id": pid, "version": "1.0.0", "name": pid.rsplit(".", 1)[1],
                "data_type": data_type, "required": True, "nullable": nullable,
                "sensitivity": "public"}

    obj = {"type_id": "uk:Customer", "version": version, "name": "Customer",
           "description": "Synthetic", "properties": [CID, EMAIL, CODE],
           "identity_strategy": "record_key"}
    if unique_keys is not None:
        obj["unique_keys"] = unique_keys
    return {
        "pack_id": "uk-pack", "schema_version": version, "object_types": [obj],
        "property_types": [prop(CID, "identifier"), prop(EMAIL, "string"),
                           prop(CODE, code_type, code_nullable)],
        "link_types": [], "action_types": [],
    }


def _pack(unique_keys=None, **kwargs):
    return parse_domain_pack(_pack_data(unique_keys, **kwargs))


def _binding():
    return load_binding({
        "binding_id": "uk.customer", "binding_version": "1.0.0",
        "object_type_id": "uk:Customer", "object_type_version": "1.0.0",
        "dataset_id": "uk_customers", "schema_id": "uk-customers", "schema_version": "1.0.0",
        "column_map": {"customer_id": CID, "email": EMAIL, "code": CODE},
        "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
    })


def _import(project, rows, *, code_type="string", code_nullable=False):
    def column(name, kind="string", **extra):
        return {"name": name, "type": kind, "nullable": False, "sensitivity": "public", **extra}

    code = column("code", code_type, nullable=code_nullable)
    if code_nullable:
        code["empty_as_null"] = True
    if code_type == "decimal":
        code.update(precision=40, scale=4)
    schema = {
        "schema_id": "uk-customers", "schema_version": "1.0.0", "dataset_name": "uk_customers",
        "columns": [column("customer_id", primary_key=True), column("email"), code],
    }
    project.mkdir(parents=True, exist_ok=True)
    source = project / "customers.csv"
    source.write_text("customer_id,email,code\n" + "".join(f"{r}\n" for r in rows), encoding="utf-8")
    return ingest_csv(project, source, schema, data_role="context")["import_id"]


def _allow(operation, resource):
    return {"decision": "allow", "reason": "policy_allow", "subject_id": "uk-operator",
            "policy_version": "uk-test", "resource_ids": list(resource["resource_ids"])}


def _read_all(pack, project, import_id):
    return materialize_instances(_binding(), pack, project, import_id, policy=_allow)


def _read_refs(pack, project, import_id):
    return list(iter_source_object_refs(_binding(), pack, project, import_id, policy=_allow))


def _read_scenario(pack, project, import_id):
    return build_scenario_input(_binding(), pack, project, import_id, policy=_allow,
                                transformation_policy=None)


READERS = [_read_all, _read_refs, _read_scenario]
REFUSED = (OntologyError, ScenarioInputError)


@pytest.mark.parametrize("reader", READERS)
def test_duplicate_value_of_a_declared_key_is_refused_without_echoing_it(tmp_path, reader):
    import_id = _import(tmp_path, ["C1,same@example.test,a", "C2,same@example.test,b"])

    with pytest.raises(REFUSED, match="unique key") as caught:
        reader(_pack([[EMAIL]]), tmp_path, import_id)

    assert EMAIL in str(caught.value)
    assert "same@example.test" not in str(caught.value)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("keys", [None, [], [[CODE]], [[EMAIL, CODE]]])
def test_rows_that_satisfy_the_declared_keys_are_read(tmp_path, reader, keys):
    # The shared email is only a problem when email is declared unique on its own.
    import_id = _import(tmp_path, ["C1,same@example.test,a", "C2,same@example.test,b"])

    assert reader(_pack(keys), tmp_path, import_id)


def test_composite_key_refuses_only_the_whole_combination(tmp_path):
    import_id = _import(tmp_path, ["C1,x@example.test,a", "C2,y@example.test,a", "C3,x@example.test,a"])

    with pytest.raises(OntologyError, match="unique key"):
        _read_all(_pack([[EMAIL, CODE]]), tmp_path, import_id)


def test_composite_key_components_cannot_run_together(tmp_path):
    import_id = _import(tmp_path, ["C1,ab,c", "C2,a,bc"])

    assert len(_read_all(_pack([[EMAIL, CODE]]), tmp_path, import_id)) == 2


def test_every_declared_key_is_checked(tmp_path):
    import_id = _import(tmp_path, ["C1,x@example.test,a", "C2,y@example.test,a"])

    with pytest.raises(OntologyError, match=CODE):
        _read_all(_pack([[EMAIL], [CODE]]), tmp_path, import_id)


def test_separate_keys_do_not_share_seen_values(tmp_path):
    import_id = _import(tmp_path, ["C1,a,b", "C2,b,a"])

    assert len(_read_all(_pack([[EMAIL], [CODE]]), tmp_path, import_id)) == 2


@pytest.mark.parametrize("reader", [_read_all, _read_refs])
def test_a_key_with_a_null_component_is_not_compared(tmp_path, reader):
    import_id = _import(tmp_path, ["C1,x@example.test,", "C2,x@example.test,"], code_nullable=True)
    pack = _pack([[CODE], [EMAIL, CODE]], code_nullable=True)

    assert len(reader(pack, tmp_path, import_id)) == 2


@pytest.mark.parametrize("first, second, duplicate", [
    ("1.5", "1.50", True),
    ("0", "-0.0", True),
    ("100", "100.0", True),
    ("1", "10", False),
    ("1.5", "-1.5", False),
])
def test_decimal_keys_compare_by_exact_numeric_value(tmp_path, first, second, duplicate):
    import_id = _import(tmp_path, [f"C1,x,{first}", f"C2,y,{second}"], code_type="decimal")
    pack = _pack([[CODE]], code_type="decimal")

    if duplicate:
        with pytest.raises(OntologyError, match="unique key"):
            _read_all(pack, tmp_path, import_id)
    else:
        assert len(_read_all(pack, tmp_path, import_id)) == 2


def test_decimal_comparison_does_not_round_to_the_decimal_context():
    # CSV ingestion cannot store this many digits today; the comparison must
    # still not call two different numbers equal.
    prop = _pack(code_type="decimal").property_types[2]
    first = "123456789012345678901234567890.0001"

    assert _comparable(first, prop) != _comparable("123456789012345678901234567890.0002", prop)
    assert _comparable(first, prop) == _comparable(first + "00", prop)


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity"])
def test_a_non_finite_decimal_in_a_key_is_refused_without_echoing_it(value):
    prop = _pack(code_type="decimal").property_types[2]

    with pytest.raises(OntologyError, match="not a finite decimal") as caught:
        _comparable(value, prop)

    assert value not in str(caught.value)


def test_integer_source_column_bound_to_decimal_property_is_compared(tmp_path):
    import_id = _import(tmp_path, ["C1,x,7", "C2,y,7"], code_type="integer")

    with pytest.raises(OntologyError, match="unique key"):
        _read_all(_pack([[CODE]], code_type="decimal"), tmp_path, import_id)


def test_string_keys_are_exact(tmp_path):
    import_id = _import(tmp_path, ["C1,A@example.test,a", "C2,a@example.test,b"])

    assert len(_read_all(_pack([[EMAIL]]), tmp_path, import_id)) == 2


def test_uniqueness_is_scoped_to_one_import(tmp_path):
    first = _import(tmp_path, ["C1,x@example.test,a"])
    second = _import(tmp_path, ["C2,x@example.test,a"])
    pack = _pack([[EMAIL]])

    assert first != second
    assert _read_all(pack, tmp_path, first) and _read_all(pack, tmp_path, second)


def test_store_indexes_nothing_from_an_import_that_breaks_a_key(tmp_path):
    # The conflict is on the last row, after earlier rows were already inserted.
    rows = ["C1,x@example.test,a", "C2,y@example.test,b", "C3,x@example.test,c"]
    import_id = _import(tmp_path, rows)
    store = OntologyObjectStore(tmp_path)
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    guard = {"policy": _allow, "audit": audit}
    pack_fp = store.register_pack(_pack([[EMAIL]]), **guard)
    binding_fp = store.register_binding(pack_fp, _binding(), **guard)

    with pytest.raises(OntologyError, match="unique key"):
        store.materialize_binding(pack_fp, binding_fp, import_id, **guard)

    conn = store._connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM ontology_object_refs").fetchone()[0] == 0
    finally:
        conn.close()


def test_store_keeps_unique_keys_and_verifies(tmp_path):
    store = OntologyObjectStore(tmp_path)
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    guard = {"policy": _allow, "audit": audit}
    pack = _pack([[EMAIL], [EMAIL, CODE]])

    fingerprint = store.register_pack(pack, **guard)

    assert store.get_pack(fingerprint, **guard) == pack
    assert store.verify_integrity(**guard)["ok"] is True


# Fingerprints computed on main 8c03d2b, before unique_keys existed. Stored packs
# are verified against these, so a pack without keys must keep its old identity.
@pytest.mark.parametrize("name, pack_fp, object_fp", [
    ("civic_in", "bd9d953ff43e2bd8be35520a70b349451b62d3e9b9605bc9ca8c19207a1446df",
     "405c251aeaef74d9ed07d1da565850a4c24c26f1d93568f3885200e6856721f4"),
    ("retail_in", "edc5db9d0462cb65b58de82033f12066994a16e264f5cc7ee3106565bd66ea61",
     "48e8eb53e9f3dd6c6779ea35ad8522559cf08e295f0db77bf72f10a4123b3969"),
])
def test_packs_without_unique_keys_keep_their_fingerprints(name, pack_fp, object_fp):
    pack = load_domain_pack(REPO / "domain_packs" / name / "pack.yaml")

    assert pack.fingerprint == pack_fp
    assert pack.object_types[0].fingerprint == object_fp
    assert all("unique_keys" not in item for item in pack_document(pack)["object_types"])


def test_a_keyless_pack_is_stored_in_the_old_form(tmp_path):
    # An existing store compares re-registered content byte for byte.
    store = OntologyObjectStore(tmp_path)
    guard = {"policy": _allow, "audit": AuditChainStore(tmp_path / "audit.sqlite3")}
    fingerprint = store.register_pack(_pack(), **guard)

    conn = store._connect()
    try:
        content = conn.execute("SELECT content_json FROM ontology_packs").fetchone()[0]
    finally:
        conn.close()

    assert "unique_keys" not in content
    assert store.register_pack(_pack(), **guard) == fingerprint


def test_empty_list_is_the_same_pack_as_no_declaration():
    assert _pack([]) == _pack() and _pack([]).fingerprint == _pack().fingerprint


def test_declared_keys_change_the_fingerprints():
    plain, keyed = _pack(), _pack([[EMAIL]])

    assert keyed.fingerprint != plain.fingerprint
    assert keyed.object_types[0].fingerprint != plain.object_types[0].fingerprint
    assert parse_domain_pack(json.loads(json.dumps(pack_document(keyed)))) == keyed


@pytest.mark.parametrize("keys, message", [
    (None, "must be a list"),
    ("uk:Customer.email", "must be a list"),
    ([EMAIL], "list of non-empty strings"),
    ([[]], "must name at least one property"),
    ([[1]], "list of non-empty strings"),
    ([[EMAIL, EMAIL]], "must not repeat a property"),
    ([[EMAIL, CODE], [CODE, EMAIL]], "same unique key twice"),
    ([["uk:Customer.unknown"]], "not a property of this object type"),
])
def test_malformed_unique_keys_are_refused_at_parse(keys, message):
    data = _pack_data()
    data["object_types"][0]["unique_keys"] = keys

    with pytest.raises(OntologyError, match=message):
        parse_domain_pack(data)


def test_a_structured_object_cannot_be_part_of_a_key():
    with pytest.raises(OntologyError, match="structured_object"):
        _pack([[CODE]], code_type="structured_object")


@pytest.mark.parametrize("keys, message", [
    ((("uk:Customer.unknown",),), "not mapped"),
    (((),), "not mapped"),
])
def test_a_hand_built_pack_with_an_unusable_key_fails_closed(tmp_path, keys, message):
    import_id = _import(tmp_path, ["C1,x@example.test,a"])
    pack = _pack()
    pack = replace(pack, object_types=(replace(pack.object_types[0], unique_keys=keys),))

    with pytest.raises(OntologyError, match=message):
        _read_all(pack, tmp_path, import_id)


def _codes(old, new):
    return {(item.code, item.level) for item in compare_packs(old, new).changes}


@pytest.mark.parametrize("before, after, expected", [
    (None, [[EMAIL]], {("unique_key_added", "breaking")}),
    ([[EMAIL]], None, {("unique_key_removed", "breaking")}),
    ([[EMAIL]], [[CODE]], {("unique_key_added", "breaking"), ("unique_key_removed", "breaking")}),
    ([[EMAIL, CODE], [CODE]], [[CODE], [CODE, EMAIL]], {("unique_keys_reordered", "compatible")}),
])
def test_compatibility_classifies_unique_key_changes(before, after, expected):
    assert _codes(_pack(before), _pack(after, version="2.0.0")) == expected

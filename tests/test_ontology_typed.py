"""Typed client generation. All data is synthetic."""

from __future__ import annotations

import ast
import copy
import dataclasses
import os
import subprocess
import sys
import types
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, parse_domain_pack
from agora.ontology.binding import load_binding, materialize_instances
from agora.ontology.loader import load_domain_pack
from agora.ontology.typed import generate_python_types, main
from agora.tabular import ingest_csv


ROOT = Path(__file__).resolve().parents[1]
PACKS = sorted((ROOT / "domain_packs").glob("*/pack.yaml"))
RETAIL = ROOT / "domain_packs" / "retail_in"


def _load(source: str, name: str = "generated_ontology"):
    module = types.ModuleType(name)
    # dataclasses looks the defining module up in sys.modules.
    sys.modules[name] = module
    try:
        exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    finally:
        del sys.modules[name]
    return module


def _prop(local, data_type="string", **extra):
    return {"property_id": f"t:Thing.{local}", "version": "1.0.0", "name": local,
            "data_type": data_type, "required": True, "nullable": False,
            "sensitivity": "internal", **extra}


def _pack_data(*props, type_id="t:Thing"):
    props = props or (_prop("code", "identifier"),)
    return {
        "pack_id": "typed-pack", "schema_version": "1.0.0",
        "object_types": [{
            "type_id": type_id, "version": "1.0.0", "name": "Thing", "description": "Synthetic",
            "properties": [item["property_id"] for item in props], "identity_strategy": "record_key",
        }],
        "property_types": list(props), "link_types": [], "action_types": [],
    }


def _instance(values, *, type_id="t:Thing", sensitivity="internal"):
    full = {f"t:Thing.{key}": value for key, value in values.items()}
    return {
        "object_type_id": type_id, "object_type_version": "1.0.0", "property_values": full,
        "property_sensitivity": {key: sensitivity for key in full},
        "record_key": "key-1", "import_id": "import-1", "row_id": "row-1", "dataset_id": "things",
        "binding_id": "things.v1", "binding_version": "1.0.0", "binding_fingerprint": "f" * 64,
        "file_sha256": "a" * 64, "source_registry_id": None,
    }


def _thing(*props):
    return _load(generate_python_types(parse_domain_pack(_pack_data(*props))))


@pytest.mark.parametrize("path", PACKS, ids=lambda path: path.parent.name)
def test_shipped_packs_generate_the_same_loadable_module_twice(path):
    pack = load_domain_pack(path)
    source = generate_python_types(pack)
    assert source == generate_python_types(load_domain_pack(path))
    assert source.isascii()
    module = _load(source)
    assert module.PACK_FINGERPRINT == pack.fingerprint
    assert set(module.OBJECT_TYPES) == {(item.type_id, item.version) for item in pack.object_types}


def test_generated_module_imports_only_the_standard_library():
    tree = ast.parse(generate_python_types(load_domain_pack(RETAIL / "pack.yaml")))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
    assert imported == {"__future__", "re", "collections.abc", "dataclasses", "datetime", "decimal"}


def _retail(tmp_path):
    pack = load_domain_pack(RETAIL / "pack.yaml")
    source = tmp_path / "sample.csv"
    source.write_bytes((RETAIL / "sample.csv").read_bytes())
    schema = yaml.safe_load((RETAIL / "schema.yaml").read_text(encoding="utf-8"))
    result = ingest_csv(tmp_path, source, schema, data_role="context")
    return pack, load_binding(RETAIL / "binding.yaml"), result["import_id"]


def test_materialized_retail_rows_become_typed_objects(tmp_path):
    pack, binding, import_id = _retail(tmp_path)
    module = _load(generate_python_types(pack))
    rows = materialize_instances(binding, pack, tmp_path, import_id)
    customers = [module.Customer.from_instance(row) for row in rows]
    assert len(customers) == 30
    first = customers[0]
    assert (first.age, first.spend, first.joined_on, first.opted_in) == (
        21, Decimal("12.50"), date(2024, 1, 1), True)
    assert str(first.spend) == "12.50"
    assert first.provenance.import_id == import_id
    assert first.provenance.record_key == rows[0]["record_key"]
    assert dict(first.provenance.property_sensitivity) == rows[0]["property_sensitivity"]
    assert len(set(customers)) == 30  # frozen and hashable
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.age = 99


def test_objects_read_through_the_store_fit_the_generated_type(tmp_path):
    def allow(operation, resource):
        return {"decision": "allow", "reason": "policy_allow", "subject_id": "typed-test",
                "policy_version": "typed-test-v1", "resource_ids": list(resource["resource_ids"])}

    pack, binding, import_id = _retail(tmp_path)
    module = _load(generate_python_types(pack))
    audit = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    store = OntologyObjectStore(tmp_path)
    assert store.register_pack(pack, policy=allow, audit=audit) == module.PACK_FINGERPRINT
    binding_fingerprint = store.register_binding(module.PACK_FINGERPRINT, binding, policy=allow, audit=audit)
    store.materialize_binding(
        module.PACK_FINGERPRINT, binding_fingerprint, import_id, policy=allow, audit=audit,
        purpose="synthetic_test", retention="test_only")
    page = store.query_objects(
        module.PACK_FINGERPRINT, module.Customer.TYPE_ID, module.Customer.TYPE_VERSION, import_id,
        {}, 5, None, policy=allow, audit=audit, purpose="synthetic_test", retention="test_only")
    assert len(page["objects"]) == 5
    for row in page["objects"]:
        assert module.Customer.from_instance(row).provenance.record_key == row["record_key"]


def test_repr_shows_no_property_value(tmp_path):
    pack, binding, import_id = _retail(tmp_path)
    module = _load(generate_python_types(pack))
    row = materialize_instances(binding, pack, tmp_path, import_id)[0]
    shown = repr(module.Customer.from_instance(row))
    for value in ("synthetic001@example.test", "C001", "12.50", "2024"):
        assert value not in shown


def test_each_data_type_is_converted():
    module = _thing(
        _prop("code", "identifier"), _prop("count", "integer"), _prop("amount", "decimal"),
        _prop("live", "boolean"), _prop("day", "date"), _prop("seen", "timestamp"),
        _prop("label"), _prop("state", "enum"))
    got = module.Thing.from_instance(_instance({
        "code": "A", "count": 3, "amount": 7, "live": False, "day": "2026-01-31",
        "seen": "2026-01-31T10:00:00+00:00", "label": "", "state": "open"}))
    assert type(got.amount) is Decimal and got.amount == 7
    assert got.day == date(2026, 1, 31)
    assert got.seen == datetime(2026, 1, 31, 10, tzinfo=timezone.utc)
    assert (got.code, got.count, got.live, got.label, got.state) == ("A", 3, False, "", "open")


@pytest.mark.parametrize("data_type, value", [
    ("string", 5), ("string", b"x"), ("integer", True), ("integer", "5"), ("integer", 5.0),
    ("boolean", 1), ("boolean", "true"), ("decimal", 1.5), ("decimal", True), ("decimal", "abc-secret"),
    ("decimal", "NaN"), ("decimal", "Infinity"), ("decimal", " 5"), ("decimal", "1_000"),
    ("decimal", "1e3"), ("decimal", "5\n"), ("date", "20260131"), ("date", "2026-13-01"),
    ("date", date(2026, 1, 1)), ("timestamp", "2026-01-31T10:00:00"),
    ("timestamp", "2026-01-31T10:00:00Z"), ("timestamp", "2026-01-31T15:30:00+05:30"),
    ("timestamp", "0001-01-01T00:00:00+05:30"),
])
def test_a_value_of_the_wrong_form_is_refused(data_type, value):
    module = _thing(_prop("v", data_type))
    with pytest.raises(module.InstanceError, match="t:Thing.v does not have its declared data type") as caught:
        module.Thing.from_instance(_instance({"v": value}))
    assert str(caught.value) == "t:Thing.v does not have its declared data type"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_nullability_follows_the_pack():
    strict = _thing(_prop("v"))
    with pytest.raises(strict.InstanceError, match="not nullable"):
        strict.Thing.from_instance(_instance({"v": None}))
    loose = _thing(_prop("v", "integer", nullable=True, allowed_values=[1, None]))
    assert loose.Thing.from_instance(_instance({"v": None})).v is None
    assert loose.Thing.from_instance(_instance({"v": 1})).v == 1


@pytest.mark.parametrize("data_type, allowed, good, bad", [
    ("enum", ["open", "closed"], "open", "OPEN"),
    ("integer", [1, 2], 2, 3),
    ("decimal", [1.5, "2.50"], "1.50", "1.51"),
    ("boolean", [True], True, False),
    ("date", ["2026-01-01"], "2026-01-01", "2026-01-02"),
])
def test_allowed_values_are_enforced(data_type, allowed, good, bad):
    module = _thing(_prop("v", data_type, allowed_values=allowed))
    module.Thing.from_instance(_instance({"v": good}))
    with pytest.raises(module.InstanceError, match="not an allowed value"):
        module.Thing.from_instance(_instance({"v": bad}))


def _without(key):
    def change(row):
        del row[key]
    return change


@pytest.mark.parametrize("change, message", [
    (lambda row: row.update(object_type_id="t:Other"), "not of this object type"),
    (lambda row: row.update(object_type_version="2.0.0"), "not of this object type"),
    (lambda row: row["property_values"].update({"t:Thing.extra": 1}), "exactly the properties"),
    (lambda row: row["property_values"].clear(), "exactly the properties"),
    (_without("property_values"), "exactly the properties"),
    (_without("property_sensitivity"), "classify exactly"),
    (lambda row: row["property_sensitivity"].clear(), "classify exactly"),
    (lambda row: row["property_sensitivity"].update({"t:Thing.extra": "public"}), "classify exactly"),
    (lambda row: row["property_sensitivity"].update({"t:Thing.v": "public"}), "below the declared"),
    (lambda row: row["property_sensitivity"].update({"t:Thing.v": "secret"}), "below the declared"),
    (_without("record_key"), "provenance field record_key"),
    (lambda row: row.update(import_id=""), "provenance field import_id"),
    (_without("binding_fingerprint"), "provenance field binding_fingerprint"),
    (lambda row: row.update(file_sha256=5), "provenance field file_sha256"),
])
def test_an_instance_that_does_not_fit_is_refused(change, message):
    module = _thing(_prop("v"))
    row = _instance({"v": "x"})
    change(row)
    with pytest.raises(module.InstanceError, match=message):
        module.Thing.from_instance(row)


def test_non_mapping_is_refused_and_a_raised_classification_is_kept():
    module = _thing(_prop("v"))
    with pytest.raises(module.InstanceError, match="mapping"):
        module.Thing.from_instance([])
    got = module.Thing.from_instance(_instance({"v": "x"}, sensitivity="sensitive"))
    assert got.provenance.property_sensitivity == (("t:Thing.v", "sensitive"),)


# Each string would run or break the module if written out unescaped.
HOSTILE = [
    '"); raise SystemExit("ran") #', "'''\nraise SystemExit('ran')\n'''", '\\', "a\nimport os",
    "‮ raise SystemExit()", "{0}", "\x00",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_pack_text_stays_data_in_the_generated_module(text):
    data = _pack_data(_prop("v", "enum", allowed_values=[text, "ok"], units=f"u{text}"))
    data["pack_id"] = f"p{text}p"
    data["object_types"][0]["name"] = f"n{text}"
    data["object_types"][0]["description"] = f"d{text}"
    data["property_types"][0]["name"] = f"n{text}"
    pack = parse_domain_pack(data)
    source = generate_python_types(pack)
    assert source.isascii() and "\x00" not in source
    module = _load(source)
    assert module.PACK_ID == pack.pack_id
    assert module.Thing.from_instance(_instance({"v": text})).v == text
    clean = copy.deepcopy(data)
    clean["pack_id"] = "p"
    clean["property_types"][0]["allowed_values"] = ["x", "ok"]
    # Only literal contents differ from a module made from plain text.
    def shape(value):
        tree = ast.parse(value)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                node.value = ""
        return ast.dump(tree)
    assert shape(source) == shape(generate_python_types(parse_domain_pack(clean)))


@pytest.mark.parametrize("local", [
    "class", "None", "with space", "a-b", "1st", "_hidden", "__class__", "provenance",
    "from_instance", "TYPE_ID", "classmethod", "str", "int", "bool", "x: int = 0\n    y",
    "café",
])
def test_an_unusable_property_name_is_refused(local):
    pack = parse_domain_pack(_pack_data(_prop("v")))
    bad = dataclasses.replace(pack.property_types[0], property_id=f"t:Thing.{local}")
    pack = dataclasses.replace(
        pack, property_types=(bad,),
        object_types=(dataclasses.replace(pack.object_types[0], properties=(bad.property_id,)),))
    with pytest.raises(OntologyError, match="no usable Python name"):
        generate_python_types(pack)


@pytest.mark.parametrize("local", [
    "lower", "ValueError", "Exception", "True", "InstanceError", "Provenance", "OBJECT_TYPES",
    "PACK_ID", "_Decimal", "A B", "A(object): pass\nclass B",
])
def test_an_unusable_class_name_is_refused(local):
    with pytest.raises(OntologyError, match="no usable Python name"):
        generate_python_types(parse_domain_pack(_pack_data(type_id=f"t:{local}")))


def test_names_that_would_shadow_a_helper_still_work():
    names = ["field", "dataclass", "date", "datetime", "Decimal", "id", "type", "property", "self", "Thing"]
    module = _thing(*[_prop(name) for name in names], _prop("when", "date"))
    row = _instance({**{name: name for name in names}, "when": "2026-01-01"})
    got = module.Thing.from_instance(row)
    assert [getattr(got, name) for name in names] == names
    assert got.when == date(2026, 1, 1)


def test_colliding_names_are_refused():
    first, second = _prop("v"), {**_prop("v"), "property_id": "u:Other.v"}
    with pytest.raises(OntologyError, match="same Python name"):
        generate_python_types(parse_domain_pack(_pack_data(first, second)))
    data = _pack_data()
    data["object_types"].append({**data["object_types"][0], "type_id": "u:Thing"})
    with pytest.raises(OntologyError, match="same Python class name"):
        generate_python_types(parse_domain_pack(data))


def test_a_structured_object_property_is_refused():
    with pytest.raises(OntologyError, match="no typed form"):
        generate_python_types(parse_domain_pack(_pack_data(_prop("v", "structured_object"))))


def test_an_allowed_list_of_only_null_is_not_read_as_unrestricted():
    pack = parse_domain_pack(_pack_data(_prop("v", nullable=True, allowed_values=[None])))
    with pytest.raises(OntologyError, match="only null"):
        generate_python_types(pack)


def test_generation_needs_a_parsed_pack():
    with pytest.raises(OntologyError, match="parsed OntologyPack"):
        generate_python_types(_pack_data())


def test_command_prints_the_module_or_exits_2(capsys, tmp_path):
    assert main([str(RETAIL / "pack.yaml")]) == 0
    assert capsys.readouterr().out == generate_python_types(load_domain_pack(RETAIL / "pack.yaml"))
    for arguments in ([], ["--help"], [str(tmp_path / "missing.yaml")], ["a", "b"]):
        assert main(arguments) == 2
        assert capsys.readouterr().out == ""


def test_printed_module_runs_without_agora_on_the_path(tmp_path):
    source = generate_python_types(load_domain_pack(RETAIL / "pack.yaml"))
    (tmp_path / "retail_types.py").write_text(source, encoding="utf-8")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import retail_types, typing; "
            "typing.get_type_hints(retail_types.Customer); "
            "assert not any(m == 'agora' or m.startswith('agora.') for m in sys.modules)")
    done = subprocess.run([sys.executable, "-I", "-c", code, str(tmp_path)],
                          capture_output=True, text=True, cwd=tmp_path, env=dict(os.environ))
    assert done.returncode == 0, done.stderr

import copy
import json

import pytest

from agora.ontology import OntologyError, parse_domain_pack
from agora.ontology.compat import BREAKING, COMPATIBLE, compare_packs, main, require_release


def base():
    return {
        "pack_id": "test.pack",
        "schema_version": "1.0.0",
        "property_types": [
            {"property_id": "t:id", "version": "1.0.0", "name": "Id", "data_type": "identifier",
             "required": True, "nullable": False, "sensitivity": "internal"},
            {"property_id": "t:state", "version": "1.0.0", "name": "State", "data_type": "enum",
             "required": False, "nullable": True, "sensitivity": "internal", "allowed_values": ["a", "b"]},
        ],
        "object_types": [
            {"type_id": "t:thing", "version": "1.0.0", "name": "Thing", "description": "A thing.",
             "properties": ["t:id", "t:state"], "identity_strategy": "record_key"},
        ],
        "link_types": [
            {"link_type_id": "t:rel", "version": "1.0.0", "name": "Rel", "source_type_id": "t:thing",
             "target_type_id": "t:thing", "predicate": "relates", "cardinality": "one_to_many"},
        ],
        "action_types": [
            {"action_type_id": "t:act", "version": "1.0.0", "name": "Act", "actor_type_id": "t:thing",
             "target_type_id": "t:thing", "inputs": [], "preconditions": [], "effects": [],
             "permissions": ["p:run"], "simulated_only": True, "execution_mode": "simulation_only",
             "external_writeback": "prohibited"},
        ],
    }


def diff(mutate):
    new = base()
    mutate(new)
    return compare_packs(parse_domain_pack(base()), parse_domain_pack(new))


def codes(report):
    return {(v.kind, v.code) for v in report.violations}


def edit(section, index, key, value, version="2.0.0", pack="2.0.0", obj=None):
    def apply(data):
        data[section][index][key] = value
        data[section][index]["version"] = version
        data["schema_version"] = pack
        if obj:
            data["object_types"][0]["version"] = obj
    return apply


def test_identical_packs_have_no_changes():
    report = diff(lambda data: None)
    assert report.changes == () and report.violations == () and not report.breaking
    assert report.old_fingerprint == report.new_fingerprint


@pytest.mark.parametrize("section,index,key,value", [
    ("object_types", 0, "identity_strategy", "assigned"),
    ("object_types", 0, "source_binding", {"source_registry_id": "s", "locator": "l"}),
    ("property_types", 0, "data_type", "string"),
    ("property_types", 0, "required", False),
    ("property_types", 0, "nullable", True),
    ("property_types", 0, "units", "kg"),
    ("property_types", 0, "timezone", "UTC"),
    ("property_types", 0, "precision", 4),
    ("property_types", 1, "allowed_values", ["a", "b", "c"]),
    ("property_types", 1, "allowed_values", ["a"]),
    ("property_types", 1, "allowed_values", []),
    ("link_types", 0, "predicate", "other"),
    ("link_types", 0, "cardinality", "many_to_many"),
    ("link_types", 0, "cardinality", "one_to_one"),
    ("action_types", 0, "permissions", []),
    ("action_types", 0, "preconditions", ["x"]),
    ("action_types", 0, "effects", ["x"]),
    ("action_types", 0, "inputs", ["x"]),
])
def test_semantic_edit_is_breaking_and_needs_major(section, index, key, value):
    obj = "2.0.0" if section == "property_types" else None
    good = diff(edit(section, index, key, value, obj=obj))
    assert good.breaking and good.violations == ()
    assert any(c.level == BREAKING and c.code == f"{key}_changed" for c in good.changes)
    minor = diff(edit(section, index, key, value, version="1.1.0", obj=obj))
    assert "breaking_change_without_major_increase" in {v.code for v in minor.violations}


@pytest.mark.parametrize("new,code", [("sensitive", "sensitivity_raised"), ("public", "sensitivity_lowered")])
def test_sensitivity_change_is_named_and_breaking(new, code):
    report = diff(edit("property_types", 0, "sensitivity", new, obj="2.0.0"))
    assert [(c.code, c.level) for c in report.changes if c.kind == "PropertyType"] == [(code, BREAKING)]


@pytest.mark.parametrize("section", ["object_types", "property_types", "link_types", "action_types"])
def test_label_change_is_compatible_but_still_needs_a_version_increase(section):
    report = diff(edit(section, 0, "name", "Renamed", version="1.1.0", pack="1.1.0"))
    assert [c.level for c in report.changes] == [COMPATIBLE]
    assert report.violations == () and not report.breaking
    silent = diff(edit(section, 0, "name", "Renamed", version="1.0.0", pack="1.1.0"))
    assert [v.code for v in silent.violations] == ["content_changed_without_version_increase"]


@pytest.mark.parametrize("key,value,section,index,code", [
    ("allowed_values", ["b", "a"], "property_types", 1, "allowed_values_reordered"),
    ("properties", ["t:state", "t:id"], "object_types", 0, "properties_reordered"),
])
def test_reorder_is_compatible(key, value, section, index, code):
    report = diff(edit(section, index, key, value, version="1.0.1", pack="1.0.1"))
    assert [(c.code, c.level) for c in report.changes] == [(code, COMPATIBLE)]
    assert report.violations == ()


def test_allowed_value_of_another_scalar_type_is_a_change():
    old = base()
    old["property_types"][1]["allowed_values"] = [1]
    new = copy.deepcopy(old)
    new["property_types"][1]["allowed_values"] = [True]
    report = compare_packs(parse_domain_pack(old), parse_domain_pack(new))
    assert [(c.code, c.level) for c in report.changes] == [("allowed_values_changed", BREAKING)]


def test_breaking_property_change_requires_object_major():
    report = diff(edit("property_types", 0, "data_type", "string"))
    assert codes(report) == {("ObjectType", "object_without_major_increase_for_property_change")}


def test_property_added_to_object_is_breaking():
    def apply(data):
        data["property_types"].append({"property_id": "t:note", "version": "1.0.0", "name": "Note",
            "data_type": "string", "required": False, "nullable": True, "sensitivity": "internal"})
        data["object_types"][0]["properties"].append("t:note")
        data["object_types"][0]["version"] = "1.1.0"
        data["schema_version"] = "2.0.0"
    report = diff(apply)
    assert ("property_added_to_object", BREAKING) in {(c.code, c.level) for c in report.changes}
    assert codes(report) == {("ObjectType", "breaking_change_without_major_increase")}


def test_property_removed_from_object_is_breaking():
    def apply(data):
        data["object_types"][0]["properties"] = ["t:id"]
        data["object_types"][0]["version"] = "2.0.0"
        data["schema_version"] = "2.0.0"
    report = diff(apply)
    assert [(c.code, c.level) for c in report.changes] == [("property_removed_from_object", BREAKING)]
    assert report.violations == ()


@pytest.mark.parametrize("section", ["link_types", "action_types"])
def test_removal_is_breaking_and_addition_is_compatible(section):
    def remove(data):
        data[section] = []
        data["schema_version"] = "1.1.0"
    removed = diff(remove)
    assert [c.code for c in removed.changes] == ["definition_removed"]
    assert codes(removed) == {("OntologyPack", "breaking_change_without_major_increase")}

    old = base()
    old[section] = []
    new = base()
    new["schema_version"] = "1.1.0"
    added = compare_packs(parse_domain_pack(old), parse_domain_pack(new))
    assert [(c.code, c.level) for c in added.changes] == [("definition_added", COMPATIBLE)]
    assert added.violations == ()


def test_pack_version_must_increase_when_content_changes():
    report = diff(edit("link_types", 0, "name", "R2", version="1.1.0", pack="1.0.0"))
    assert codes(report) == {("OntologyPack", "content_changed_without_version_increase")}


def test_pack_version_must_increase_when_only_a_definition_version_moves():
    def apply(data):
        data["link_types"][0]["version"] = "1.0.1"
    assert codes(diff(apply)) == {("OntologyPack", "content_changed_without_version_increase")}


def test_decreases_are_refused_even_without_content_change():
    def definition(data):
        data["link_types"][0]["version"] = "0.9.0"
        data["schema_version"] = "1.0.1"
    assert codes(diff(definition)) == {("LinkType", "version_decreased")}
    def pack(data):
        data["schema_version"] = "0.9.0"
    assert codes(diff(pack)) == {("OntologyPack", "version_decreased")}


@pytest.mark.parametrize("old,new,ok", [
    ("1.0.0-alpha.2", "1.0.0-alpha.10", True),
    ("1.0.0-alpha.10", "1.0.0-alpha.2", False),
    ("1.0.0-rc.1", "1.0.0", True),
    ("1.0.0", "1.0.0-rc.1", False),
    ("1.0.0-1", "1.0.0-alpha", True),
    ("1.0.0+a", "1.0.0+b", False),
    ("1.9.0", "1.10.0", True),
])
def test_semantic_version_precedence(old, new, ok):
    first, second = base(), base()
    first["link_types"][0]["version"] = old
    second["link_types"][0].update(version=new, name="Changed")
    second["schema_version"] = "1.0.1"
    report = compare_packs(parse_domain_pack(first), parse_domain_pack(second))
    assert (report.violations == ()) is ok


def test_different_packs_and_duplicate_definitions_are_refused():
    other = base()
    other["pack_id"] = "other"
    with pytest.raises(OntologyError, match="different packs"):
        compare_packs(parse_domain_pack(base()), parse_domain_pack(other))
    pack = parse_domain_pack(base())
    from dataclasses import replace
    doubled = replace(pack, link_types=pack.link_types * 2)
    with pytest.raises(OntologyError, match="more than one"):
        compare_packs(pack, doubled)


def test_require_release_gates():
    old = parse_domain_pack(base())
    new = base()
    edit("link_types", 0, "predicate", "other")(new)
    broke = parse_domain_pack(new)
    with pytest.raises(OntologyError, match="breaking changes"):
        require_release(old, broke)
    with pytest.raises(OntologyError, match="breaking changes"):
        require_release(old, broke, allow_breaking="yes")
    assert require_release(old, broke, allow_breaking=True).breaking
    bad = base()
    bad["link_types"][0]["predicate"] = "other"
    with pytest.raises(OntologyError, match="version rules"):
        require_release(old, parse_domain_pack(bad), allow_breaking=True)


def test_command_line_exit_codes(tmp_path, capsys):
    old, broke, silent = base(), base(), base()
    edit("link_types", 0, "predicate", "other")(broke)
    silent["link_types"][0]["predicate"] = "other"
    paths = {}
    for name, data in {"old": old, "broke": broke, "silent": silent}.items():
        paths[name] = str(tmp_path / f"{name}.json")
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    assert main([paths["old"], paths["old"]]) == 0
    assert json.loads(capsys.readouterr().out)["release_allowed"] is True
    assert main([paths["old"], paths["broke"]]) == 1
    assert json.loads(capsys.readouterr().out)["release_allowed"] is False
    assert main([paths["old"], paths["broke"], "--allow-breaking"]) == 0
    capsys.readouterr()
    assert main([paths["old"], paths["silent"], "--allow-breaking"]) == 1
    capsys.readouterr()
    assert main([paths["old"], str(tmp_path / "missing.json")]) == 2
    assert capsys.readouterr().out == ""

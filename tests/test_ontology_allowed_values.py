"""Pack parsing refuses allowed values that no source value could equal."""

import pytest

from agora.ontology import OntologyError, parse_domain_pack


def _pack(data_type, allowed, *, nullable=False):
    return {
        "pack_id": "av-pack", "schema_version": "1.0.0",
        "object_types": [], "link_types": [], "action_types": [],
        "property_types": [{
            "property_id": "av:Item.value", "version": "1.0.0", "name": "value",
            "data_type": data_type, "required": True, "nullable": nullable,
            "sensitivity": "internal", "allowed_values": allowed,
        }],
    }


@pytest.mark.parametrize("data_type, allowed", [
    ("string", ["a", ""]), ("identifier", ["a"]), ("enum", ["a"]),
    (" enum ", ["a"]),
    ("integer", [0, -3]), ("boolean", [True, False]),
    ("decimal", [1, 1.5, "2.50", "-0.1"]),
    ("date", ["2026-02-28"]),
    ("timestamp", ["2026-02-28T23:59:59+00:00", "2026-02-28T23:59:59.500000+00:00"]),
    ("structured_object", []), ("integer", []),
])
def test_matching_values_are_accepted_unchanged(data_type, allowed):
    pack = parse_domain_pack(_pack(data_type, allowed))
    assert pack.property_types[0].allowed_values == tuple(allowed)


@pytest.mark.parametrize("data_type, value", [
    ("string", 1), ("identifier", True), ("enum", 1.5),
    ("integer", True), ("integer", 1.0), ("integer", "1"),
    ("boolean", 1), ("boolean", "true"),
    ("decimal", True), ("decimal", "secret-text"), ("decimal", "NaN"), ("decimal", "Infinity"),
    ("date", 20260131), ("date", "20260131"), ("date", "2026-02-30"), ("date", "2026-01-31T00:00:00"),
    ("timestamp", 0), ("timestamp", "secret-text"), ("timestamp", "2026-01-31"),
    ("timestamp", "2026-01-31T10:00:00"), ("timestamp", "2026-01-31T10:00:00Z"),
    ("timestamp", "2026-01-31T15:30:00+05:30"), ("timestamp", "0001-01-01T00:00:00+05:30"),
    ("structured_object", "a"),
])
def test_values_that_could_never_match_are_refused(data_type, value):
    with pytest.raises(OntologyError, match=r"allowed_values\[0\] does not match data_type") as caught:
        parse_domain_pack(_pack(data_type, [value]))
    assert "secret-text" not in str(caught.value)


def test_every_entry_is_checked():
    with pytest.raises(OntologyError, match=r"allowed_values\[2\]"):
        parse_domain_pack(_pack("string", ["a", "b", 3]))


def test_null_entry_follows_nullability():
    assert parse_domain_pack(_pack("string", ["a", None], nullable=True))
    with pytest.raises(OntologyError, match="not nullable"):
        parse_domain_pack(_pack("string", ["a", None]))


def test_an_integer_too_long_to_print_is_refused_as_an_ontology_error():
    with pytest.raises(OntologyError):
        parse_domain_pack(_pack("decimal", [10 ** 10000]))

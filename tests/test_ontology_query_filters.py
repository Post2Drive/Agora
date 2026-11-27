"""Query filters compare decimals, dates and timestamps by value, not by stored text."""

from __future__ import annotations

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore
from test_ontology_typed import _retail

SPEND, JOINED, AGE, EMAIL = (f"retail:Customer.{name}" for name in ("spend", "joined_on", "age", "email"))
SCOPE = {"purpose": "synthetic_test", "retention": "test_only"}


def _allow(operation, resource):
    return {"decision": "allow", "reason": "policy_allow", "subject_id": "filter-test",
            "policy_version": "filter-test-v1", "resource_ids": list(resource["resource_ids"])}


@pytest.fixture
def query(tmp_path):
    """Query 30 synthetic retail rows through the real store."""
    pack, binding, import_id = _retail(tmp_path)
    audit = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    store = OntologyObjectStore(tmp_path)
    fingerprint = store.register_pack(pack, policy=_allow, audit=audit)
    binding_fp = store.register_binding(fingerprint, binding, policy=_allow, audit=audit)
    store.materialize_binding(fingerprint, binding_fp, import_id, policy=_allow, audit=audit, **SCOPE)
    kind = pack.object_types[0]

    def run(filters):
        page = store.query_objects(
            fingerprint, kind.type_id, kind.version, import_id, filters, 100, None,
            policy=_allow, audit=audit, **SCOPE)
        assert page["next_cursor"] is None
        return [row["property_values"] for row in page["objects"]]

    return run


def _where(property_id, op, value):
    return {property_id: {"op": op, "value": value}}


def test_decimal_filters_compare_numbers(query):
    from decimal import Decimal
    spends = [Decimal(row[SPEND]) for row in query({}) if row[SPEND] is not None]
    assert "12.50" in {row[SPEND] for row in query({})}
    # Equality ignores how many zeros the stored or the asked text carries.
    for asked in ("12.5", "12.50", "12.500"):
        found = query(_where(SPEND, "eq", asked))
        assert found and {Decimal(row[SPEND]) for row in found} == {Decimal("12.5")}
    assert len(query(_where(SPEND, "in", ["12.5"]))) == len(query(_where(SPEND, "eq", "12.50")))
    # Numeric order, not text order: as text "9" sorts after "12.50".
    for op, test in (("gt", lambda x: x > 9), ("gte", lambda x: x >= 9),
                     ("lt", lambda x: x < 9), ("lte", lambda x: x <= 9)):
        for asked in (9, "9"):
            found = [Decimal(row[SPEND]) for row in query(_where(SPEND, op, asked))]
            assert sorted(found) == sorted(x for x in spends if test(x))


def test_date_filters_compare_dates(query):
    rows = query({})
    pivot = sorted(row[JOINED] for row in rows if row[JOINED])[len(rows) // 3]
    after = query(_where(JOINED, "gt", pivot))
    assert after and {row[JOINED] for row in after} == {
        row[JOINED] for row in rows if row[JOINED] and row[JOINED] > pivot}


@pytest.mark.parametrize("property_id, value", [
    (SPEND, 12.5), (SPEND, "12,5"), (SPEND, "1e1"), (SPEND, "NaN"), (SPEND, " 12.5"),
    (SPEND, "1_000"), (SPEND, True),
    (JOINED, "abc"), (JOINED, "20240101"), (JOINED, "2024-02-30"), (JOINED, 20240101),
    (AGE, "21"), (AGE, True), (AGE, 21.0), (EMAIL, 1),
])
def test_an_unusable_operand_is_refused_without_repeating_it(query, property_id, value):
    for op, operand in (("eq", value), ("gt", value), ("in", [value])):
        with pytest.raises(OntologyError) as caught:
            query(_where(property_id, op, operand))
        assert "does not match property type" in str(caught.value)
        assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
def test_ordering_against_null_is_refused(op):
    prop = type("P", (), {"property_id": "t:T.v", "data_type": "integer", "nullable": True,
                          "allowed_values": ()})()
    pack = type("Pack", (), {
        "object_types": (type("O", (), {"type_id": "t:T", "properties": ("t:T.v",)})(),),
        "property_types": (prop,)})()
    with pytest.raises(OntologyError, match="non-null filter value"):
        OntologyObjectStore._validate_filters(pack, "t:T", _where("t:T.v", op, None))


def _match(data_type, stored, op, operand):
    prop = type("P", (), {"data_type": data_type, "nullable": True, "allowed_values": ()})()
    check = OntologyObjectStore._validate_filter_value
    asked = [check(prop, item) for item in operand] if op == "in" else check(prop, operand)
    return OntologyObjectStore._matches_filters({"p": stored}, [("p", data_type, op, asked)])


def test_timestamps_compare_as_instants():
    stored = "2026-01-31T10:00:00+00:00"
    for same in ("2026-01-31T10:00:00Z", "2026-01-31T15:30:00+05:30", stored):
        assert _match("timestamp", stored, "eq", same)
        assert _match("timestamp", stored, "in", [same])
    assert _match("timestamp", stored, "gt", "2026-01-31T14:00:00+05:30")
    assert not _match("timestamp", stored, "lt", "2026-01-31T14:00:00+05:30")


@pytest.mark.parametrize("value", ["2026-01-31T10:00:00", "2026-01-31", "soon",
                                   "0001-01-01T00:00:00+05:30"])
def test_a_timestamp_operand_needs_a_usable_instant(value):
    with pytest.raises(OntologyError, match="does not match property type timestamp"):
        _match("timestamp", "2026-01-31T10:00:00+00:00", "eq", value)


def test_large_integers_and_integer_backed_decimals_stay_exact():
    assert _match("decimal", "12345678901234567.89", "gt", "12345678901234567.88")
    assert not _match("decimal", "12345678901234567.89", "eq", "12345678901234567.88")
    # An integer column may feed a decimal property.
    assert _match("decimal", 7, "eq", "7.0")


def test_null_matches_only_null():
    assert _match("decimal", None, "eq", None)
    assert _match("decimal", None, "in", ["1", None])
    assert not _match("decimal", None, "gt", 0)
    assert not _match("decimal", "1", "eq", None)


@pytest.mark.parametrize("data_type, stored", [
    ("decimal", "private-1"), ("date", "private-2"), ("timestamp", "private-3"), ("integer", "private-4"),
])
def test_an_incomparable_stored_value_is_an_error_not_a_non_match(data_type, stored):
    operand = {"decimal": 1, "date": "2026-01-01", "timestamp": "2026-01-01T00:00:00Z", "integer": 1}[data_type]
    with pytest.raises(OntologyError, match="cannot be compared") as caught:
        _match(data_type, stored, "eq", operand)
    assert "private" not in str(caught.value)

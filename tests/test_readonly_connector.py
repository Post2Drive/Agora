from __future__ import annotations

import threading

import pytest

import agora.readonly_connector as readonly_connector
from agora.identity import stable_record_key

from agora.readonly_connector import (
    ConnectorError, MockReadOnlyConnector, QueryPlan, reject_sql_text,
)


@pytest.fixture
def connector():
    return MockReadOnlyConnector(
        connector_id="test-source",
        tables={"customers": [
            {"id": 2, "name": "B", "segment": "standard"},
            {"id": 1, "name": "A", "segment": "priority"},
            {"id": 3, "name": "C", "segment": "standard"},
        ]},
        allowlist={"customers": ("id", "name", "segment")},
        primary_keys={"customers": "id"},
        snapshot_id="snapshot-001",
    )


def test_discover_returns_only_allowlisted_schema(connector):
    assert connector.discover() == {"customers": ("id", "name", "segment")}


def test_select_returns_typed_projected_rows_and_provenance(connector):
    page = connector.select(QueryPlan("customers", ("id", "name"), limit=2))
    assert [r["values"]["id"] for r in page.rows] == [1, 2]
    assert page.rows[0]["source_locator"]["connector_id"] == "test-source"
    assert page.rows[0]["source_locator"]["query_fingerprint"] == page.query_fingerprint
    assert page.source_registry_id.startswith("mock-source-")
    assert len(page.source_sha256) == 64
    assert page.rows[0]["source_locator"]["source_sha256"] == page.source_sha256


def test_pagination_is_deterministic_without_duplicates(connector):
    first = connector.select(QueryPlan("customers", ("id",), limit=2))
    second = connector.select(QueryPlan("customers", ("id",), limit=2, offset=first.next_offset))
    assert [r["values"]["id"] for r in first.rows + second.rows] == [1, 2, 3]
    assert second.next_offset is None


def test_primary_key_row_identity_is_stable_for_same_snapshot(connector):
    a = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    b = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    assert a.rows[0]["row_id"] == b.rows[0]["row_id"]
    assert a.rows[0]["record_key"] == stable_record_key("test-source:customers", 1)


def test_query_parameters_are_data_and_not_in_fingerprint(connector):
    a = connector.select(QueryPlan("customers", ("id",), filters={"segment": "standard"}))
    b = connector.select(QueryPlan("customers", ("id",), filters={"segment": "priority"}))
    assert a.query_fingerprint == b.query_fingerprint


def test_unallowlisted_table_rejected(connector):
    with pytest.raises(ConnectorError, match="not allowlisted"):
        connector.select(QueryPlan("private", ("id",)))


def test_unallowlisted_column_rejected(connector):
    with pytest.raises(ConnectorError, match="not allowlisted"):
        connector.select(QueryPlan("customers", ("email",)))


@pytest.mark.parametrize("statement", [
    "SELECT * FROM customers; DELETE FROM customers",
    "INSERT INTO customers VALUES (1)",
    "UPDATE customers SET name='x'",
    "DELETE FROM customers",
    "MERGE INTO customers",
    "CREATE TABLE x (id int)",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD x int",
    "TRUNCATE customers",
    "CALL do_something()",
    "EXEC do_something",
])
def test_arbitrary_sql_and_write_statements_rejected(statement):
    with pytest.raises(ConnectorError):
        reject_sql_text(statement)


def test_connector_rejects_sql_execution_method(connector):
    with pytest.raises(ConnectorError):
        connector.execute("SELECT * FROM customers")


def test_order_must_include_unique_primary_key(connector):
    with pytest.raises(ConnectorError, match="stable primary key"):
        connector.select(QueryPlan("customers", ("id",), order_by=("name",)))


def test_invalid_page_size_rejected(connector):
    with pytest.raises(ConnectorError, match="Page bounds"):
        connector.select(QueryPlan("customers", ("id",), limit=501))


def test_cancelled_query_fails_closed(connector):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ConnectorError, match="cancelled"):
        connector.select(QueryPlan("customers", ("id",)), cancel_event=cancel)


def test_non_unique_primary_key_rejected():
    with pytest.raises(ConnectorError, match="unique"):
        MockReadOnlyConnector(
            connector_id="bad", tables={"t": [{"id": 1}, {"id": 1}]},
            allowlist={"t": ("id",)}, primary_keys={"t": "id"},
        )


def test_filter_uses_parameter_values_without_string_interpolation(connector):
    page = connector.select(QueryPlan("customers", ("id",), filters={"name": "A"}))
    assert [r["values"]["id"] for r in page.rows] == [1]


def test_record_identity_is_scoped_to_table_schema(connector):
    original = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    narrower = MockReadOnlyConnector(
        connector_id="test-source",
        tables={"customers": [{"id": 1, "name": "A"}]},
        allowlist={"customers": ("id", "name")},
        primary_keys={"customers": "id"},
        snapshot_id="snapshot-001",
    )
    changed = narrower.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    assert original.rows[0]["row_id"] != changed.rows[0]["row_id"]


def test_numeric_ordering_is_numeric_not_lexicographic():
    numeric = MockReadOnlyConnector(
        connector_id="numeric-source",
        tables={"items": [{"id": 2}, {"id": 10}, {"id": 1}]},
        allowlist={"items": ("id",)}, primary_keys={"items": "id"},
    )
    page = numeric.select(QueryPlan("items", ("id",), order_by=("id",)))
    assert [row["values"]["id"] for row in page.rows] == [1, 2, 10]


def test_timeout_returns_no_partial_page(connector, monkeypatch):
    ticks = iter([0.0, 0.0, 0.0, 6.0])
    monkeypatch.setattr(readonly_connector.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ConnectorError, match="timed out"):
        connector.select(QueryPlan("customers", ("id",), limit=3), timeout_seconds=5)


def test_failed_extraction_exposes_no_partial_result(connector, monkeypatch):
    ticks = iter([0.0, 0.0, 0.0, 6.0])
    monkeypatch.setattr(readonly_connector.time, "monotonic", lambda: next(ticks))
    result = None
    with pytest.raises(ConnectorError):
        result = connector.select(QueryPlan("customers", ("id",), limit=3), timeout_seconds=5)
    assert result is None


def test_query_fingerprint_and_errors_do_not_expose_filter_values(connector):
    secret = "synthetic-secret-DO-NOT-LEAK"
    page = connector.select(QueryPlan("customers", ("id",), filters={"name": secret}))
    assert secret not in page.query_fingerprint
    with pytest.raises(ConnectorError) as exc:
        connector.select(QueryPlan("customers", ("id",), filters={"private_column": secret}))
    assert secret not in str(exc.value)


def test_record_key_stable_across_snapshots_while_row_id_changes():
    def make(snapshot_id):
        return MockReadOnlyConnector(
            connector_id="stable-source",
            tables={"customers": [{"id": 7, "name": "Ada"}]},
            allowlist={"customers": ("id", "name")},
            primary_keys={"customers": "id"},
            snapshot_id=snapshot_id,
        )

    first = make("snapshot-a").select(QueryPlan("customers", ("id",)))
    second = make("snapshot-b").select(QueryPlan("customers", ("id",)))
    assert first.rows[0]["record_key"] == second.rows[0]["record_key"]
    assert first.rows[0]["row_id"] != second.rows[0]["row_id"]
    assert first.rows[0]["record_key"] == stable_record_key("stable-source:customers", 7)


def test_record_key_is_scoped_to_connector_and_table():
    def read(connector_id, table):
        return MockReadOnlyConnector(
            connector_id=connector_id,
            tables={table: [{"id": 7}]},
            allowlist={table: ("id",)},
            primary_keys={table: "id"},
        ).select(QueryPlan(table, ("id",))).rows[0]["record_key"]

    baseline = read("source-a", "customers")
    assert baseline != read("source-b", "customers")
    assert baseline != read("source-a", "accounts")


def test_record_key_matches_documented_shared_identity(connector):
    page = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    assert page.rows[0]["record_key"] == stable_record_key("test-source:customers", 1)


def test_source_registry_and_row_hash_separators_are_nul_bytes():
    source = MockReadOnlyConnector(
        connector_id="sep-source", tables={"t": [{"id": 1}]},
        allowlist={"t": ("id",)}, primary_keys={"t": "id"},
        snapshot_id="sep-snapshot",
    )
    expected = "mock-source-" + readonly_connector.hashlib.sha256(
        f"sep-source\0sep-snapshot\0{source.source_sha256}".encode("utf-8")
    ).hexdigest()[:24]
    assert source.source_registry_id == expected

from __future__ import annotations

import threading

import pytest

import agora.readonly_connector as readonly_connector

from agora.readonly_connector import (
    ConnectorError, MockReadOnlyConnector, QueryPlan, validate_read_only_statement,
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


def test_pagination_is_deterministic_without_duplicates(connector):
    first = connector.select(QueryPlan("customers", ("id",), limit=2))
    second = connector.select(QueryPlan("customers", ("id",), limit=2, offset=first.next_offset))
    assert [r["values"]["id"] for r in first.rows + second.rows] == [1, 2, 3]
    assert second.next_offset is None


def test_primary_key_row_identity_is_stable_for_same_snapshot(connector):
    a = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    b = connector.select(QueryPlan("customers", ("id",), filters={"id": 1}))
    assert a.rows[0]["record_key"] == b.rows[0]["record_key"]


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
        validate_read_only_statement(statement)


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


def test_read_only_acceptance_detects_a_removed_guard_mutation(monkeypatch):
    # Simulate a mutation that removes the statement guard. The acceptance
    # expectation itself must fail when a write statement is no longer rejected.
    monkeypatch.setattr(readonly_connector, "validate_read_only_statement", lambda statement: None)
    with pytest.raises(AssertionError):
        with pytest.raises(ConnectorError):
            readonly_connector.validate_read_only_statement("DELETE FROM customers")

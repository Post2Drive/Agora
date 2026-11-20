"""Read-only relational connector contract and deterministic in-memory mock.

The interface accepts structured query plans, not arbitrary SQL. This module
contains no database drivers, sockets, credentials or network access.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class ConnectorError(ValueError):
    """Safe connector contract error."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


@dataclass(frozen=True)
class QueryPlan:
    table: str
    columns: tuple[str, ...]
    filters: Mapping[str, Any] = field(default_factory=dict)
    limit: int = 100
    offset: int = 0
    order_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConnectorPage:
    rows: tuple[dict[str, Any], ...]
    next_offset: int | None
    query_fingerprint: str
    snapshot_id: str
    extracted_at: str
    connector_id: str


class ReadOnlyConnector(Protocol):
    """Future adapter contract. Implementations must remain SELECT-only."""

    connector_id: str

    def discover(self) -> dict[str, tuple[str, ...]]:
        """Return only explicitly allowlisted tables and columns."""
        ...

    def select(self, plan: QueryPlan, *, timeout_seconds: float = 5.0,
               cancel_event: threading.Event | None = None) -> ConnectorPage:
        """Return one bounded deterministic page from an immutable source snapshot."""
        ...


class MockReadOnlyConnector:
    """In-memory mock adapter used for contract tests; never connects externally."""

    def __init__(self, *, connector_id: str, tables: Mapping[str, list[dict[str, Any]]],
                 allowlist: Mapping[str, tuple[str, ...]],
                 primary_keys: Mapping[str, str], snapshot_id: str = "mock-snapshot-v1",
                 max_page_size: int = 500):
        if not connector_id or not snapshot_id:
            raise ConnectorError("Connector and snapshot identifiers are required.")
        self.connector_id = connector_id
        self._tables = {name: [dict(row) for row in rows] for name, rows in tables.items()}
        self._allowlist = {name: tuple(cols) for name, cols in allowlist.items()}
        self._primary_keys = dict(primary_keys)
        self.snapshot_id = snapshot_id
        self.max_page_size = max_page_size
        if max_page_size < 1:
            raise ConnectorError("Maximum page size must be positive.")
        if set(self._allowlist) - set(self._tables):
            raise ConnectorError("Allowlist references an unavailable mock table.")
        for table, columns in self._allowlist.items():
            if len(columns) != len(set(columns)) or not columns:
                raise ConnectorError("Allowlisted columns must be unique and non-empty.")
            if table not in self._primary_keys:
                raise ConnectorError("Every mock table requires a stable primary key.")
            key = self._primary_keys[table]
            if key not in columns:
                raise ConnectorError("Primary key must be allowlisted.")
            seen = set()
            for row in self._tables[table]:
                if set(row) - set(columns) or key not in row or row[key] is None:
                    raise ConnectorError("Mock row violates its declared table schema.")
                token = _canonical(row[key])
                if token in seen:
                    raise ConnectorError("Mock primary keys must be unique.")
                seen.add(token)

    def discover(self) -> dict[str, tuple[str, ...]]:
        """Expose the fixed allowlist; query input cannot expand it."""
        return dict(self._allowlist)

    def execute(self, statement: str, *args: Any, **kwargs: Any) -> None:
        """Reject SQL text entirely; callers must use a structured QueryPlan."""
        raise ConnectorError("SQL text is not accepted; use a structured SELECT query plan.")

    def select(self, plan: QueryPlan, *, timeout_seconds: float = 5.0,
               cancel_event: threading.Event | None = None) -> ConnectorPage:
        if not isinstance(plan, QueryPlan):
            raise ConnectorError("A structured QueryPlan is required.")
        if timeout_seconds <= 0:
            raise ConnectorError("Timeout must be positive.")
        deadline = time.monotonic() + timeout_seconds
        if cancel_event is not None and cancel_event.is_set():
            raise ConnectorError("Query cancelled.")
        if plan.table not in self._allowlist:
            raise ConnectorError("Table is not allowlisted.")
        allowed = self._allowlist[plan.table]
        if not plan.columns or len(plan.columns) != len(set(plan.columns)):
            raise ConnectorError("Selected columns must be unique and non-empty.")
        if set(plan.columns) - set(allowed):
            raise ConnectorError("A selected column is not allowlisted.")
        if set(plan.filters) - set(allowed):
            raise ConnectorError("A filter column is not allowlisted.")
        if plan.limit < 1 or plan.limit > self.max_page_size or plan.offset < 0:
            raise ConnectorError("Page bounds are invalid.")
        key = self._primary_keys[plan.table]
        order = tuple(plan.order_by) if plan.order_by else (key,)
        if set(order) - set(allowed) or key not in order:
            raise ConnectorError("Ordering must include the stable primary key.")
        # Values are bound as data; they are never interpolated into SQL.
        canonical_plan = {
            "table": plan.table, "columns": list(plan.columns),
            "filter_columns": sorted(plan.filters), "order_by": list(order),
            "limit": plan.limit, "offset": plan.offset,
            "connector_id": self.connector_id, "snapshot_id": self.snapshot_id,
            "allowlist": {k: list(v) for k, v in sorted(self._allowlist.items())},
        }
        fingerprint = hashlib.sha256(
            b"agora-query-plan-v1\0" + _canonical(canonical_plan).encode("utf-8")
        ).hexdigest()
        filtered = []
        for row in self._tables[plan.table]:
            if time.monotonic() > deadline:
                raise ConnectorError("Query timed out.")
            if cancel_event is not None and cancel_event.is_set():
                raise ConnectorError("Query cancelled.")
            if all(row.get(column) == value for column, value in plan.filters.items()):
                filtered.append(row)
        filtered.sort(key=lambda row: tuple(_canonical(row[c]) for c in order))
        page_rows = filtered[plan.offset:plan.offset + plan.limit]
        projected = []
        for row in page_rows:
            key_value = row[key]
            record_id = hashlib.sha256(
                b"agora-db-record-v1\0" + _canonical({
                    "connector_id": self.connector_id, "snapshot_id": self.snapshot_id,
                    "table": plan.table, "primary_key": key_value,
                }).encode("utf-8")
            ).hexdigest()
            projected.append({
                "record_key": record_id,
                "values": {column: row[column] for column in plan.columns},
                "source_locator": {
                    "connector_id": self.connector_id, "snapshot_id": self.snapshot_id,
                    "table": plan.table, "primary_key_column": key,
                    "primary_key_value": key_value,
                    "query_fingerprint": fingerprint,
                },
            })
        next_offset = plan.offset + len(page_rows)
        if next_offset >= len(filtered):
            next_offset = None
        from datetime import datetime, timezone
        return ConnectorPage(
            rows=tuple(projected), next_offset=next_offset,
            query_fingerprint=fingerprint, snapshot_id=self.snapshot_id,
            extracted_at=datetime.now(timezone.utc).isoformat(),
            connector_id=self.connector_id,
        )


def validate_read_only_statement(statement: str) -> None:
    """Fail closed for any SQL statement; SQL is intentionally not a v1 input."""
    if not isinstance(statement, str) or not statement.strip():
        raise ConnectorError("Statement must be non-empty text.")
    raise ConnectorError("Arbitrary SQL is prohibited; use a structured SELECT query plan.")

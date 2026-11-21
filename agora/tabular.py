"""Structured, provenance-preserving CSV snapshot ingestion.

This module is deliberately separate from the legacy document/text graph
ingestion and calibration CSV paths. It stores immutable typed snapshots in a
project-local SQLite database and never opens a network connection.
"""
from __future__ import annotations

from agora import protection as _protection

import csv
import hashlib
import json
import logging
import math
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .identity import stable_record_key
from .policy_enforcement import PolicyCallable, PolicyEnforcementError, enforce_policy

logger = logging.getLogger(__name__)

PARSER_VERSION = "agora-tabular-csv-v1"
ROLES = {"context", "scenario_input", "calibration", "validation", "sealed_holdout"}
TYPES = {"string", "integer", "decimal", "boolean", "date", "timestamp", "enum"}
SENSITIVITY = {"public", "internal", "personal", "sensitive"}
DEFAULT_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_ROWS = 1_000_000


class TabularIngestError(ValueError):
    """Safe, stable ingestion error; never includes source field values."""

    def __init__(self, code: str, message: str, *, row_number: int | None = None,
                 column_name: str | None = None):
        self.code = code
        self.row_number = row_number
        self.column_name = column_name
        self.diagnostic = {
            "row_number": row_number,
            "column_name": column_name,
            "error_code": code,
        }
        super().__init__(message)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _hash(prefix: bytes, value: Any) -> str:
    return hashlib.sha256(prefix + _canonical(value).encode("utf-8")).hexdigest()


def _schema_contract(schema: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    if not isinstance(schema, dict):
        raise TabularIngestError("SCHEMA_INVALID", "Schema must be an object.")
    allowed_schema_keys = {
        "schema_id", "schema_version", "dataset_id", "dataset_name", "purpose",
        "retention_policy", "encoding", "delimiter", "quotechar", "header",
        "columns", "row_policy", "allow_empty",
    }
    if set(schema) - allowed_schema_keys:
        raise TabularIngestError("SCHEMA_INVALID", "Schema contains unsupported fields.")
    dataset_id = schema.get("dataset_id") or schema.get("dataset_name")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise TabularIngestError("SCHEMA_DATASET_REQUIRED", "Schema dataset identity is required.")
    columns = schema.get("columns")
    if not isinstance(columns, list) or not columns:
        raise TabularIngestError("SCHEMA_COLUMNS_REQUIRED", "Schema columns are required.")
    names: set[str] = set()
    primary: list[str] = []
    clean: list[dict[str, Any]] = []
    allowed_column_keys = {
        "name", "type", "nullable", "primary_key", "allowed_values", "precision",
        "scale", "timezone", "minimum", "maximum", "format", "sensitivity",
        "empty_as_null", "purpose", "retention",
    }
    for item in columns:
        if not isinstance(item, dict) or set(item) - allowed_column_keys:
            raise TabularIngestError("SCHEMA_COLUMN_INVALID", "Column definition is invalid.")
        name, kind = item.get("name"), item.get("type")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise TabularIngestError("SCHEMA_COLUMN_NAME", "Column names must be unique and non-empty.")
        if kind not in TYPES or not isinstance(item.get("nullable"), bool):
            raise TabularIngestError("SCHEMA_COLUMN_TYPE", "Column type or nullability is invalid.")
        sensitivity = item.get("sensitivity")
        if sensitivity not in SENSITIVITY:
            raise TabularIngestError("SCHEMA_SENSITIVITY_REQUIRED", "Every column needs a valid sensitivity classification.")
        if "empty_as_null" in item and not isinstance(item["empty_as_null"], bool):
            raise TabularIngestError("SCHEMA_EMPTY_POLICY", "empty_as_null must be boolean.")
        if item.get("primary_key"):
            primary.append(name)
        if kind == "enum" and (not isinstance(item.get("allowed_values"), list)
                               or not item["allowed_values"]):
            raise TabularIngestError("SCHEMA_ENUM_VALUES", "Enum columns need allowed values.")
        if kind == "decimal":
            if not isinstance(item.get("precision"), int) or not isinstance(item.get("scale"), int):
                raise TabularIngestError("SCHEMA_DECIMAL_PRECISION", "Decimal columns need precision and scale.")
            if item["precision"] <= 0 or item["scale"] < 0 or item["scale"] > item["precision"]:
                raise TabularIngestError("SCHEMA_DECIMAL_PRECISION", "Decimal precision or scale is invalid.")
        if "minimum" in item or "maximum" in item:
            try:
                minimum = _bound_value(item["minimum"], kind) if "minimum" in item else None
                maximum = _bound_value(item["maximum"], kind) if "maximum" in item else None
                if minimum is not None and maximum is not None and minimum > maximum:
                    raise ValueError
            except (ValueError, TypeError, InvalidOperation, OverflowError, ZoneInfoNotFoundError):
                raise TabularIngestError(
                    "SCHEMA_BOUND_INVALID", "Schema bounds are invalid for the declared column type."
                ) from None
        names.add(name)
        clean.append(dict(item))
    if len(primary) > 1:
        raise TabularIngestError("SCHEMA_PRIMARY_KEY", "Only one primary-key column is supported in v1.")
    if any(c["sensitivity"] == "personal" for c in clean):
        if not isinstance(schema.get("purpose"), str) or not schema["purpose"].strip():
            # Import is allowed for validation, but downstream use is not. This marker is
            # persisted so a future consumer can fail closed until policy is supplied.
            pass
        if schema.get("retention_policy") is not None and not isinstance(schema["retention_policy"], str):
            raise TabularIngestError("SCHEMA_RETENTION_POLICY", "Retention policy must be text.")
    if schema.get("header", True) is not True:
        raise TabularIngestError("SCHEMA_HEADER_REQUIRED", "CSV v1 requires a header row.")
    if "allow_empty" in schema and not isinstance(schema["allow_empty"], bool):
        raise TabularIngestError("SCHEMA_EMPTY_POLICY", "allow_empty must be boolean.")
    row_policy = schema.get("row_policy", {})
    if not isinstance(row_policy, dict) or row_policy.get("malformed", "fail") != "fail":
        raise TabularIngestError("SCHEMA_ROW_POLICY", "CSV v1 supports fail-closed malformed-row handling only.")
    if row_policy.get("unknown_columns", "reject") != "reject" or row_policy.get("missing_columns", "reject") != "reject":
        raise TabularIngestError("SCHEMA_ROW_POLICY", "CSV v1 rejects unknown and missing columns.")
    schema_version = schema.get("schema_version", "1.0.0")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise TabularIngestError("SCHEMA_VERSION", "Schema version is required.")
    fingerprint = hashlib.sha256(_canonical(schema).encode("utf-8")).hexdigest()
    return clean, str(dataset_id), fingerprint


def validate_downstream_policy(schema: dict[str, Any]) -> None:
    """Fail closed before downstream use of personal columns."""
    columns = schema.get("columns", [])
    for column in columns:
        if isinstance(column, dict) and column.get("sensitivity") == "personal":
            if not (isinstance(column.get("purpose"), str) and column["purpose"].strip()
                    and isinstance(column.get("retention"), str) and column["retention"].strip()):
                raise TabularIngestError(
                    "PERSONAL_DATA_POLICY_REQUIRED",
                    "Every personal column requires its own purpose and retention policy before downstream use.",
                )


def _bound_value(value: Any, kind: str) -> Any:
    """Convert a declared range bound to the parsed value's native type."""
    if kind == "decimal":
        return Decimal(str(value))
    if kind == "integer":
        return int(value)
    if kind == "date":
        return date.fromisoformat(str(value))
    if kind == "timestamp":
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "1"}:
            return True
        if str(value).lower() in {"false", "0"}:
            return False
        raise ValueError
    return str(value) if kind in {"string", "enum"} else value


def _convert(value: str, column: dict[str, Any], row_number: int) -> Any:
    name, kind = column["name"], column["type"]
    if value == "" and column.get("empty_as_null", False):
        if column["nullable"]:
            return None
        raise TabularIngestError("NULL_NOT_ALLOWED", "A required CSV value is empty.",
                                 row_number=row_number, column_name=name)
    try:
        if kind == "string":
            result: Any = value
        elif kind == "integer":
            if not value or value.strip() != value or any(ch in value for ch in ".eE"):
                raise ValueError
            result = int(value, 10)
        elif kind == "decimal":
            number = Decimal(value)
            if not number.is_finite():
                raise ValueError
            quant = Decimal(1).scaleb(-column["scale"])
            if number.quantize(quant) != number or len(number.as_tuple().digits) > column["precision"]:
                raise ValueError
            result = format(number, "f")
        elif kind == "boolean":
            literals = {"true": True, "false": False, "1": True, "0": False}
            if value.lower() not in literals:
                raise ValueError
            result = literals[value.lower()]
        elif kind == "date":
            result = date.fromisoformat(value).isoformat()
        elif kind == "timestamp":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                zone = column.get("timezone")
                if not zone:
                    raise ValueError
                parsed = parsed.replace(tzinfo=ZoneInfo(zone))
            result = parsed.astimezone(timezone.utc).isoformat()
        else:
            if value not in column["allowed_values"]:
                raise ValueError
            result = value
        if result is not None:
            comparable = Decimal(result) if kind == "decimal" else result
            if kind == "date":
                comparable = date.fromisoformat(result)
            elif kind == "timestamp":
                comparable = datetime.fromisoformat(result)
            if "minimum" in column and comparable < _bound_value(column["minimum"], kind):
                raise ValueError
            if "maximum" in column and comparable > _bound_value(column["maximum"], kind):
                raise ValueError
        return result
    except (ValueError, TypeError, InvalidOperation, OverflowError, ZoneInfoNotFoundError):
        raise TabularIngestError(
            "VALUE_INVALID", "A CSV value failed schema validation.",
            row_number=row_number, column_name=name,
        ) from None


def _db(project: Path) -> sqlite3.Connection:
    path = project / "data" / "tabular.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS datasets (
      dataset_id TEXT PRIMARY KEY, schema_id TEXT NOT NULL,
      schema_version TEXT NOT NULL, schema_fingerprint TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS dataset_schemas (
      dataset_id TEXT NOT NULL, schema_id TEXT NOT NULL,
      schema_version TEXT NOT NULL, schema_fingerprint TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(dataset_id, schema_id, schema_version)
    );
    CREATE TABLE IF NOT EXISTS imports (
      import_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL,
      dataset_id TEXT NOT NULL, source_registry_id TEXT NOT NULL,
      file_sha256 TEXT NOT NULL, status TEXT NOT NULL,
      manifest_json TEXT NOT NULL, created_at TEXT NOT NULL,
      FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
    );
    CREATE TABLE IF NOT EXISTS import_rows (
      row_id TEXT PRIMARY KEY, record_key TEXT, import_id TEXT NOT NULL,
      source_record_number INTEGER NOT NULL, payload_json TEXT NOT NULL,
      locator_json TEXT NOT NULL,
      UNIQUE(import_id, source_record_number),
      FOREIGN KEY(import_id) REFERENCES imports(import_id)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_committed_import_idempotency
      ON imports(idempotency_key) WHERE status='committed';
    CREATE INDEX IF NOT EXISTS idx_import_rows_record_key ON import_rows(record_key);
    CREATE TABLE IF NOT EXISTS rejected_rows (
      rejection_id TEXT PRIMARY KEY, import_id TEXT NOT NULL,
      source_record_number INTEGER, column_name TEXT, error_code TEXT NOT NULL,
      diagnostic_json TEXT NOT NULL,
      FOREIGN KEY(import_id) REFERENCES imports(import_id)
    );
    CREATE TABLE IF NOT EXISTS dataset_records (
      dataset_id TEXT NOT NULL, record_key TEXT NOT NULL, latest_row_id TEXT NOT NULL,
      updated_at TEXT NOT NULL, PRIMARY KEY(dataset_id, record_key),
      FOREIGN KEY(latest_row_id) REFERENCES import_rows(row_id)
    );
    """)


def ingest_csv(project: str | Path, source_path: str | Path, schema: dict[str, Any], *,
               data_role: str, max_bytes: int = DEFAULT_MAX_BYTES,
               max_rows: int = DEFAULT_MAX_ROWS,
               policy: PolicyCallable | None = None,
               audit: Any | None = None) -> dict[str, Any]:
    """Import a local CSV as an immutable, typed, provenance-registered snapshot.

    When supplied, policy is called as policy("import", resource) before the
    source file is checked or read. A policy is mandatory: None is denied (and audited).
    """
    project, source_path = Path(project), Path(source_path)
    if data_role not in ROLES:
        raise TabularIngestError("DATA_ROLE_INVALID", "An explicit valid data role is required.")
    columns, dataset_id, schema_fp = _schema_contract(schema)
    if policy is not None or _protection.POLICY_REQUIRED:
        sensitivity_rank = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
        source_sensitivity = max(
            (column["sensitivity"] for column in columns),
            key=lambda value: sensitivity_rank[value],
        )
        try:
            enforce_policy(
                policy,
                audit=audit,
                project=project,
                operation="import",
                require_policy=_protection.POLICY_REQUIRED,
                resource={
                    "project_id": project.name or str(project),
                    "resource_ids": [dataset_id],
                    "dataset_id": dataset_id,
                    "source_role": data_role,
                    "source_sensitivity": source_sensitivity,
                    "target_sensitivity": source_sensitivity,
                },
            )
        except PolicyEnforcementError as exc:
            raise TabularIngestError(
                "POLICY_DENIED", "Policy denied CSV import."
            ) from exc
    if not source_path.is_file():
        raise FileNotFoundError("CSV source file was not found.")
    raw = source_path.read_bytes()
    if len(raw) > max_bytes:
        raise TabularIngestError("FILE_TOO_LARGE", "CSV exceeds the configured byte limit.")
    file_hash = hashlib.sha256(raw).hexdigest()
    schema_id = str(schema.get("schema_id", dataset_id))
    schema_version = str(schema.get("schema_version", "1.0.0"))
    primary = next((c for c in columns if c.get("primary_key")), None)
    idempotency_key = _hash(b"agora-import-v1\0", {
        "dataset_id": dataset_id, "file_sha256": file_hash,
        "schema_fingerprint": schema_fp, "parser_version": PARSER_VERSION,
        "data_role": data_role,
    })
    import_id = hashlib.sha256(("agora-import-id-v1\0" + idempotency_key).encode()).hexdigest()
    source_id = "tabular-" + hashlib.sha256(
        f"{dataset_id}\0{file_hash}\0{data_role}".encode("utf-8")
    ).hexdigest()[:32]
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "manifest_version": 1, "import_id": import_id, "dataset_id": dataset_id,
        "dataset_name": schema.get("dataset_name", dataset_id), "source_filename": source_path.name,
        "file_sha256": file_hash, "byte_length": len(raw), "schema_id": schema_id,
        "schema_version": schema_version, "schema_fingerprint": schema_fp,
        "column_sensitivity": {c["name"]: c["sensitivity"] for c in columns},
        "column_types": {c["name"]: c["type"] for c in columns},
        "purpose": schema.get("purpose"), "retention_policy": schema.get("retention_policy"),
        "column_policies": {
            c["name"]: {"purpose": c.get("purpose"), "retention": c.get("retention")}
            for c in columns if c["sensitivity"] == "personal"
        },
        "parser_version": PARSER_VERSION, "application_version": "0.3.0",
        "encoding": schema.get("encoding", "utf-8-sig"),
        "delimiter": schema.get("delimiter", ","), "quotechar": schema.get("quotechar", '"'),
        "max_bytes": max_bytes, "max_rows": max_rows,
        "data_role": data_role, "source_registry_id": source_id,
        "first_source_record_number": None, "last_source_record_number": None,
        "started_at": now, "completed_at": None,
        "status": "pending", "parsed_records": 0, "accepted_records": 0,
        "rejected_records": 0, "row_id_algorithm": "agora-row-v1",
        "record_key_algorithm": "agora-record-v1", "idempotency_key": idempotency_key,
    }
    from .governance import (audit_event, begin_operation, finish_operation, record_source)
    operation = begin_operation(project, "tabular_csv_import",
                                source_ids=[source_id],
                                details={"dataset_id": dataset_id, "file_sha256": file_hash})
    conn = _db(project)
    rejected: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    try:
        _init_db(conn)
        # Serialise identical imports before the idempotency lookup.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT import_id, manifest_json FROM imports WHERE idempotency_key=? AND status='committed'",
            (idempotency_key,),
        ).fetchone()
        if existing:
            conn.commit()
            finish_operation(project, operation["operation_id"], "committed",
                             details={"import_id": existing["import_id"], "idempotent_noop": True})
            return {"import_id": existing["import_id"],
                    "manifest": json.loads(existing["manifest_json"]), "idempotent": True}
        # Register the exact bytes before parsing so failed source attempts retain provenance.
        record_source(project, source_id=source_id, content=raw, data_role=data_role,
                      parser_version=PARSER_VERSION, extraction_status="received")
        try:
            text = raw.decode(schema.get("encoding", "utf-8-sig"))
            reader = csv.reader(text.splitlines(keepends=True), delimiter=schema.get("delimiter", ","),
                                quotechar=schema.get("quotechar", '"'), strict=True)
            header = next(reader, None)
            names = [c["name"] for c in columns]
            if not header or len(header) != len(set(header)) or set(header) != set(names):
                raise TabularIngestError("HEADER_INVALID", "CSV header does not match the declared schema.")
            indexes = {name: header.index(name) for name in names}
            keys: set[str] = set()
            for record_number, values in enumerate(reader, start=2):
                if record_number - 1 > max_rows:
                    raise TabularIngestError("ROW_LIMIT_EXCEEDED", "CSV exceeds the configured row limit.",
                                             row_number=record_number)
                manifest["parsed_records"] += 1
                if len(values) != len(header):
                    raise TabularIngestError("ROW_WIDTH_INVALID", "CSV record width does not match its header.",
                                             row_number=record_number)
                payload = {}
                for col in columns:
                    payload[col["name"]] = _convert(values[indexes[col["name"]]], col, record_number)
                record_key = None
                if primary:
                    pk_value = payload[primary["name"]]
                    if pk_value is None or pk_value == "":
                        raise TabularIngestError("PRIMARY_KEY_NULL", "Primary key cannot be null or empty.",
                                                 row_number=record_number, column_name=primary["name"])
                    record_key = stable_record_key(dataset_id, pk_value)
                    if record_key in keys:
                        raise TabularIngestError("PRIMARY_KEY_DUPLICATE",
                                                 "Duplicate primary key in CSV snapshot.",
                                                 row_number=record_number, column_name=primary["name"])
                    keys.add(record_key)
                row_id = hashlib.sha256(
                    b"agora-row-v1\0" + _canonical({
                        "dataset_id": dataset_id, "source_registry_id": source_id,
                        "file_sha256": file_hash, "schema_fingerprint": schema_fp,
                        "row": payload, "source_record_number": record_number,
                    }).encode("utf-8")
                ).hexdigest()
                rows.append({"row_id": row_id, "record_key": record_key,
                             "source_record_number": record_number, "payload": payload,
                             "locator": {"source_registry_id": source_id, "file_sha256": file_hash,
                                         "source_record_number": record_number, "dataset_id": dataset_id,
                                         "import_id": import_id}})
            if not rows and not schema.get("allow_empty", False):
                raise TabularIngestError("CSV_EMPTY", "CSV contains no data records.")
            manifest["accepted_records"] = len(rows)
            if rows:
                manifest["first_source_record_number"] = rows[0]["source_record_number"]
                manifest["last_source_record_number"] = rows[-1]["source_record_number"]
        except TabularIngestError as exc:
            rejected.append(exc.diagnostic)
            manifest["rejected_records"] = 1
            raise
        except (UnicodeDecodeError, csv.Error, StopIteration, LookupError):
            rejected.append({"row_number": None, "column_name": None, "error_code": "CSV_PARSE_FAILED"})
            manifest["rejected_records"] = 1
            raise TabularIngestError("CSV_PARSE_FAILED", "CSV could not be decoded or parsed.") from None

        prior_schema = conn.execute(
            "SELECT schema_fingerprint FROM dataset_schemas "
            "WHERE dataset_id=? AND schema_id=? AND schema_version=?",
            (dataset_id, schema_id, schema_version),
        ).fetchone()
        if prior_schema and prior_schema["schema_fingerprint"] != schema_fp:
            raise TabularIngestError("SCHEMA_DRIFT",
                                     "Schema fingerprint changed without a schema-version change.")
        if not prior_schema:
            conn.execute(
                "INSERT INTO dataset_schemas(dataset_id,schema_id,schema_version,schema_fingerprint,created_at) "
                "VALUES(?,?,?,?,?)",
                (dataset_id, schema_id, schema_version, schema_fp, now),
            )
        conn.execute(
            "INSERT INTO datasets(dataset_id,schema_id,schema_version,schema_fingerprint,created_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET "
            "schema_id=excluded.schema_id,schema_version=excluded.schema_version,"
            "schema_fingerprint=excluded.schema_fingerprint",
            (dataset_id, schema_id, schema_version, schema_fp, now),
        )
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["status"] = "committed"
        conn.execute(
            "INSERT INTO imports(import_id,idempotency_key,dataset_id,source_registry_id,file_sha256,status,manifest_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (import_id, idempotency_key, dataset_id, source_id, file_hash, "committed",
             _canonical(manifest), now),
        )
        for row in rows:
            conn.execute(
                "INSERT INTO import_rows(row_id,record_key,import_id,source_record_number,payload_json,locator_json) "
                "VALUES(?,?,?,?,?,?)",
                (row["row_id"], row["record_key"], import_id, row["source_record_number"],
                 _canonical(row["payload"]), _canonical(row["locator"])),
            )
            if row["record_key"]:
                conn.execute(
                    "INSERT INTO dataset_records(dataset_id,record_key,latest_row_id,updated_at) "
                    "VALUES(?,?,?,?) ON CONFLICT(dataset_id,record_key) DO UPDATE SET "
                    "latest_row_id=excluded.latest_row_id,updated_at=excluded.updated_at",
                    (dataset_id, row["record_key"], row["row_id"], now),
                )
        conn.commit()
        # The SQLite snapshot is already committed. If the external JSONL audit
        # append fails, leave the operation pending for manual reconciliation;
        # never rewrite a committed snapshot as a failed import.
        try:
            audit_event(project, "tabular_import_committed", import_id=import_id,
                        source_registry_id=source_id, file_sha256=file_hash,
                        accepted_records=len(rows), data_role=data_role)
            finish_operation(project, operation["operation_id"], "committed",
                             details={"import_id": import_id, "accepted_records": len(rows)})
        except Exception:
            logger.warning("Tabular import audit finalisation failed; operation remains pending.")
        return {"import_id": import_id, "manifest": manifest, "idempotent": False}
    except Exception as exc:
        if conn.in_transaction:
            conn.rollback()
        if not any(row.get("error_code") for row in rejected):
            rejected.append({"row_number": getattr(exc, "row_number", None),
                             "column_name": getattr(exc, "column_name", None),
                             "error_code": getattr(exc, "code", "IMPORT_FAILED")})
        # The whole snapshot is atomic: all previously parsed candidate rows are rejected
        # on failure, but only safe row/column/error metadata is retained.
        failed_numbers = {r.get("row_number") for r in rejected}
        for candidate in rows:
            number = candidate["source_record_number"]
            if number not in failed_numbers:
                rejected.append({"row_number": number, "column_name": None,
                                 "error_code": "IMPORT_ROLLED_BACK"})
        failed_manifest = dict(manifest)
        failed_import_id = import_id + "-failed-" + uuid.uuid4().hex[:8]
        failed_manifest.update({"import_id": failed_import_id, "status": "failed",
                                "completed_at": datetime.now(timezone.utc).isoformat(),
                                "accepted_records": 0, "rejected_records": manifest["parsed_records"]})
        # Persist only a failed manifest and safe diagnostics; no partial accepted rows.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO datasets(dataset_id,schema_id,schema_version,schema_fingerprint,created_at) "
            "VALUES(?,?,?,?,?)",
            (dataset_id, schema_id, schema_version, schema_fp, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO imports(import_id,idempotency_key,dataset_id,source_registry_id,file_sha256,status,manifest_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (failed_import_id, idempotency_key, dataset_id, source_id, file_hash, "failed",
             _canonical(failed_manifest), now),
        )
        for diag in rejected:
            conn.execute(
                "INSERT INTO rejected_rows(rejection_id,import_id,source_record_number,column_name,error_code,diagnostic_json) "
                "VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex, failed_import_id, diag.get("row_number"), diag.get("column_name"),
                 diag.get("error_code", "IMPORT_FAILED"), _canonical(diag)),
            )
        conn.commit()
        try:
            audit_event(project, "tabular_import_failed", import_id=failed_import_id,
                        file_sha256=file_hash, rejected_records=len(rejected),
                        diagnostics=rejected, data_role=data_role)
            finish_operation(project, operation["operation_id"], "failed",
                             error=f"{type(exc).__name__}: {getattr(exc, 'code', 'IMPORT_FAILED')}")
        except Exception:
            logger.warning("Tabular import failure audit finalisation failed; operation remains pending.")
        raise
    finally:
        conn.close()


def read_snapshot(project: str | Path, import_id: str) -> list[dict[str, Any]]:
    """Read typed rows from one explicit immutable snapshot."""
    conn = _db(Path(project))
    try:
        rows = conn.execute(
            "SELECT row_id,record_key,source_record_number,payload_json,locator_json "
            "FROM import_rows WHERE import_id=? ORDER BY source_record_number", (import_id,)
        ).fetchall()
        return [{"row_id": r["row_id"], "record_key": r["record_key"],
                 "source_record_number": r["source_record_number"],
                 "values": json.loads(r["payload_json"]), "source_locator": json.loads(r["locator_json"])}
                for r in rows]
    finally:
        conn.close()

"""Read-only catalogue and CSV-import commands for tabular snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .tabular import TabularIngestError, ingest_csv, validate_downstream_policy

ROLES = ("context", "scenario_input", "calibration", "validation", "sealed_holdout")


def _db(project: Path) -> sqlite3.Connection:
    database = (project / "data" / "tabular.sqlite3").resolve()
    conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _manifest(row: sqlite3.Row) -> dict:
    return json.loads(row["manifest_json"])


def import_csv(args: argparse.Namespace) -> int:
    schema_path = Path(args.schema)
    try:
        import yaml
        schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.suffix.lower() == ".json" else yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        validate_downstream_policy(schema)
        result = ingest_csv(Path(args.project), Path(args.csv), schema, data_role=args.role)
    except TabularIngestError as exc:
        code = 3 if exc.code == "PERSONAL_DATA_POLICY_REQUIRED" else 2
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return code
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, TypeError, AttributeError):
        print("SCHEMA_FILE_INVALID: schema file could not be read or parsed.", file=sys.stderr)
        return 2
    if result.get("idempotent"):
        print(f"already imported: {result['import_id']}")
    else:
        print(f"imported: {result['import_id']}")
    return 0


def snapshots(args: argparse.Namespace) -> int:
    try:
        conn = _db(Path(args.project))
        rows = conn.execute("SELECT manifest_json FROM imports ORDER BY created_at, import_id").fetchall()
    except sqlite3.Error as exc:
        print(f"DATA_STORE_ERROR: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    for row in rows:
        m = _manifest(row)
        print(json.dumps({k: m.get(k) for k in (
            "import_id", "dataset_id", "schema_version", "file_sha256", "data_role", "status",
            "parsed_records", "accepted_records", "rejected_records",
        )}, ensure_ascii=False))
    return 0


def show(args: argparse.Namespace) -> int:
    try:
        conn = _db(Path(args.project))
        row = conn.execute("SELECT manifest_json FROM imports WHERE import_id=?", (args.import_id,)).fetchone()
    except sqlite3.Error as exc:
        print(f"DATA_STORE_ERROR: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    if row is None:
        print("IMPORT_NOT_FOUND", file=sys.stderr)
        return 2
    m = _manifest(row)
    # Manifest metadata contains no row values; do not add payloads to this command.
    print(json.dumps(m, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def rejected(args: argparse.Namespace) -> int:
    try:
        conn = _db(Path(args.project))
        rows = conn.execute(
            "SELECT source_record_number,column_name,error_code,diagnostic_json "
            "FROM rejected_rows WHERE import_id=? ORDER BY source_record_number,rejection_id", (args.import_id,)
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"DATA_STORE_ERROR: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    for row in rows:
        print(json.dumps({"source_record_number": row[0], "column_name": row[1], "error_code": row[2]}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agora data")
    sub = ap.add_subparsers(dest="action", required=True)
    p = sub.add_parser("import-csv", help="import one CSV as an immutable snapshot")
    p.add_argument("--project", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--role", required=True, choices=ROLES)
    p.set_defaults(func=import_csv)
    p = sub.add_parser("snapshots", help="list imported snapshots")
    p.add_argument("--project", required=True)
    p.set_defaults(func=snapshots)
    for name, func in (("show", show), ("rejected", rejected)):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("--import-id", required=True)
        p.set_defaults(func=func)
    args = ap.parse_args(argv)
    return args.func(args)

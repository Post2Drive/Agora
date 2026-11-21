from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

import agora.governance as governance
from agora.ontology import stable_record_key as ontology_stable_record_key
from agora.tabular import (
    TabularIngestError, ingest_csv, read_snapshot, validate_downstream_policy,
)
from agora.audit_chain import AuditChainStore


def schema():
    return {
        "schema_id": "people-v1", "schema_version": "1.0.0",
        "dataset_id": "people", "purpose": "Test-only synthetic data",
        "retention_policy": "Delete after test",
        "columns": [
            {"name": "person_id", "type": "string", "nullable": False,
             "primary_key": True, "sensitivity": "personal",
             "purpose": "Account reconciliation", "retention": "Delete after validation"},
            {"name": "age", "type": "integer", "nullable": True, "sensitivity": "internal"},
            {"name": "score", "type": "decimal", "nullable": True,
             "precision": 8, "scale": 2, "sensitivity": "internal"},
            {"name": "active", "type": "boolean", "nullable": False, "sensitivity": "public"},
        ],
    }


def write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["person_id", "age", "score", "active"])
        writer.writerows(rows)
    return path


def test_import_typed_values_and_provenance(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    result = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    rows = read_snapshot(tmp_path / "project", result["import_id"])
    assert rows[0]["values"] == {"person_id": "a", "age": 21, "score": "12.30", "active": True}
    assert rows[0]["record_key"]
    assert rows[0]["source_locator"]["file_sha256"] == result["manifest"]["file_sha256"]


def test_exact_reimport_is_idempotent(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    first = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    second = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert first["import_id"] == second["import_id"]
    assert second["idempotent"] is True
    assert len(read_snapshot(tmp_path / "project", first["import_id"])) == 1


def test_record_key_stable_across_snapshots_but_row_id_changes(tmp_path):
    project = tmp_path / "project"
    first_file = write_csv(tmp_path / "first.csv", [["a", "21", "12.30", "true"]])
    first = ingest_csv(project, first_file, schema(), data_role="context")
    second_file = write_csv(tmp_path / "second.csv", [["a", "22", "12.30", "true"]])
    second = ingest_csv(project, second_file, schema(), data_role="context")
    a = read_snapshot(project, first["import_id"])[0]
    b = read_snapshot(project, second["import_id"])[0]
    assert a["record_key"] == b["record_key"]
    assert a["row_id"] != b["row_id"]
    assert a["values"]["age"] == 21 and b["values"]["age"] == 22


def test_duplicate_primary_key_fails_without_partial_rows(tmp_path):
    source = write_csv(tmp_path / "people.csv", [
        ["a", "21", "12.30", "true"], ["a", "22", "13.30", "false"]
    ])
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(project, source, schema(), data_role="context")
    assert exc.value.code == "PRIMARY_KEY_DUPLICATE"
    db = sqlite3.connect(project / "data" / "tabular.sqlite3")
    assert db.execute("select count(*) from import_rows").fetchone()[0] == 0
    assert db.execute("select count(*) from rejected_rows").fetchone()[0] == 2


def test_invalid_value_diagnostic_never_contains_value(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["sensitive-name", "not-an-int", "1.00", "true"]])
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert "not-an-int" not in str(exc.value)
    assert exc.value.diagnostic == {
        "row_number": 2, "column_name": "age", "error_code": "VALUE_INVALID"
    }


def test_personal_data_requires_purpose_and_retention_before_downstream_use():
    s = schema()
    s["columns"][0].pop("purpose")
    s["columns"][0].pop("retention")
    with pytest.raises(TabularIngestError, match="purpose and retention"):
        validate_downstream_policy(s)


def test_2001_rows_are_not_truncated(tmp_path):
    source = write_csv(tmp_path / "large.csv", [
        [f"id-{i}", str(i), "1.00", "true"] for i in range(2001)
    ])
    result = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert result["manifest"]["accepted_records"] == 2001
    assert len(read_snapshot(tmp_path / "project", result["import_id"])) == 2001


def test_row_limit_fails_explicitly_and_does_not_commit(tmp_path):
    source = write_csv(tmp_path / "limited.csv", [
        [f"id-{i}", str(i), "1.00", "true"] for i in range(3)
    ])
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(project, source, schema(), data_role="context", max_rows=2)
    assert exc.value.code == "ROW_LIMIT_EXCEEDED"
    db = sqlite3.connect(project / "data" / "tabular.sqlite3")
    assert db.execute("select count(*) from import_rows").fetchone()[0] == 0


def test_unknown_role_rejected(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, schema(), data_role="production")
    assert exc.value.code == "DATA_ROLE_INVALID"


def test_sealed_holdout_role_is_preserved_in_manifest(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    result = ingest_csv(tmp_path / "project", source, schema(), data_role="sealed_holdout")
    assert result["manifest"]["data_role"] == "sealed_holdout"


def test_changed_schema_fingerprint_creates_new_snapshot(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    first = ingest_csv(project, source, schema(), data_role="context")
    s = schema()
    s["schema_version"] = "1.0.1"
    second = ingest_csv(project, source, s, data_role="context")
    assert first["import_id"] != second["import_id"]


def test_utf8_bom_is_supported(tmp_path):
    source = tmp_path / "bom.csv"
    source.write_text("\ufeffperson_id,age,score,active\na,21,12.30,true\n", encoding="utf-8")
    result = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert result["manifest"]["accepted_records"] == 1


def test_malformed_header_fails_closed(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("person_id,person_id,score,active\na,21,1.00,true\n", encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert exc.value.code == "HEADER_INVALID"


def test_sensitive_rejection_stores_only_safe_diagnostic(tmp_path):
    s = schema()
    s["columns"][0]["sensitivity"] = "sensitive"
    source = write_csv(tmp_path / "bad.csv", [["SECRET-123", "not-int", "1.00", "true"]])
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError):
        ingest_csv(project, source, s, data_role="context")
    db = sqlite3.connect(project / "data" / "tabular.sqlite3")
    text = json.dumps(db.execute("select diagnostic_json from rejected_rows").fetchall())
    assert "SECRET-123" not in text
    assert "not-int" not in text


def test_source_role_is_registered(tmp_path):
    from agora.sources.registry import list_sources
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    ingest_csv(project, source, schema(), data_role="calibration")
    rows = list_sources(project / "governance" / "sources.jsonl")
    assert rows[0]["data_role"] == "calibration"


def test_empty_value_is_not_silently_converted_to_null(tmp_path):
    source = write_csv(tmp_path / "empty.csv", [["a", "", "1.00", "true"]])
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert exc.value.code == "VALUE_INVALID"
    s = schema()
    s["columns"][1]["empty_as_null"] = True
    result = ingest_csv(tmp_path / "project-allowed", source, s, data_role="context")
    assert read_snapshot(tmp_path / "project-allowed", result["import_id"])[0]["values"]["age"] is None


def test_failed_attempt_can_be_retried_without_idempotency_collision(tmp_path):
    source = write_csv(tmp_path / "retry.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError):
        ingest_csv(project, source, schema(), data_role="context", max_rows=0)
    result = ingest_csv(project, source, schema(), data_role="context")
    assert result["manifest"]["status"] == "committed"
    assert len(read_snapshot(project, result["import_id"])) == 1


def test_header_only_csv_rejected_unless_schema_allows_empty(tmp_path):
    source = tmp_path / "header-only.csv"
    source.write_text("person_id,age,score,active\n", encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    assert exc.value.code == "CSV_EMPTY"
    s = schema()
    s["allow_empty"] = True
    result = ingest_csv(tmp_path / "project-empty", source, s, data_role="context")
    assert result["manifest"]["accepted_records"] == 0




def test_personal_column_policy_is_declared_per_column():
    s = schema()
    validate_downstream_policy(s)
    s["columns"][0].pop("purpose")
    with pytest.raises(TabularIngestError, match="purpose and retention"):
        validate_downstream_policy(s)


def test_decimal_integer_and_date_bounds_use_native_types(tmp_path):
    s = schema()
    s["columns"][1]["minimum"] = 18
    s["columns"][2]["minimum"] = 10
    s["columns"][2]["maximum"] = 20
    source = write_csv(tmp_path / "bounds.csv", [["a", "19", "12.30", "true"]])
    result = ingest_csv(tmp_path / "project", source, s, data_role="context")
    assert result["manifest"]["accepted_records"] == 1
    bad = write_csv(tmp_path / "bad-bounds.csv", [["b", "17", "21.00", "true"]])
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project-bad", bad, s, data_role="context")
    assert exc.value.code == "VALUE_INVALID"

    date_schema = {
        "schema_id": "dates", "schema_version": "1", "dataset_id": "dates",
        "columns": [{"name": "day", "type": "date", "nullable": False,
                     "sensitivity": "internal", "minimum": "2026-01-01",
                     "maximum": "2026-12-31"}],
    }
    dates = tmp_path / "dates.csv"
    dates.write_text("day\n2026-07-15\n", encoding="utf-8")
    assert ingest_csv(tmp_path / "date-project", dates, date_schema,
                      data_role="context")["manifest"]["accepted_records"] == 1


def test_same_schema_version_with_changed_fingerprint_fails(tmp_path):
    source = write_csv(tmp_path / "drift.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    ingest_csv(project, source, schema(), data_role="context")
    changed = schema()
    changed["columns"][1]["nullable"] = False
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(project, source, changed, data_role="context")
    assert exc.value.code == "SCHEMA_DRIFT"


def test_new_schema_version_preserves_schema_history(tmp_path):
    source = write_csv(tmp_path / "versions.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    ingest_csv(project, source, schema(), data_role="context")
    newer = schema()
    newer["schema_version"] = "1.0.1"
    ingest_csv(project, source, newer, data_role="context")
    db = sqlite3.connect(project / "data" / "tabular.sqlite3")
    assert db.execute("select count(*) from dataset_schemas").fetchone()[0] == 2


def test_concurrent_identical_import_commits_one_snapshot(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    source = write_csv(tmp_path / "concurrent.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"
    barrier = threading.Barrier(2)

    def run():
        barrier.wait()
        return ingest_csv(project, source, schema(), data_role="context")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: run(), range(2)))
    assert first["import_id"] == second["import_id"]
    assert sum(bool(x["idempotent"]) for x in (first, second)) == 1
    assert len(read_snapshot(project, first["import_id"])) == 1


def test_csv_quoted_delimiter_escaped_quote_and_embedded_newline(tmp_path):
    s = {"schema_id": "notes", "schema_version": "1", "dataset_id": "notes",
         "columns": [{"name": "id", "type": "string", "nullable": False,
                      "primary_key": True, "sensitivity": "internal"},
                     {"name": "note", "type": "string", "nullable": False,
                      "sensitivity": "internal"}]}
    source = tmp_path / "notes.csv"
    expected = 'comma, quote " and\nnewline'
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "note"])
        writer.writerow(["n1", expected])
    result = ingest_csv(tmp_path / "project", source, s, data_role="context")
    row = read_snapshot(tmp_path / "project", result["import_id"])[0]
    assert row["values"]["note"] == expected


def test_invalid_encoding_and_malformed_quoting_fail_closed(tmp_path):
    s = {"schema_id": "simple", "schema_version": "1", "dataset_id": "simple",
         "columns": [{"name": "id", "type": "string", "nullable": False,
                      "sensitivity": "internal"}]}
    invalid = tmp_path / "invalid.csv"
    invalid.write_bytes(bytes([105, 100, 10, 255]))
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "invalid-project", invalid, s, data_role="context")
    assert exc.value.code == "CSV_PARSE_FAILED"
    malformed = tmp_path / "malformed.csv"
    malformed.write_text('id\n"unterminated\n', encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "malformed-project", malformed, s, data_role="context")
    assert exc.value.code == "CSV_PARSE_FAILED"


def test_uneven_row_width_fails_closed(tmp_path):
    s = {"schema_id": "simple", "schema_version": "1", "dataset_id": "simple",
         "columns": [{"name": "id", "type": "string", "nullable": False,
                      "sensitivity": "internal"}]}
    source = tmp_path / "uneven.csv"
    source.write_text("id\n1,extra\n", encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, s, data_role="context")
    assert exc.value.code == "ROW_WIDTH_INVALID"


def test_date_timestamp_and_enum_conversion(tmp_path):
    s = {
        "schema_id": "typed-extra", "schema_version": "1", "dataset_id": "typed-extra",
        "columns": [
            {"name": "day", "type": "date", "nullable": False, "sensitivity": "internal"},
            {"name": "created", "type": "timestamp", "nullable": False,
             "timezone": "UTC", "sensitivity": "internal"},
            {"name": "state", "type": "enum", "nullable": False,
             "allowed_values": ["active", "inactive"], "sensitivity": "internal"},
        ],
    }
    source = tmp_path / "typed-extra.csv"
    source.write_text(
        "day,created,state\n2026-11-20,2026-11-20T10:00:00Z,active\n",
        encoding="utf-8",
    )
    result = ingest_csv(tmp_path / "project", source, s, data_role="context")
    values = read_snapshot(tmp_path / "project", result["import_id"])[0]["values"]
    assert values == {
        "day": "2026-11-20", "created": "2026-11-20T10:00:00+00:00", "state": "active"
    }


def test_decimal_precision_and_scale_fail_closed(tmp_path):
    s = schema()
    source = write_csv(tmp_path / "bad-scale.csv", [["a", "21", "1.234", "true"]])
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, s, data_role="context")
    assert exc.value.code == "VALUE_INVALID"


@pytest.mark.parametrize("kind,bounds", [
    ("integer", {"minimum": "abc"}),
    ("decimal", {"minimum": "2", "maximum": "1"}),
    ("date", {"minimum": "not-a-date"}),
])
def test_invalid_schema_bounds_fail_before_reading_rows(tmp_path, kind, bounds):
    s = {
        "dataset_name": "bounds",
        "columns": [{"name": "value", "type": kind, "nullable": False, "sensitivity": "internal", **bounds}],
    }
    if kind == "decimal":
        s["columns"][0].update(precision=6, scale=2)
    source = tmp_path / "bounds.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "project", source, s, data_role="context")
    assert exc.value.code == "SCHEMA_BOUND_INVALID"


def test_csv_record_key_uses_shared_ontology_identity(tmp_path):
    source = write_csv(tmp_path / "shared-key.csv", [["same-id", "21", "12.30", "true"]])
    result = ingest_csv(tmp_path / "project", source, schema(), data_role="context")
    row = read_snapshot(tmp_path / "project", result["import_id"])[0]
    assert row["record_key"] == ontology_stable_record_key("people", "same-id")
    assert result["manifest"]["record_key_algorithm"] == "agora-record-v1"


def test_audit_failure_after_commit_preserves_import_and_pending_operation(tmp_path, monkeypatch):
    source = write_csv(tmp_path / "audit-success.csv", [["a", "21", "12.30", "true"]])
    project = tmp_path / "project"

    def fail_audit(*args, **kwargs):
        raise OSError("synthetic audit sink failure")

    monkeypatch.setattr(governance, "audit_event", fail_audit)
    result = ingest_csv(project, source, schema(), data_role="context")
    assert len(read_snapshot(project, result["import_id"])) == 1
    states = governance.operation_states(project)
    assert len(states) == 1
    assert next(iter(states.values()))["status"] == "pending"


def test_audit_failure_during_failed_import_preserves_original_error_and_pending_operation(
    tmp_path, monkeypatch
):
    source = write_csv(tmp_path / "audit-failure.csv", [["a", "not-an-integer", "12.30", "true"]])
    project = tmp_path / "project"

    def fail_audit(*args, **kwargs):
        raise OSError("synthetic audit sink failure")

    monkeypatch.setattr(governance, "audit_event", fail_audit)
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(project, source, schema(), data_role="context")
    assert exc.value.code == "VALUE_INVALID"
    states = governance.operation_states(project)
    assert len(states) == 1
    assert next(iter(states.values()))["status"] == "pending"



def test_policy_denial_is_audited_before_csv_source_is_read(tmp_path):
    source = tmp_path / "missing.csv"

    def deny(operation, resource):
        assert operation == "import"
        assert resource["dataset_id"] == "people"
        return {
            "decision": "deny", "reason": "cross_scope",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": ["people"],
        }

    with pytest.raises(TabularIngestError, match="Policy denied") as exc:
        ingest_csv(tmp_path / "project", source, schema(),
                   data_role="context", policy=deny)
    assert exc.value.code == "POLICY_DENIED"
    audit = AuditChainStore(tmp_path / "project" / "data" / "audit_chain.sqlite3")
    try:
        assert audit.verify()["valid"] is True
        row = audit.db.execute("SELECT event_json FROM audit_events").fetchone()
        event = json.loads(row[0])
        assert event["operation"] == "import"
        assert event["decision"] == "deny"
        assert event["reason"] == "cross_scope"
        assert event["resource_ids"] == ["people"]
    finally:
        audit.close()


def test_policy_allow_preserves_csv_import(tmp_path):
    source = write_csv(tmp_path / "people.csv", [["a", "21", "12.30", "true"]])
    seen = {}

    def allow(operation, resource):
        seen["operation"] = operation
        seen["resource"] = dict(resource)
        return {
            "decision": "allow", "reason": "policy_allow",
            "subject_id": "operator-1", "policy_version": "test-v1",
            "resource_ids": ["people"],
        }

    result = ingest_csv(tmp_path / "project", source, schema(),
                        data_role="context", policy=allow)
    assert result["manifest"]["accepted_records"] == 1
    assert seen["operation"] == "import"
    assert seen["resource"]["dataset_id"] == "people"

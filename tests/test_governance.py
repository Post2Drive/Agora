"""G0/G1 regression tests for compatibility and shared provenance foundations."""
import ast
import hashlib
import json

import pytest

from agora import governance
from agora.sources import registry
from agora.validation import audit_log


def test_report_renderer_parses_on_python_310():
    source = ( __import__("pathlib").Path(__file__).parents[1] / "agora/report/render.py").read_text(encoding="utf-8")
    ast.parse(source, filename="agora/report/render.py", feature_version=(3, 10))


def test_source_registry_round_trip_and_idempotency(tmp_path):
    path = tmp_path / "governance" / "sources.jsonl"
    raw = b"date,metric,value\\n2026-11-01,registrations,12\\n"
    first = registry.register_source(path, source_id="calibration-1", content=raw,
        data_role="calibration", publisher="test publisher", geography="India",
        population="apartment residents", extraction_status="reviewed", quality_flags=["complete"])
    second = registry.register_source(path, source_id="calibration-1", content=raw,
        data_role="calibration", publisher="test publisher", geography="India",
        population="apartment residents", extraction_status="reviewed", quality_flags=["complete"])
    assert first == second
    assert first["sha256"] == hashlib.sha256(raw).hexdigest()
    assert registry.get_source(path, "calibration-1") == first
    assert registry.list_sources(path) == [first]


def test_source_registry_rejects_conflicts_and_duplicate_rows(tmp_path):
    path = tmp_path / "sources.jsonl"
    registry.register_source(path, source_id="same", content=b"one", data_role="context")
    with pytest.raises(ValueError, match="Conflicting source_id"):
        registry.register_source(path, source_id="same", content=b"two", data_role="context")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registry.get_source(path, "same")) + "\n")
    with pytest.raises(ValueError, match="Duplicate source_id"):
        registry.list_sources(path)


def test_shared_governance_api_and_role_enforcement(tmp_path):
    raw = b"observations"
    governance.record_source(tmp_path, source_id="obs-1", content=raw,
        data_role="calibration", published_at="2026-11-01", licence="CC-BY-4.0")
    source_file = tmp_path / "data" / "observations.csv"
    source_file.parent.mkdir()
    source_file.write_bytes(raw)
    assert governance.source_roles(tmp_path) == {"obs-1": "calibration"}
    assert governance.require_registered_source(tmp_path, source_file) == ["obs-1"]
    with pytest.raises(PermissionError, match="(?i)sealed holdout"):
        governance.record_source(tmp_path, source_id="holdout-1", content=raw,
            data_role="sealed_holdout")
        governance.require_registered_source(tmp_path, source_file)


def test_audit_log_append_and_verify(tmp_path):
    path = tmp_path / "governance" / "audit.jsonl"
    governance.audit_event(tmp_path, "source_registered", source_id="s1")
    governance.audit_event(tmp_path, "source_used", source_id="s1")
    result = audit_log.verify(path)
    assert result["valid"] is True and result["entries"] == 2


def test_operation_journal_records_commit_failure_and_pending_recovery(tmp_path):
    committed = governance.begin_operation(tmp_path, "document_ingest", source_ids=["doc-1"])
    assert [row["operation_id"] for row in governance.pending_operations(tmp_path)] == [
        committed["operation_id"]]
    governance.finish_operation(tmp_path, committed["operation_id"], "committed",
                                details={"document_id": "doc-1"})
    failed = governance.begin_operation(tmp_path, "event_queue", source_ids=["event-1"])
    governance.finish_operation(tmp_path, failed["operation_id"], "failed", error="disk full")
    states = governance.operation_states(tmp_path)
    assert states[committed["operation_id"]]["status"] == "committed"
    assert states[failed["operation_id"]]["status"] == "failed"
    assert governance.pending_operations(tmp_path) == []
    with pytest.raises(ValueError, match="already committed"):
        governance.finish_operation(tmp_path, committed["operation_id"], "failed")


def test_operation_journal_rejects_invalid_state_history(tmp_path):
    path = tmp_path / "governance" / "operations.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"operation_id": "op-1", "operation_type": "ingest",
        "status": "committed", "created_at": "2026-11-19T00:00:00Z",
        "updated_at": "2026-11-19T00:00:01Z", "source_ids": [], "details": {}}) + "\n")
    with pytest.raises(ValueError, match="must begin pending"):
        governance.list_operations(tmp_path)


def test_calibration_upload_has_committed_operation_and_source_provenance(tmp_path):
    from agora.calibrate.project import save_data
    from conftest import make_project

    project = make_project(tmp_path, "calibration-provenance")
    save_data(project, "observations", "day,register_lakeview\n1,4\n")
    states = governance.operation_states(project)
    assert len(states) == 1
    operation = next(iter(states.values()))
    assert operation["status"] == "committed"
    assert operation["operation_type"] == "calibration_data_save"
    assert operation["source_ids"][0].startswith("data-observations-")
    assert governance.source_roles(project)[operation["source_ids"][0]] == "calibration"


def test_source_registry_rejects_malformed_records(tmp_path):
    path = tmp_path / "sources.jsonl"
    path.write_text(json.dumps({"source_id": "bad", "data_role": "context",
                                "sha256": "not-a-hash"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid source registry record"):
        registry.list_sources(path)


def test_exploratory_markdown_report_is_explicitly_qualified():
    from agora.report.render import to_markdown

    report = {"analysis": {"funnel": [], "choice": None}, "title": "Test report",
              "generated": "2026-11-19 00:00", "model": "mock",
              "sections": [], "quotes": {}}
    markdown = to_markdown(report)
    assert markdown.startswith("**EXPLORATORY SIMULATION")
    assert "# Test report" in markdown


def _append_audit_events(path, worker, count):
    for index in range(count):
        audit_log.append(path, {"event_type": "parallel_test", "worker": worker,
                                "sequence": index})


def test_audit_log_rejects_non_object_and_invalid_events(tmp_path):
    path = tmp_path / "audit.jsonl"
    with pytest.raises(TypeError, match="JSON object"):
        audit_log.append(path, ["not", "an", "object"])
    with pytest.raises(ValueError, match="event_type"):
        audit_log.append(path, {"event_type": ""})
    with pytest.raises(ValueError, match="reserved"):
        audit_log.append(path, {"event_type": "spoof", "entry_hash": "0" * 64})
    with pytest.raises(ValueError):
        audit_log.append(path, {"event_type": "bad_number", "value": float("nan")})
    assert not path.exists()


def test_audit_log_detects_non_object_json_and_blank_lines(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    result = audit_log.verify(path)
    assert result["valid"] is False
    assert result["reason"] == "audit record must be a JSON object"
    path.write_text("\n", encoding="utf-8")
    assert audit_log.verify(path)["reason"] == "blank JSONL record"


def test_audit_log_detects_truncated_final_record(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit_log.append(path, {"event_type": "first"})
    with path.open("ab") as handle:
        handle.write(b'{"event_type":"partial"}')
    result = audit_log.verify(path)
    assert result["valid"] is False
    assert "incomplete final" in result["reason"]
    with pytest.raises(ValueError, match="integrity check failed"):
        audit_log.append(path, {"event_type": "second"})


def test_audit_log_detects_tampering_and_reordering(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit_log.append(path, {"event_type": "first", "value": 1})
    audit_log.append(path, {"event_type": "second", "value": 2})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["value"] = 99
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    assert audit_log.verify(path)["reason"] == "entry hash mismatch"
    path.write_text("".join(json.dumps(row) + "\n" for row in reversed(rows)), encoding="utf-8")
    assert audit_log.verify(path)["valid"] is False


def test_audit_log_rejects_malformed_hashes_and_timestamps(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text(json.dumps({"event_type": "bad", "recorded_at": "yesterday",
        "previous_hash": "0" * 64, "entry_hash": "0" * 64}) + "\n", encoding="utf-8")
    result = audit_log.verify(path)
    assert result["valid"] is False
    assert result["reason"] == "missing or invalid recorded_at"


def test_audit_log_serialises_concurrent_process_appends(tmp_path):
    import multiprocessing

    path = str(tmp_path / "audit.jsonl")
    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_append_audit_events, args=(path, worker, 12))
                 for worker in range(4)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
    assert all(process.exitcode == 0 for process in processes)
    result = audit_log.verify(path)
    assert result["valid"] is True
    assert result["entries"] == 48


def test_audit_log_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text('{"event_type":"one","event_type":"two",'
                    '"recorded_at":"2026-11-19T00:00:00+00:00",'
                    '"previous_hash":"' + "0" * 64 + '","entry_hash":"' +
                    "0" * 64 + '"}\n', encoding="utf-8")
    result = audit_log.verify(path)
    assert result["valid"] is False
    assert "duplicate JSON object key" in result["reason"]

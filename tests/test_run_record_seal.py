"""Run record is hash-linked into the anchored audit chain (closes RT05 limitation). Synthetic only."""
import json
import shutil
from datetime import datetime, timezone

import pytest

import agora.pilot as pilot
from agora.pilot import PROJECT_ID, load_run_record, run_pilot, verify_run_record_seal

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def project(tmp_path):
    assert run_pilot(tmp_path / "run", now=NOW).status == "completed"
    return tmp_path / "run" / PROJECT_ID


def _edit(project, **kw):
    p = project / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec.update(kw)
    p.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")


def test_untouched_record_verifies(project):
    verify_run_record_seal(project)
    assert load_run_record(project)["status"] == "completed"


def test_well_formed_edit_is_detected(project):
    _edit(project, repository_sha="f" * 40)
    with pytest.raises(ValueError, match="seal"):
        load_run_record(project)


def test_whitespace_only_change_is_detected(project):
    p = project / "run_record.json"
    p.write_bytes(p.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="seal"):
        verify_run_record_seal(project)


def test_record_swapped_from_another_run_is_detected(project, tmp_path):
    assert run_pilot(tmp_path / "other", now=NOW).status == "completed"
    shutil.copy(tmp_path / "other" / PROJECT_ID / "run_record.json", project / "run_record.json")
    with pytest.raises(ValueError, match="seal"):
        verify_run_record_seal(project)


def test_missing_seal_event_is_detected(project, monkeypatch):
    monkeypatch.setattr(pilot, "_seal_id", lambda run_id: "other-" + run_id)
    with pytest.raises(ValueError, match="not sealed"):
        verify_run_record_seal(project)


def test_tampered_anchor_makes_seal_unverifiable(project):
    a = project / "audit_anchor" / "anchor.jsonl"
    a.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="unverifiable"):
        verify_run_record_seal(project)


def test_seal_failure_fails_the_pilot_closed(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise PermissionError("anchor down")
    monkeypatch.setattr(pilot, "seal_run_record", boom)
    with pytest.raises(PermissionError):
        run_pilot(tmp_path / "x", now=NOW)

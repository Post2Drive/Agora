"""Backup / restore / tamper drill (M2 item 5). Synthetic data only."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from agora.backup import ANCHOR_REL, CHAIN_REL, MANIFEST, BackupBlocked, backup, restore, verify_backup
from agora.cli import main as cli_main
from agora.pilot import PROJECT_ID, run_pilot

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def project(tmp_path):
    res = run_pilot(tmp_path / "run", now=NOW)
    assert res.status == "completed"
    return tmp_path / "run" / PROJECT_ID


def _rewrite_event(project):
    db = sqlite3.connect(project / CHAIN_REL)
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        db.execute(f"DROP TRIGGER {name}")  # an attacker with file access can do this
    db.execute("UPDATE audit_events SET event_json = replace(event_json, 'decision', 'DECISION') WHERE seq = 2")
    db.commit()
    db.close()


def test_backup_restore_round_trip_is_intact(project, tmp_path):
    out = backup(project, tmp_path / "bk")
    assert out["audit_status"] == "anchored_verified"
    assert verify_backup(tmp_path / "bk")["files"] == out["files"]
    res = restore(tmp_path / "bk", tmp_path / "restored")
    assert res["audit_status"] == "anchored_verified"
    assert (tmp_path / "restored" / "report" / "pilot_report.md").is_file()


def test_tampered_chain_blocks_backup_and_writes_nothing(project, tmp_path):
    _rewrite_event(project)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SOURCE_NOT_INTACT" and not (tmp_path / "bk").exists()


def test_tampered_anchor_blocks_backup(project, tmp_path):
    a = project / ANCHOR_REL
    lines = a.read_text(encoding="utf-8").splitlines()
    a.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")  # drop newest anchor: tail unanchored
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SOURCE_NOT_INTACT"


def test_modified_backup_file_blocks_restore(project, tmp_path):
    backup(project, tmp_path / "bk")
    _rewrite_event(tmp_path / "bk" / "data")
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", tmp_path / "restored")
    assert e.value.code == "BACKUP_FILE_MODIFIED" and not (tmp_path / "restored").exists()


def test_chain_tamper_detected_even_if_manifest_is_regenerated(project, tmp_path):
    backup(project, tmp_path / "bk")
    _rewrite_event(tmp_path / "bk" / "data")
    from agora.backup import _files, _sha
    mp = tmp_path / "bk" / MANIFEST
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["files"] = {r: _sha(tmp_path / "bk" / "data" / r) for r in _files(tmp_path / "bk" / "data")}
    mp.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", tmp_path / "restored")
    assert e.value.code == "BACKUP_NOT_INTACT" and e.value.status == "chain_integrity_failure"


def test_missing_extra_and_manifestless_backups_block(project, tmp_path):
    backup(project, tmp_path / "bk")
    (tmp_path / "bk" / "data" / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    assert e.value.code == "BACKUP_EXTRA_FILE"
    (tmp_path / "bk" / "data" / "extra.txt").unlink()
    (tmp_path / "bk" / "data" / "synthetic_units.csv").unlink()
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    assert e.value.code == "BACKUP_FILE_MISSING"
    (tmp_path / "bk" / MANIFEST).unlink()
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    assert e.value.code == "BACKUP_MANIFEST_MISSING"


def test_non_empty_destination_and_target_are_refused(project, tmp_path):
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "f").write_text("x", encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "busy")
    assert e.value.code == "DEST_NOT_EMPTY"
    backup(project, tmp_path / "bk")
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", tmp_path / "busy")
    assert e.value.code == "DEST_NOT_EMPTY" and (tmp_path / "busy" / "f").read_text() == "x"


def test_cli_drill_reports_in_plain_words(project, tmp_path, capsys):
    assert cli_main(["backup", "--project", str(project), "--dest", str(tmp_path / "bk")]) == 0
    assert cli_main(["backup", "verify", "--backup", str(tmp_path / "bk")]) == 0
    assert cli_main(["restore", "--backup", str(tmp_path / "bk"), "--target", str(tmp_path / "r")]) == 0
    assert "INTACT" in capsys.readouterr().out
    _rewrite_event(tmp_path / "bk" / "data")
    assert cli_main(["restore", "--backup", str(tmp_path / "bk"), "--target", str(tmp_path / "r2")]) == 2
    assert "BLOCKED BACKUP_FILE_MODIFIED" in capsys.readouterr().err

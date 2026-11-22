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


# --- hardening (symlinks, synthetic gate, manifest schema, post-copy verification) -------------

def _symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform")


def test_symlink_in_source_is_refused_and_nothing_written(project, tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("not part of the project", encoding="utf-8")
    _symlink_or_skip(project / "report" / "link.txt", secret)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "bk").exists()


def test_symlink_in_backup_blocks_verify_and_restore(project, tmp_path):
    backup(project, tmp_path / "bk")
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    _symlink_or_skip(tmp_path / "bk" / "data" / "link.txt", outside)
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", tmp_path / "restored")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "restored").exists()


def test_non_synthetic_or_unmarked_project_is_refused(project, tmp_path):
    rec = project / "run_record.json"
    data = json.loads(rec.read_text(encoding="utf-8"))
    data["data_class"] = "real"
    rec.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SOURCE_NOT_SYNTHETIC"
    rec.unlink()
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk2")
    assert e.value.code == "SOURCE_NOT_SYNTHETIC"
    assert not (tmp_path / "bk").exists() and not (tmp_path / "bk2").exists()


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(files=["a", "b"]),
    lambda m: m.update(files={"../escape.txt": "0" * 64}),
    lambda m: m.update(files={"/abs.txt": "0" * 64}),
    lambda m: m.update(files={"ok.txt": 7}),
    lambda m: m.update(files={"ok.txt": "zz"}),
    lambda m: m.update(synthetic_only=False),
    lambda m: m.update(manifest_version=2),
    lambda m: m.update(chain_id=5),
    lambda m: m.pop("files"),
])
def test_malformed_manifest_is_blocked_with_a_stable_code(project, tmp_path, mutate):
    backup(project, tmp_path / "bk")
    mf = tmp_path / "bk" / MANIFEST
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    mutate(manifest)
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    assert e.value.code == "BACKUP_MANIFEST_INVALID"


def test_non_object_manifest_is_blocked(project, tmp_path):
    backup(project, tmp_path / "bk")
    (tmp_path / "bk" / MANIFEST).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    assert e.value.code == "BACKUP_MANIFEST_INVALID"


def test_chain_changing_during_copy_is_detected_and_cleaned(project, tmp_path, monkeypatch):
    import agora.backup as mod
    real = mod._copy_one

    def racing(src, dst):
        real(src, dst)
        if dst.name == "chain.sqlite3":  # a writer appends/changes the chain after the snapshot verdict
            db = sqlite3.connect(dst)
            for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
                db.execute(f"DROP TRIGGER {n}")
            db.execute("DELETE FROM audit_events WHERE seq = (SELECT max(seq) FROM audit_events)")
            db.commit()
            db.close()
    monkeypatch.setattr(mod, "_copy_one", racing)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SNAPSHOT_CHANGED"
    assert not (tmp_path / "bk").exists()


def test_restore_rehashes_every_copied_file(project, tmp_path, monkeypatch):
    import agora.backup as mod
    backup(project, tmp_path / "bk")
    real = mod.shutil.copy2

    def corrupting(src, dst, *a, **k):
        out = real(src, dst, *a, **k)
        if str(dst).endswith("pilot_report.md"):
            with open(dst, "ab") as fh:
                fh.write(b"tampered in transit")
        return out
    monkeypatch.setattr(mod.shutil, "copy2", corrupting)
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", tmp_path / "restored")
    assert e.value.code == "RESTORED_NOT_INTACT"
    assert not (tmp_path / "restored").exists()


# --- root-level symlink refusal (M2 item 3 follow-up) -----------------------------------------

def test_symlinked_source_root_is_refused(project, tmp_path):
    link = tmp_path / "proj_link"
    _symlink_or_skip(link, project)
    with pytest.raises(BackupBlocked) as e:
        backup(link, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "bk").exists()


def test_symlinked_backup_destination_is_refused_and_outside_untouched(project, tmp_path):
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    link = tmp_path / "bk_link"
    _symlink_or_skip(link, outside)
    with pytest.raises(BackupBlocked) as e:
        backup(project, link)
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []


def test_symlinked_backup_root_data_and_manifest_block_verify_and_restore(project, tmp_path):
    backup(project, tmp_path / "bk")
    root_link = tmp_path / "bk_root_link"
    _symlink_or_skip(root_link, tmp_path / "bk")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(root_link)
    assert e.value.code == "UNSAFE_PATH"
    with pytest.raises(BackupBlocked) as e:
        restore(root_link, tmp_path / "r1")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "r1").exists()

    # symlinked data directory inside a real backup
    real = tmp_path / "bk2"
    backup(project, real)
    moved = tmp_path / "data_elsewhere"
    (real / "data").rename(moved)
    _symlink_or_skip(real / "data", moved)
    with pytest.raises(BackupBlocked) as e:
        verify_backup(real)
    assert e.value.code == "UNSAFE_PATH"

    # symlinked manifest
    real3 = tmp_path / "bk3"
    backup(project, real3)
    m_out = tmp_path / "manifest_elsewhere.json"
    (real3 / MANIFEST).rename(m_out)
    _symlink_or_skip(real3 / MANIFEST, m_out)
    with pytest.raises(BackupBlocked) as e:
        verify_backup(real3)
    assert e.value.code == "UNSAFE_PATH"


def test_symlinked_restore_target_is_refused_and_outside_untouched(project, tmp_path):
    backup(project, tmp_path / "bk")
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    link = tmp_path / "t_link"
    _symlink_or_skip(link, outside)
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", link)
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []

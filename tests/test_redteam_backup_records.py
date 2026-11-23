"""Track A red-team, group 3: record edits, backup/restore tamper, special files (RT04/RT05/RT08-RT11).

Synthetic data only. Each attack runs on a disposable copy under tmp_path. A test passes only when the
attack is refused with the pinned stable code AND nothing is published (no target) AND the original
backup bytes are unchanged. Two limitations are pinned as such, not hidden (see the *_limitation tests).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone

import pytest

from agora.backup import ANCHOR_REL, CHAIN_REL, MANIFEST, BackupBlocked, _files, _sha, backup, restore, verify_backup
from agora.pilot import PROJECT_ID, load_run_record, run_pilot

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
H64 = "sha256:" + "ab" * 32


@pytest.fixture()
def project(tmp_path):
    assert run_pilot(tmp_path / "run", now=NOW).status == "completed"
    return tmp_path / "run" / PROJECT_ID


def _tree_hash(root):
    return {r: _sha(root / r) for r in _files(root)}


def _regen_manifest(bk):
    mp = bk / MANIFEST
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["files"] = {r: _sha(bk / "data" / r) for r in _files(bk / "data")}
    mp.write_text(json.dumps(m), encoding="utf-8")


def _refused(bk, target, code):
    before = _tree_hash(bk)
    with pytest.raises(BackupBlocked) as e:
        restore(bk, target)
    assert e.value.code == code
    assert not target.exists()  # nothing published
    with pytest.raises(BackupBlocked):
        verify_backup(bk)
    assert _tree_hash(bk) == before  # backup untouched by the refusal


# ---- RT05 run-record edit after the fact ----------------------------------------------------
@pytest.mark.parametrize("field,value", [
    ("data_class", "real"), ("engine_invoked", True), ("validated_prediction_enabled", True),
    ("record_version", 999), ("run_id", None), ("status", 5), ("fixture_hashes", {"x.csv": "not-a-hash"}),
    ("fixture_hashes", {}), ("audit_ref", "head"), ("stage_results", [{"step": "x"}]),
])
def test_rt05_structural_run_record_edit_is_rejected_by_strict_loader(project, field, value):
    p = project / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec[field] = value
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(ValueError):
        load_run_record(project)


def test_rt05_run_record_edit_in_backup_is_caught_by_manifest(project, tmp_path):
    bk = tmp_path / "bk"
    backup(project, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["status"] = "completed-edited"
    p.write_text(json.dumps(rec), encoding="utf-8")
    _refused(bk, tmp_path / "restored", "BACKUP_FILE_MODIFIED")


def test_rt05_well_formed_run_record_edit_with_regenerated_manifest_is_detected_by_seal(project, tmp_path):
    """Formerly a pinned limitation: the run record is now hash-linked into the anchored audit chain
    (run_record_sealed event), so a well-formed edit plus a regenerated manifest is refused."""
    bk = tmp_path / "bk"
    backup(project, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    first = next(iter(rec["fixture_hashes"]))
    rec["fixture_hashes"][first] = H64
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")
    with pytest.raises(BackupBlocked):
        verify_backup(bk)


# ---- RT08 backup file tampering ---------------------------------------------------------------
def test_rt08_extra_file_missing_file_and_modified_file_are_each_refused(project, tmp_path):
    for i, (mutate, code) in enumerate([
        (lambda d: (d / "planted.txt").write_text("x"), "BACKUP_EXTRA_FILE"),
        (lambda d: (d / "run_record.json").unlink(), "BACKUP_FILE_MISSING"),
        (lambda d: (d / "run_record.json").write_bytes(b"{}"), "BACKUP_FILE_MODIFIED"),
    ]):
        bk = tmp_path / f"bk{i}"
        backup(project, bk)
        mutate(bk / "data")
        _refused(bk, tmp_path / f"out{i}", code)


@pytest.mark.parametrize("edit", [
    lambda m: m["files"].pop("run_record.json"),            # drop a member from the manifest
    lambda m: m["files"].update({"ghost.txt": "0" * 64}),    # list a file that does not exist
    lambda m: m["files"].update({"../evil": "0" * 64}),
    lambda m: m.update({"files": []}),
    lambda m: m.update({"synthetic_only": False}),
    lambda m: m.update({"manifest_version": 2}),
    lambda m: m.update({"chain_sequence": -1}),
])
def test_rt08_manifest_membership_and_schema_edits_are_refused(project, tmp_path, edit):
    bk = tmp_path / "bk"
    backup(project, bk)
    mp = bk / MANIFEST
    m = json.loads(mp.read_text(encoding="utf-8"))
    edit(m)
    mp.write_text(json.dumps(m), encoding="utf-8")
    before = _tree_hash(bk)
    with pytest.raises(BackupBlocked) as e:
        restore(bk, tmp_path / "out")
    assert e.value.code in {"BACKUP_MANIFEST_INVALID", "BACKUP_FILE_MISSING", "BACKUP_EXTRA_FILE"}
    assert not (tmp_path / "out").exists() and _tree_hash(bk) == before


# ---- RT09 audit pair tampering with a regenerated (self-consistent) manifest -----------------
def test_rt09_older_anchor_with_regenerated_manifest_is_not_intact(project, tmp_path):
    bk = tmp_path / "bk"
    backup(project, bk)
    a = bk / "data" / ANCHOR_REL
    lines = a.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    a.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "out", "BACKUP_NOT_INTACT")


def test_rt09_chain_from_another_run_with_regenerated_manifest_is_not_intact(project, tmp_path):
    other = tmp_path / "other"
    assert run_pilot(other, now=NOW.replace(hour=11)).status == "completed"
    bk = tmp_path / "bk"
    backup(project, bk)
    shutil.copy2(other / PROJECT_ID / CHAIN_REL, bk / "data" / CHAIN_REL)  # mismatched pair
    _regen_manifest(bk)
    _refused(bk, tmp_path / "out", "BACKUP_NOT_INTACT")


def test_rt09_manifest_head_edit_is_not_intact(project, tmp_path):
    bk = tmp_path / "bk"
    backup(project, bk)
    mp = bk / MANIFEST
    m = json.loads(mp.read_text(encoding="utf-8"))
    flat = json.dumps(m)
    assert "head_hash" in flat or "head" in flat
    for k, v in list(m.items()):
        if "head" in k and isinstance(v, str):
            m[k] = "0" * len(v)
    mp.write_text(json.dumps(m), encoding="utf-8")
    before = _tree_hash(bk)
    with pytest.raises(BackupBlocked) as e:
        restore(bk, tmp_path / "out")
    assert e.value.code in {"BACKUP_NOT_INTACT", "BACKUP_MANIFEST_INVALID"}
    assert not (tmp_path / "out").exists() and _tree_hash(bk) == before


def test_rt09_event_rewrite_inside_backup_with_regenerated_manifest_is_not_intact(project, tmp_path):
    bk = tmp_path / "bk"
    backup(project, bk)
    db = sqlite3.connect(bk / "data" / CHAIN_REL)
    for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        db.execute(f"DROP TRIGGER {n}")
    db.execute("UPDATE audit_events SET event_json = replace(event_json, 'a', 'b') WHERE seq = 1")
    db.commit()
    db.close()
    _regen_manifest(bk)
    _refused(bk, tmp_path / "out", "BACKUP_NOT_INTACT")


# ---- RT10 restore copy tampering ----------------------------------------------------------------
def test_rt10_non_audit_file_corrupted_during_restore_removes_target(project, tmp_path, monkeypatch):
    bk = tmp_path / "bk"
    backup(project, bk)
    before = _tree_hash(bk)
    real = shutil.copy2

    def evil(src, dst, *a, **k):
        out = real(src, dst, *a, **k)
        if str(dst).endswith("run_record.json"):
            with open(dst, "ab") as fh:
                fh.write(b" ")
        return out

    monkeypatch.setattr(shutil, "copy2", evil)
    with pytest.raises(BackupBlocked) as e:
        restore(bk, tmp_path / "out")
    assert e.value.code == "RESTORED_NOT_INTACT"
    assert not (tmp_path / "out").exists() and _tree_hash(bk) == before


def test_rt10_audit_pair_swapped_during_restore_removes_target(project, tmp_path, monkeypatch):
    """Stage mutation that keeps every listed file hash equal is impossible, so the swap is caught by
    the per-file rehash; the chain/anchor verification on the staged copy is the second gate."""
    bk = tmp_path / "bk"
    backup(project, bk)
    real = shutil.copy2

    def evil(src, dst, *a, **k):
        out = real(src, dst, *a, **k)
        if str(dst).endswith("anchor.jsonl"):
            lines = open(dst, encoding="utf-8").read().splitlines()
            open(dst, "w", encoding="utf-8").write("\n".join(lines[:-1]) + "\n")
        return out

    monkeypatch.setattr(shutil, "copy2", evil)
    with pytest.raises(BackupBlocked) as e:
        restore(bk, tmp_path / "out")
    assert e.value.code == "RESTORED_NOT_INTACT"
    assert not (tmp_path / "out").exists()


# ---- RT11 symlink / special files inside the project --------------------------------------------
@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_rt11_symlink_to_outside_sentinel_is_never_read_or_copied(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "secret.txt"
    sentinel.write_text("SENTINEL")
    mt = sentinel.stat().st_mtime_ns
    try:
        os.symlink(sentinel, project / "link.txt")
        os.symlink(outside, project / "linkdir")
    except OSError:
        pytest.skip("cannot create symlinks")
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH" and not (tmp_path / "bk").exists()
    assert sentinel.read_text() == "SENTINEL" and sentinel.stat().st_mtime_ns == mt
    assert sorted(os.listdir(outside)) == ["secret.txt"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no fifo")
def test_rt11_fifo_in_project_does_not_hang_or_leak_into_backup(project, tmp_path):
    os.mkfifo(project / "pipe")
    out = backup(project, tmp_path / "bk")  # must return (never open the pipe)
    assert not (tmp_path / "bk" / "data" / "pipe").exists()
    assert verify_backup(tmp_path / "bk")["files"] == out["files"]


def test_rt11_limitation_hardlink_to_outside_file_is_a_plain_file_and_is_copied(project, tmp_path):
    """PINNED LIMITATION: a hardlink is indistinguishable from a plain file by lstat, so its bytes are
    copied into the backup. Requires write access to the project tree; no outside file is modified."""
    outside = tmp_path / "outside.txt"
    outside.write_text("SENTINEL")
    try:
        os.link(outside, project / "hard.txt")
    except OSError:
        pytest.skip("cannot create hardlinks")
    backup(project, tmp_path / "bk")
    assert outside.read_text() == "SENTINEL"
    assert (tmp_path / "bk" / "data" / "hard.txt").read_text() == "SENTINEL"


# ---- RT05b run-record removal / status downgrade with regenerated manifest (ChatGPT 13:17 finding) ----
def test_rt05b_run_record_removed_with_regenerated_manifest_is_refused(project, tmp_path):
    bk = tmp_path / "bk"
    backup(project, bk)
    (bk / "data" / "run_record.json").unlink()
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


@pytest.mark.parametrize("status", ["denied", "failed", "bogus", "stopped"])
def test_rt05b_completed_record_status_changed_with_regenerated_manifest_is_refused(project, tmp_path, status):
    bk = tmp_path / "bk"
    backup(project, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["status"] = status
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


def test_rt05b_genuine_stopped_record_without_seal_is_still_valid(tmp_path):
    """Control: a real denied run (record present, no seal for its run_id) backs up, verifies, restores."""
    from agora.pilot import default_identities
    ids = default_identities(NOW)
    ids["operator"]["roles"] = ["reader"]
    res = run_pilot(tmp_path / "run", now=NOW, identities=ids)
    assert res.status == "stopped"
    proj = tmp_path / "run" / PROJECT_ID
    assert json.loads((proj / "run_record.json").read_text(encoding="utf-8"))["status"] == "denied"
    bk = tmp_path / "bk"
    backup(proj, bk)
    assert verify_backup(bk)["files"] > 0
    assert restore(bk, tmp_path / "restored")["restored_to"]


def test_rt05b_unknown_status_on_unsealed_stopped_record_is_refused(tmp_path):
    from agora.pilot import default_identities
    ids = default_identities(NOW)
    ids["operator"]["roles"] = ["reader"]
    run_pilot(tmp_path / "run", now=NOW, identities=ids)
    bk = tmp_path / "bk"
    backup(tmp_path / "run" / PROJECT_ID, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["status"] = "bogus"
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


# ---- RT05c residual cases (ChatGPT 14:02 finding): unsealed removal, status+run_id downgrade, bad IDs ----
def _stopped_backup(tmp_path):
    from agora.pilot import default_identities
    ids = default_identities(NOW)
    ids["operator"]["roles"] = ["reader"]
    run_pilot(tmp_path / "run", now=NOW, identities=ids)
    bk = tmp_path / "bk"
    backup(tmp_path / "run" / PROJECT_ID, bk)
    return bk


def test_rt05c_unsealed_stopped_backup_with_record_removed_and_manifest_regenerated_is_refused(tmp_path):
    bk = _stopped_backup(tmp_path)
    (bk / "data" / "run_record.json").unlink()
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


@pytest.mark.parametrize("status", ["denied", "failed"])
def test_rt05c_completed_downgraded_with_new_run_id_is_refused(project, tmp_path, status):
    bk = tmp_path / "bk"
    backup(project, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["status"], rec["run_id"] = status, "f" * 32
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


@pytest.mark.parametrize("bad", [None, "", "   ", 7, ["x"], True])
def test_rt05c_missing_empty_or_non_string_run_id_is_refused(project, tmp_path, bad):
    bk = tmp_path / "bk"
    backup(project, bk)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["status"] = "denied"
    if bad is None:
        rec.pop("run_id")
    else:
        rec["run_id"] = bad
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


@pytest.mark.parametrize("bad", [None, "", 7, ["x"]])
def test_rt05c_stopped_record_bad_run_id_is_refused(tmp_path, bad):
    bk = _stopped_backup(tmp_path)
    p = bk / "data" / "run_record.json"
    rec = json.loads(p.read_text(encoding="utf-8"))
    if bad is None:
        rec.pop("run_id")
    else:
        rec["run_id"] = bad
    p.write_text(json.dumps(rec), encoding="utf-8")
    _regen_manifest(bk)
    _refused(bk, tmp_path / "restored", "BACKUP_NOT_INTACT")


def test_rt05c_controls_genuine_completed_and_stopped_still_round_trip(project, tmp_path):
    bk = tmp_path / "bk1"
    backup(project, bk)
    assert restore(bk, tmp_path / "r1")["restored_to"]
    bk2 = _stopped_backup(tmp_path / "s")
    assert restore(bk2, tmp_path / "r2")["restored_to"]

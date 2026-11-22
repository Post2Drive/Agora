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
    lambda m: m.update(manifest_version=True),
    lambda m: m.update(manifest_version=1.0),
    lambda m: m.update(chain_sequence=True),
    lambda m: m.update(chain_sequence=-1),
    lambda m: m.update(chain_sequence=1.5),
    lambda m: m.update(chain_sequence="1"),
    lambda m: m.update(chain_head_hash="ABCDEF" + "0" * 58),
    lambda m: m.update(chain_head_hash="0" * 63),
    lambda m: m.update(chain_head_hash=None),
    lambda m: m.pop("chain_sequence"),
    lambda m: m.pop("chain_head_hash"),
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


def test_symlinked_ancestor_of_source_dest_backup_and_target_is_refused(project, tmp_path):
    parent_link = tmp_path / "parent_link"
    _symlink_or_skip(parent_link, tmp_path)
    # source reached through a linked ancestor
    with pytest.raises(BackupBlocked) as e:
        backup(parent_link / project.name, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    # destination below a linked ancestor: outside folder must stay untouched
    outside = tmp_path / "outside_parent"
    outside.mkdir()
    dest_link = tmp_path / "dest_parent_link"
    _symlink_or_skip(dest_link, outside)
    with pytest.raises(BackupBlocked) as e:
        backup(project, dest_link / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []
    # backup and restore target below a linked ancestor
    backup(project, tmp_path / "bk")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(parent_link / "bk")
    assert e.value.code == "UNSAFE_PATH"
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", dest_link / "restored")
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []


def test_nested_symlinked_run_record_is_refused_before_it_is_read(project, tmp_path, monkeypatch):
    outside = tmp_path / "outside_record.json"
    outside.write_text(json.dumps({"data_class": "synthetic"}), encoding="utf-8")
    rec = project / "run_record.json"
    rec.unlink()
    _symlink_or_skip(rec, outside)
    import agora.backup as bk
    read = []
    monkeypatch.setattr(bk, "_is_synthetic_project", lambda p: read.append(p) or True)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert read == []  # refused before any source file was read
    assert not (tmp_path / "bk").exists()


def test_lstat_error_fails_closed(project, tmp_path, monkeypatch):
    import os
    import agora.backup as bk
    real = os.lstat

    def boom(p, *a, **k):
        if str(p) == str(project):
            raise PermissionError("denied")
        return real(p, *a, **k)

    monkeypatch.setattr(bk.os, "lstat", boom)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "bk").exists()


def test_manifest_records_exact_chain_head(project, tmp_path):
    backup(project, tmp_path / "bk")
    m = json.loads((tmp_path / "bk" / MANIFEST).read_text(encoding="utf-8"))
    from agora.audit_anchor import verify_anchored_readonly
    v = verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, "synthetic-pilot-chain")
    assert m["chain_sequence"] == v["sequence"] and m["chain_head_hash"] == v["head_hash"]


def test_same_status_different_head_during_copy_is_snapshot_changed(project, tmp_path, monkeypatch):
    import agora.backup as mod
    real, calls = mod.verify_anchored_readonly, []

    def fake(*a, **k):
        v = dict(real(*a, **k))
        calls.append(1)
        if len(calls) == 2:  # the copy verifies "valid, same status" but at a different head
            v["sequence"] = v["sequence"] + 1
        return v
    monkeypatch.setattr(mod, "verify_anchored_readonly", fake)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SNAPSHOT_CHANGED"
    assert not (tmp_path / "bk").exists()


@pytest.mark.parametrize("edit", ["seq", "hash", "strip_seq", "strip_hash"])
def test_verify_rejects_manifest_head_mismatch_or_missing(project, tmp_path, edit):
    backup(project, tmp_path / "bk")
    mp = tmp_path / "bk" / MANIFEST
    m = json.loads(mp.read_text(encoding="utf-8"))
    if edit == "seq":
        m["chain_sequence"] += 1
    elif edit == "hash":
        m["chain_head_hash"] = "0" * 64
    elif edit == "strip_seq":
        del m["chain_sequence"]
    else:
        del m["chain_head_hash"]
    mp.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(tmp_path / "bk")
    expected = "BACKUP_MANIFEST_INVALID" if edit.startswith("strip") else "BACKUP_NOT_INTACT"
    assert e.value.code == expected
    with pytest.raises(BackupBlocked):
        restore(tmp_path / "bk", tmp_path / "r")
    assert not (tmp_path / "r").exists()


def test_symlink_dotdot_component_refused_before_outside_read_write(project, tmp_path):
    """symlink/.. must not be normalised away: it resolves outside, so refuse lexically."""
    sub = tmp_path / "sub"
    sub.mkdir()
    link = tmp_path / "lnk"
    _symlink_or_skip(link, sub)
    sneaky = link / ".." / project.name  # lexically == tmp_path/project, really sub/../project
    with pytest.raises(BackupBlocked) as e:
        backup(sneaky, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    outside = tmp_path / "outside_dd"
    outside.mkdir()
    with pytest.raises(BackupBlocked) as e:
        backup(project, link / ".." / "outside_dd" / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []
    backup(project, tmp_path / "bk")
    with pytest.raises(BackupBlocked) as e:
        verify_backup(link / ".." / "bk")
    assert e.value.code == "UNSAFE_PATH"
    with pytest.raises(BackupBlocked) as e:
        restore(tmp_path / "bk", link / ".." / "outside_dd" / "r")
    assert e.value.code == "UNSAFE_PATH"
    assert list(outside.iterdir()) == []


def test_plain_dotdot_without_symlink_also_refused_fail_closed(project, tmp_path):
    with pytest.raises(BackupBlocked) as e:
        backup(tmp_path / "x" / ".." / project.name, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"


def test_intermediate_ancestor_lstat_error_fails_closed(project, tmp_path, monkeypatch):
    import os
    import agora.backup as bk
    real = os.lstat
    mid = project.parent  # an ancestor, not the project root itself

    def boom(p, *a, **k):
        if str(p) == str(mid):
            raise PermissionError("denied")
        return real(p, *a, **k)

    monkeypatch.setattr(bk.os, "lstat", boom)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert not (tmp_path / "bk").exists()


@pytest.mark.parametrize("rel", ["audit/chain.sqlite3", "audit_anchor/anchor.jsonl"])
def test_nested_symlinked_chain_or_anchor_refused_before_any_read(project, tmp_path, monkeypatch, rel):
    target = project / rel
    outside = tmp_path / "outside_blob"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    _symlink_or_skip(target, outside)
    import agora.backup as bk
    read = []
    monkeypatch.setattr(bk, "_is_synthetic_project", lambda p: read.append(p) or True)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH"
    assert read == []
    assert not (tmp_path / "bk").exists()


# ---- M2: source writer lock and single-read manifest ------------------------------------------

def _append_event(project, event_id="late-1"):
    from agora.audit_anchor import open_anchored_audit
    from agora.backup import DEFAULT_CHAIN_ID
    with open_anchored_audit(project / CHAIN_REL, project / ANCHOR_REL, DEFAULT_CHAIN_ID) as audit:
        audit.append({"event_id": event_id, "event_type": "t", "subject_id": "u",
                      "operation": "import", "decision": "allow"})


def _spy_lock(monkeypatch, module, attr, name_filter, attempting, acquired):
    """Wrap a lock factory: `attempting` is set when a matching thread asks for the lock and
    `acquired` once it holds it. Handshake events replace sleep/timeout based synchronisation."""
    import contextlib
    import threading
    real = getattr(module, attr)

    @contextlib.contextmanager
    def spy(*a, **k):
        mine = threading.current_thread().name == name_filter
        if mine:
            attempting.set()
        with real(*a, **k) as value:
            if mine:
                acquired.set()
            yield value
    monkeypatch.setattr(module, attr, spy)


def _spy_os_lock_primitive(monkeypatch, name_filter, attempting):
    """Set `attempting` at the real OS lock call (flock / msvcrt.locking), made by the named thread
    immediately before it can block. A factory-entry flag would be set before the thread is
    actually waiting, so the handshake would not prove the writer is contending for the lock."""
    import os
    import threading
    if os.name == "nt":
        import msvcrt
        holder, attr = msvcrt, "locking"
    else:
        import fcntl
        holder, attr = fcntl, "flock"
    real = getattr(holder, attr)

    def spy(*a, **k):
        if threading.current_thread().name == name_filter:
            attempting.set()
        return real(*a, **k)
    monkeypatch.setattr(holder, attr, spy)


def test_real_writer_cannot_append_while_backup_holds_the_snapshot(project, tmp_path, monkeypatch):
    import threading
    import agora.audit_anchor as anchor_mod
    import agora.backup as mod
    attempting, acquired = threading.Event(), threading.Event()
    _spy_lock(monkeypatch, anchor_mod, "_exclusive_lock", "late-writer", threading.Event(), acquired)
    _spy_os_lock_primitive(monkeypatch, "late-writer", attempting)
    real = mod._copy_tree
    state = {}

    def copy_with_writer(src, dst, rels):
        t = threading.Thread(target=_append_event, args=(project,), name="late-writer")
        t.start()
        state["thread"] = t
        # handshake: the writer is provably waiting on the lock before the snapshot is copied
        assert attempting.wait(timeout=30), "writer never reached the lock"
        # a correct lock keeps it out for the whole copy; if the lock is missing it gets in
        state["acquired_during_copy"] = acquired.wait(timeout=0.5)
        real(src, dst, rels)
        state["acquired_during_copy"] = state["acquired_during_copy"] or acquired.is_set()
    monkeypatch.setattr(mod, "_copy_tree", copy_with_writer)
    before = mod.verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, mod.DEFAULT_CHAIN_ID)
    res = backup(project, tmp_path / "bk")
    state["thread"].join(timeout=30)
    assert state["acquired_during_copy"] is False, "writer was not excluded while the snapshot was taken"
    assert acquired.is_set() and not state["thread"].is_alive()
    info = verify_backup(tmp_path / "bk")  # snapshot is intact and holds the PRE-append head
    manifest = json.loads((tmp_path / "bk" / MANIFEST).read_text())
    assert (manifest["chain_sequence"], manifest["chain_head_hash"]) == (before["sequence"], before["head_hash"])
    after = mod.verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, mod.DEFAULT_CHAIN_ID)
    assert after["sequence"] == before["sequence"] + 1  # the writer ran only AFTER the backup finished
    assert res["audit_status"] == info["audit_status"] == "anchored_verified"


def test_backup_blocks_while_another_writer_holds_the_lock(project, tmp_path, monkeypatch):
    import threading
    import agora.backup as mod
    from agora.audit_anchor import AnchorStore
    from agora.backup import DEFAULT_CHAIN_ID
    attempting, acquired = threading.Event(), threading.Event()
    _spy_lock(monkeypatch, mod, "_source_writer_lock", "bk-thread", attempting, acquired)
    out = {}

    def run():
        out["res"] = backup(project, tmp_path / "bk")
    with AnchorStore(project / ANCHOR_REL, DEFAULT_CHAIN_ID).lock():
        t = threading.Thread(target=run, name="bk-thread")
        t.start()
        assert attempting.wait(timeout=30), "backup never asked for the writer lock"
        assert not acquired.wait(timeout=0.5), "backup did not wait for the writer lock"
        assert not (tmp_path / "bk" / MANIFEST).exists()
    t.join(timeout=30)
    assert acquired.is_set() and not t.is_alive()
    assert out["res"]["audit_status"] == "anchored_verified"


def test_backup_data_does_not_contain_the_lock_file(project, tmp_path):
    _append_event(project)  # creates the sidecar lock file
    assert (project / (ANCHOR_REL + ".lock")).exists()
    backup(project, tmp_path / "bk")
    assert not (tmp_path / "bk" / "data" / (ANCHOR_REL + ".lock")).exists()
    verify_backup(tmp_path / "bk")


def _count_manifest_reads(monkeypatch):
    from pathlib import Path
    reads = []
    real = Path.read_text

    def spy(self, *a, **k):
        if self.name == MANIFEST:
            reads.append(str(self))
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", spy)
    return reads


def test_verify_reads_the_manifest_exactly_once(project, tmp_path, monkeypatch):
    backup(project, tmp_path / "bk")
    reads = _count_manifest_reads(monkeypatch)
    verify_backup(tmp_path / "bk")
    assert len(reads) == 1


def test_restore_reads_the_manifest_exactly_once(project, tmp_path, monkeypatch):
    backup(project, tmp_path / "bk")
    reads = _count_manifest_reads(monkeypatch)
    restore(tmp_path / "bk", tmp_path / "out")
    assert len(reads) == 1

"""Backup holds the append-only files' writer locks while it copies. Synthetic data only."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

import agora.backup as backup_mod
from agora.backup import MANIFEST, BackupBlocked, backup, restore, verify_backup
from agora.jsonl_journal import try_writer_lock, writer_lock
from agora.pilot import PROJECT_ID, run_pilot

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def project(tmp_path):
    res = run_pilot(tmp_path / "run", now=NOW)
    assert res.status == "completed"
    return tmp_path / "run" / PROJECT_ID


def _free(path) -> bool:
    with try_writer_lock(path) as taken:
        return taken


def test_try_writer_lock_reports_a_held_lock_and_releases(tmp_path):
    f = tmp_path / "a.jsonl"
    with writer_lock(f):
        assert not _free(f)
    with try_writer_lock(f) as taken:
        assert taken and not _free(f)
    assert _free(f)


WRITER_FILES = (
    "events.jsonl", "events.synced.json", "events_candidates.jsonl",
    "governance/operations.jsonl", "governance/sources.jsonl", "governance/audit.jsonl",
    "validation/registry.jsonl", "validation/reviews.jsonl",
)


def _locks(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.lock"))


@pytest.mark.parametrize("name", WRITER_FILES)
def test_an_existing_writer_lock_is_held_during_the_copy(project, tmp_path, monkeypatch, name):
    with writer_lock(project / name):
        pass
    real, seen = backup_mod._copy_tree, []

    def copy(src, dst, rels):
        seen.append(_free(src / name))
        real(src, dst, rels)

    monkeypatch.setattr(backup_mod, "_copy_tree", copy)
    backup(project, tmp_path / "bk")
    assert seen == [False] and _free(project / name)


def test_backup_creates_no_lock_files_in_the_source(project, tmp_path):
    before = _locks(project)
    backup(project, tmp_path / "bk")
    assert set(_locks(project)) - set(before) <= {backup_mod.ANCHOR_REL + ".lock"}


def test_a_lock_file_elsewhere_in_the_project_is_taken_too(project, tmp_path, monkeypatch):
    # a prediction log or knowledge store may live under any name
    log = project / "models" / "predictions.jsonl"
    with writer_lock(log):
        log.write_text('{"kind": "x"}\n', encoding="utf-8")
    real, seen = backup_mod._copy_tree, []

    def copy(src, dst, rels):
        seen.append(_free(log))
        real(src, dst, rels)

    monkeypatch.setattr(backup_mod, "_copy_tree", copy)
    backup(project, tmp_path / "bk")
    assert seen == [False] and _free(log)


def test_backup_waits_for_a_writer_to_finish_its_record(project, tmp_path):
    log = project / "events.jsonl"
    started, finish = threading.Event(), threading.Event()

    def write():
        with writer_lock(log):
            with open(log, "ab") as fh:
                fh.write(b'{"id": "e1",')
                fh.flush()
                started.set()
                finish.wait(10)
                fh.write(b' "text": "t"}\n')

    writer = threading.Thread(target=write)
    writer.start()
    assert started.wait(10)
    timer = threading.Timer(0.5, finish.set)
    timer.start()
    try:
        backup(project, tmp_path / "bk")
    finally:
        finish.set()
        timer.cancel()
        writer.join(10)
    assert (tmp_path / "bk" / "data" / "events.jsonl").read_bytes() == b'{"id": "e1", "text": "t"}\n'


def test_a_writer_that_stays_busy_refuses_the_backup_and_keeps_no_locks(project, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "_LOCK_WAIT_SECONDS", 0.3)
    for name in WRITER_FILES:
        with writer_lock(project / name):
            pass
    busy = project / "validation" / "reviews.jsonl"  # sorts last, so every other lock was taken first
    with writer_lock(busy):
        with pytest.raises(BackupBlocked) as e:
            backup(project, tmp_path / "bk")
        assert all(_free(project / n) for n in WRITER_FILES if project / n != busy)
    assert e.value.code == "SOURCE_LOCK_FAILED" and not (tmp_path / "bk").exists()


def test_backup_holds_nothing_while_waiting_so_nested_writers_cannot_deadlock(project, tmp_path):
    # a writer holds a lock backup takes late, then wants one backup takes early
    first, second = project / "events.jsonl", project / "validation" / "registry.jsonl"
    with writer_lock(first):
        pass
    holding = threading.Event()
    done = []

    def nested():
        with writer_lock(second):
            holding.set()
            threading.Event().wait(0.4)  # let backup start trying
            with writer_lock(first):
                done.append(True)

    writer = threading.Thread(target=nested, daemon=True)
    writer.start()
    assert holding.wait(10)
    result = []
    runner = threading.Thread(target=lambda: result.append(backup(project, tmp_path / "bk")), daemon=True)
    runner.start()
    writer.join(15)
    runner.join(15)
    assert done == [True] and result


def test_restored_journals_keep_a_lock_file_and_the_backup_round_trips(project, tmp_path):
    log = project / "events.jsonl"
    with writer_lock(log):
        log.write_text('{"id": "e1"}\n', encoding="utf-8")
    backup(project, tmp_path / "bk")
    verify_backup(tmp_path / "bk")
    restore(tmp_path / "bk", tmp_path / "restored")
    assert (tmp_path / "restored" / "events.jsonl.lock").read_bytes() == b""


def test_a_lock_named_file_with_content_is_copied_as_data(project, tmp_path):
    (project / "vendor.lock").write_text("pinned\n", encoding="utf-8")
    backup(project, tmp_path / "bk")
    assert (tmp_path / "bk" / "data" / "vendor.lock").read_text(encoding="utf-8") == "pinned\n"
    assert (project / "vendor.lock").read_text(encoding="utf-8") == "pinned\n"


def test_a_file_named_only_dot_lock_is_data_and_locks_nothing_outside_the_project(project, tmp_path):
    (project / ".lock").write_bytes(b"")
    backup(project, tmp_path / "bk")
    assert (tmp_path / "bk" / "data" / ".lock").is_file()
    assert not project.with_name(project.name + ".lock").exists()


def test_a_writer_first_seen_during_the_copy_refuses_the_backup(project, tmp_path, monkeypatch):
    real = backup_mod._copy_tree

    def copy(src, dst, rels):
        real(src, dst, rels)
        with writer_lock(src / "late" / "predictions.jsonl"):
            pass

    monkeypatch.setattr(backup_mod, "_copy_tree", copy)
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "SNAPSHOT_CHANGED" and not (tmp_path / "bk").exists()


def test_a_writer_that_appears_before_the_listing_is_refused_before_anything_is_copied(
        project, tmp_path, monkeypatch):
    # the new lock file lands in the copy list; it must never be read (a held Windows lock blocks reads)
    real_files, copied = backup_mod._files, []

    def files(root):
        if root == project and collected and not (project / "late").exists():
            with writer_lock(project / "late" / "predictions.jsonl"):
                pass
        return real_files(root)

    collected = []
    real_locks = backup_mod._journal_writer_locks

    @contextmanager
    def locks(root):
        with real_locks(root) as held:
            collected.append(True)
            yield held

    monkeypatch.setattr(backup_mod, "_journal_writer_locks", locks)
    monkeypatch.setattr(backup_mod, "_files", files)
    monkeypatch.setattr(backup_mod, "_copy_tree", lambda src, dst, rels: copied.append(rels))
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert (e.value.code, e.value.status) == ("SNAPSHOT_CHANGED", "new_writer")
    assert copied == [] and (project / "late" / "predictions.jsonl.lock").is_file()
    assert not (tmp_path / "bk").exists()


def test_a_symlinked_lock_path_is_refused(project, tmp_path):
    target = tmp_path / "elsewhere"
    target.write_bytes(b"")
    try:
        (project / "events.jsonl.lock").symlink_to(target)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(BackupBlocked) as e:
        backup(project, tmp_path / "bk")
    assert e.value.code == "UNSAFE_PATH" and not (tmp_path / "bk" / MANIFEST).exists()

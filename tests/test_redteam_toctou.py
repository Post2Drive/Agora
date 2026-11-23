"""Track A RT06: concurrent path replacement between check and use (synthetic data only).

The chain is read through ONE held descriptor; a swap, in-place edit, or link after open must be refused
(fail closed), never silently followed by a path reopen."""
from __future__ import annotations

import os
import shutil
import sys
import sqlite3
from datetime import datetime, timezone

import pytest

from agora import pathsafe
from agora.audit_anchor import verify_anchored_readonly
from agora.pathsafe import UnsafePathError, open_ro_snapshot, read_stable_bytes
from agora.pilot import (CHAIN_ID, PROJECT_ID, chain_has_seal_event, load_run_record, run_pilot,
                         verify_run_record_seal)

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture()
def project(tmp_path):
    assert run_pilot(tmp_path / "run", now=NOW).status == "completed"
    return tmp_path / "run" / PROJECT_ID


@pytest.fixture(autouse=True)
def _clear_hook():
    yield
    pathsafe._RACE_HOOK = None


def _swap_with_forged(p):
    forged = p.with_name("forged.sqlite3")
    shutil.copy(p, forged)
    db = sqlite3.connect(forged)
    db.execute("DROP TRIGGER IF EXISTS protect_audit_event_delete")
    db.execute("DELETE FROM audit_events")
    db.commit(); db.close()
    os.replace(forged, p)


def test_control_snapshot_matches_path_read(project):
    chain = project / "audit" / "chain.sqlite3"
    db = open_ro_snapshot(chain)
    assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] > 0
    assert chain_has_seal_event(project) is True
    verify_run_record_seal(project)
    assert load_run_record(project)["status"] == "completed"


_SWAP = pytest.mark.skipif(sys.platform == "win32", reason="Windows refuses to replace an open file (own protection)")


@_SWAP
def test_swap_after_read_is_refused(project):
    chain = project / "audit" / "chain.sqlite3"
    pathsafe._RACE_HOOK = _swap_with_forged
    with pytest.raises(UnsafePathError):
        read_stable_bytes(chain)


@_SWAP
def test_swap_makes_verify_report_unreadable_not_valid(project):
    pathsafe._RACE_HOOK = _swap_with_forged
    v = verify_anchored_readonly(project / "audit" / "chain.sqlite3",
                                 project / "audit_anchor" / "anchor.jsonl", CHAIN_ID)
    assert v["valid"] is False and v["status"] == "store_unreadable"


@_SWAP
def test_swap_blocks_seal_verification_and_seal_probe(project):
    pathsafe._RACE_HOOK = _swap_with_forged
    with pytest.raises(ValueError):
        verify_run_record_seal(project)
    pathsafe._RACE_HOOK = _swap_with_forged
    with pytest.raises(ValueError):
        chain_has_seal_event(project)


def test_in_place_append_during_read_is_refused(project):
    chain = project / "audit" / "chain.sqlite3"

    def grow(p):
        with open(p, "ab") as f:
            f.write(b"\0" * 8)
    pathsafe._RACE_HOOK = grow
    with pytest.raises(UnsafePathError):
        read_stable_bytes(chain)


def test_symlink_and_directory_refused(project, tmp_path):
    chain = project / "audit" / "chain.sqlite3"
    link = tmp_path / "link.sqlite3"
    try:
        link.symlink_to(chain)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(UnsafePathError):
        read_stable_bytes(link)
    with pytest.raises(UnsafePathError):
        read_stable_bytes(project / "audit")

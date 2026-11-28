"""A staged store copy that cannot be deleted is reported: error, log and audit event.

Each staged copy holds every record in the store. The deletion refusal is simulated, so the
same paths run on Linux and Windows. All data is synthetic.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from agora.ontology import OntologyError, StagedCopyError
from agora.ontology.store import _discard_staged_copy
from test_ontology_maintenance_privacy import (  # noqa: F401  (env is a fixture)
    GIVEN, _staged_operations, env,
)
from test_ontology_store import _allow

_EVENT = "ontology_staged_copy_not_removed"


def _refuse_unlink(monkeypatch, matches):
    """Make deleting any matching file fail the way a locked file does."""
    real = Path.unlink

    def _unlink(self, *args, **kwargs):
        if matches(self.name) and self.exists():
            raise PermissionError("file is in use")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)


def _reports(env):
    rows = env["audit"].chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq").fetchall()
    return [event for event in (json.loads(row[0]) for row in rows) if event.get("event_type") == _EVENT]


def _held(folder):
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(".tmp"))


def test_discard_returns_only_what_was_refused(tmp_path, monkeypatch):
    staged = tmp_path / "copy.tmp"
    staged.write_bytes(b"x")
    (tmp_path / "copy.tmp-wal").write_bytes(b"x")
    _refuse_unlink(monkeypatch, lambda name: name.endswith("-wal"))
    assert [p.name for p in _discard_staged_copy(staged)] == ["copy.tmp-wal"]
    assert not staged.exists()


def test_discard_of_absent_files_reports_nothing(tmp_path):
    assert _discard_staged_copy(tmp_path / "never.tmp") == []


@pytest.mark.parametrize("operation", ["backup", "manifest", "restore"])
def test_a_refused_operation_says_the_copy_is_still_there(env, monkeypatch, caplog, operation):
    folder, call = _staged_operations(env)[operation]
    _refuse_unlink(monkeypatch, lambda name: name.endswith(".tmp"))
    with caplog.at_level(logging.ERROR, logger="agora.ontology.store"):
        with pytest.raises(StagedCopyError) as raised:
            call(env["rules"])  # no purpose or retention
    left = _held(folder)
    assert len(left) == 1
    # The original refusal stays visible and the file to remove is named.
    assert "policy denied" in str(raised.value) and left[0] in str(raised.value)
    assert [p.name for p in raised.value.remaining] == left
    assert isinstance(raised.value.__cause__, OntologyError)
    assert any(left[0] in record.getMessage() for record in caplog.records)
    (event,) = _reports(env)
    assert f"file:{left[0]}" in event["resource_ids"]
    assert event["reason"] == "staged_copy_not_removed"


@pytest.mark.parametrize("operation", ["backup", "manifest", "restore"])
def test_a_finished_operation_still_succeeds_but_is_reported(env, monkeypatch, caplog, operation):
    folder, call = _staged_operations(env)[operation]
    _refuse_unlink(monkeypatch, lambda name: name.endswith(".tmp"))
    with caplog.at_level(logging.ERROR, logger="agora.ontology.store"):
        result = call(_allow)
    assert result is not None
    left = _held(folder)
    assert len(left) == 1
    assert any(left[0] in record.getMessage() for record in caplog.records)
    (event,) = _reports(env)
    assert f"file:{left[0]}" in event["resource_ids"]


@pytest.mark.parametrize("operation", ["backup", "manifest", "restore"])
def test_a_clean_run_reports_nothing(env, caplog, operation):
    folder, call = _staged_operations(env)[operation]
    with caplog.at_level(logging.ERROR, logger="agora.ontology.store"):
        call(_allow)
    assert _held(folder) == [] and _reports(env) == [] and not caplog.records


def test_an_interrupt_keeps_its_type_and_is_still_reported(env, monkeypatch):
    folder, call = _staged_operations(env)["backup"]

    def _stop(conn):
        raise KeyboardInterrupt

    monkeypatch.setattr(type(env["store"]), "_verify_connection_integrity", staticmethod(_stop))
    _refuse_unlink(monkeypatch, lambda name: name.endswith(".tmp"))
    with pytest.raises(KeyboardInterrupt):
        call(_allow)
    assert len(_held(folder)) == 1 and len(_reports(env)) == 1


def test_a_failed_audit_report_does_not_hide_the_error(env, monkeypatch, caplog):
    folder, call = _staged_operations(env)["backup"]
    real = env["audit"].append

    def _append(event, *args, **kwargs):
        if event.get("event_type") == _EVENT:
            raise RuntimeError("audit unavailable")
        return real(event, *args, **kwargs)

    monkeypatch.setattr(env["audit"], "append", _append)
    _refuse_unlink(monkeypatch, lambda name: name.endswith(".tmp"))
    with caplog.at_level(logging.ERROR, logger="agora.ontology.store"):
        with pytest.raises(StagedCopyError, match="policy denied"):
            call(env["rules"])
    assert any("could not record" in record.getMessage() for record in caplog.records)


def test_an_unanchored_backup_that_cannot_be_removed_is_reported(env, monkeypatch):
    destination = env["project"] / "data" / "unanchored.sqlite3"
    real = env["audit"].append

    def _append(event, *args, **kwargs):
        if event.get("event_type") == "ontology_backup_anchored":
            raise RuntimeError("anchor write failed")
        return real(event, *args, **kwargs)

    monkeypatch.setattr(env["audit"], "append", _append)
    _refuse_unlink(monkeypatch, lambda name: name == destination.name)
    with pytest.raises(StagedCopyError, match="could not be anchored") as raised:
        env["store"].create_anchored_backup(destination, policy=env["rules"], audit=env["audit"], **GIVEN)
    assert [p.name for p in raised.value.remaining] == [destination.name]
    assert destination.exists()
    (event,) = _reports(env)
    assert event["operation"] == "store_anchored_backup"


def test_a_manifest_made_while_handling_another_error_still_succeeds(env, monkeypatch):
    """Inside a caller's ``except`` block the old error is still current; it is not this call's failure."""
    _, call = _staged_operations(env)["manifest"]
    _refuse_unlink(monkeypatch, lambda name: name.endswith(".tmp"))
    try:
        raise OntologyError("an earlier, already handled failure")
    except OntologyError:
        assert call(_allow)["manifest_sha256"]
    assert len(_reports(env)) == 1


def test_an_interrupt_while_anchoring_keeps_its_type(env, monkeypatch):
    destination = env["project"] / "data" / "interrupted.sqlite3"
    real = env["audit"].append

    def _append(event, *args, **kwargs):
        if event.get("event_type") == "ontology_backup_anchored":
            raise KeyboardInterrupt
        return real(event, *args, **kwargs)

    monkeypatch.setattr(env["audit"], "append", _append)
    _refuse_unlink(monkeypatch, lambda name: name == destination.name)
    with pytest.raises(KeyboardInterrupt):
        env["store"].create_anchored_backup(destination, policy=env["rules"], audit=env["audit"], **GIVEN)
    assert destination.exists() and len(_reports(env)) == 1

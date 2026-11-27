from __future__ import annotations

import json
import sqlite3
import time

import pytest

from agora import audit_chain
from agora.audit_chain import AuditChainStore


def test_hash_chain_redacts_and_verifies(tmp_path):
    store = AuditChainStore(tmp_path / "audit.db")
    first = store.append({"event_id": "e1", "event_type": "import", "email": "person@example.test", "count": 1})
    second = store.append({"event_id": "e2", "event_type": "bind", "previous": first["event_hash"]})
    assert first["event"]["email"] == "[REDACTED]"
    assert second["previous_hash"] == first["event_hash"]
    assert store.verify()["valid"] is True
    store.close()


def test_tamper_delete_reorder_and_replay_are_rejected(tmp_path):
    store = AuditChainStore(tmp_path / "audit.db")
    store.append({"event_id": "e1", "event_type": "one"})
    store.append({"event_id": "e2", "event_type": "two"})
    with pytest.raises(ValueError, match="replay"):
        store.append({"event_id": "e1", "event_type": "one"})
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM audit_events WHERE seq=1")
    store.db.execute("DROP TRIGGER protect_audit_event_update")
    store.db.execute("UPDATE audit_events SET event_json=? WHERE seq=2", (json.dumps({"event_id": "e2", "event_type": "tampered"}),))
    store.db.commit()
    assert store.verify()["valid"] is False
    store.close()


def test_reordered_chain_reports_first_broken_link(tmp_path):
    store = AuditChainStore(tmp_path / "audit.db")
    store.append({"event_id": "e1", "event_type": "one"})
    store.append({"event_id": "e2", "event_type": "two"})
    store.db.execute("DROP TRIGGER protect_audit_event_update")
    rows = store.db.execute("SELECT event_json FROM audit_events ORDER BY seq").fetchall()
    store.db.execute("UPDATE audit_events SET event_json=? WHERE seq=1", (rows[1][0],))
    store.db.commit()
    result = store.verify()
    assert result["valid"] is False
    assert result["first_broken_sequence"] == 1
    store.close()


def test_sensitive_values_are_redacted_without_hashes(tmp_path):
    store = AuditChainStore(tmp_path / "audit.db")
    item = store.append({"event_id": "e1", "event_type": "profile", "phone": "9999999999", "nested": {"address": "secret"}})
    serialized = json.dumps(item)
    assert "9999999999" not in serialized and "secret" not in serialized
    assert "value_hash" not in serialized
    store.close()


def test_allowlisted_audit_fields_pass_and_unknown_personal_fields_redact(tmp_path):
    store = AuditChainStore(tmp_path / "audit.db")
    item = store.append({
        "event_id": "e1", "event_type": "export", "subject_id": "u1",
        "operation": "report_export", "decision": "deny", "policy_version": "v1",
        "resource_ids": ["r1"], "reason": "scope_missing", "count": 2,
        "schema_hash": "sha256:abc", "customer_name": "Ada", "dob": "2000-01-01",
        "unknown_field": "secret",
    })
    assert item["event"]["subject_id"] == "u1"
    assert item["event"]["schema_hash"] == "sha256:abc"
    assert item["event"]["customer_name"] == "[REDACTED]"
    assert item["event"]["dob"] == "[REDACTED]"
    assert item["event"]["unknown_field"] == "[REDACTED]"
    assert "Ada" not in json.dumps(item) and "2000-01-01" not in json.dumps(item)
    store.close()


def test_two_connections_append_without_forking_chain(tmp_path):
    left = AuditChainStore(tmp_path / "audit.db")
    right = AuditChainStore(tmp_path / "audit.db")
    left.append({"event_id": "e1", "event_type": "one"})
    right.append({"event_id": "e2", "event_type": "two"})
    assert left.verify()["valid"] is True
    assert right.verify()["valid"] is True
    left.close()
    right.close()


def test_concurrent_threads_do_not_fork_chain(tmp_path):
    import threading

    path = tmp_path / "audit.db"
    AuditChainStore(path).close()
    errors: list[str] = []

    def writer(prefix: str) -> None:
        store = AuditChainStore(path)  # one connection per thread
        try:
            for i in range(25):
                try:
                    store.append({"event_id": f"{prefix}{i}", "event_type": "t"})
                except Exception as exc:  # noqa: BLE001 - recorded for the assertion
                    errors.append(str(exc))
        finally:
            store.close()

    threads = [threading.Thread(target=writer, args=(p,)) for p in "abcd"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    verifier = AuditChainStore(path)
    result = verifier.verify()
    verifier.close()
    assert errors == []
    assert result["valid"] is True
    assert result["entries"] == 100


def _hold_write_lock(path):
    holder = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE")
    return holder


def test_append_waits_out_a_writer_that_holds_the_lock_longer_than_five_seconds(tmp_path):
    import threading

    path = tmp_path / "audit.db"
    store = AuditChainStore(path)
    holder = _hold_write_lock(path)
    release = threading.Timer(6.0, holder.rollback)
    release.start()
    try:
        store.append({"event_id": "waited", "event_type": "t"})
        result = store.verify()
    finally:
        release.join()
        holder.close()
        store.close()
    assert result["valid"] is True
    assert result["entries"] == 1


def test_append_wait_is_bounded_and_a_timed_out_append_writes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    AuditChainStore(path).close()
    monkeypatch.setattr(audit_chain, "BUSY_TIMEOUT_SECONDS", 0.2)
    store = AuditChainStore(path)
    holder = _hold_write_lock(path)
    try:
        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            store.append({"event_id": "refused", "event_type": "t"})
        assert time.monotonic() - started < 10  # the configured wait is the one used
        holder.rollback()
        assert store.find_event("refused") is None
        store.append({"event_id": "refused", "event_type": "t"})  # the same connection is still usable
        assert store.verify()["entries"] == 1
    finally:
        holder.close()
        store.close()


def test_commit_that_times_out_behind_a_reader_rolls_back_and_leaves_the_store_usable(tmp_path, monkeypatch):
    path = tmp_path / "audit.db"
    AuditChainStore(path).close()
    monkeypatch.setattr(audit_chain, "BUSY_TIMEOUT_SECONDS", 0.2)
    store = AuditChainStore(path)
    reader = sqlite3.connect(str(path), isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM audit_events").fetchall()  # keeps a shared lock until rollback
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            store.append({"event_id": "refused", "event_type": "t"})
        reader.rollback()
        assert store.find_event("refused") is None
        store.append({"event_id": "refused", "event_type": "t"})
        assert store.verify()["entries"] == 1
    finally:
        reader.close()
        store.close()

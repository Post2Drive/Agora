from __future__ import annotations

import json
import sqlite3

import pytest

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

from __future__ import annotations

import json

import pytest

from agora.audit_chain import AuditChainStore
from agora.policy_enforcement import PolicyEnforcementError, enforce_policy


def test_policy_none_preserves_legacy_behavior(tmp_path):
    assert enforce_policy(
        None, project=tmp_path, operation="import",
        resource={"project_id": "p1", "resource_ids": ["dataset-1"]},
    ) is None
    assert not (tmp_path / "data" / "audit_chain.sqlite3").exists()


def test_policy_allow_returns_decision_without_writing_audit(tmp_path):
    decision = {
        "decision": "allow", "reason": "policy_allow",
        "subject_id": "user-1", "policy_version": "test-v1",
        "resource_ids": ["dataset-1"],
    }
    result = enforce_policy(
        lambda operation, resource: decision,
        project=tmp_path, operation="import",
        resource={"project_id": "p1", "resource_ids": ["dataset-1"]},
    )
    assert result == decision
    assert not (tmp_path / "data" / "audit_chain.sqlite3").exists()


def test_policy_deny_is_audited_with_allowlisted_fields_only(tmp_path):
    decision = {
        "decision": "deny", "reason": "cross_scope",
        "subject_id": "user-1", "policy_version": "test-v1",
        "resource_ids": ["dataset-1"],
    }
    with pytest.raises(PolicyEnforcementError, match="policy denied"):
        enforce_policy(
            lambda operation, resource: decision,
            project=tmp_path, operation="binding",
            resource={"project_id": "p1", "resource_ids": ["dataset-1"]},
        )

    store = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    try:
        events = store.db.execute("SELECT event_json FROM audit_events").fetchall()
        assert len(events) == 1
        event = json.loads(events[0][0])
        assert event == {
            "decision": "deny", "event_id": event["event_id"],
            "event_type": "policy_denied", "operation": "binding",
            "policy_version": "test-v1", "reason": "cross_scope",
            "resource_ids": ["dataset-1"], "subject_id": "user-1",
            "recorded_at": event["recorded_at"],
        }
        assert store.verify()["valid"] is True
    finally:
        store.close()


def test_policy_exception_fails_closed_and_is_audited(tmp_path):
    def broken_policy(operation, resource):
        raise RuntimeError("private details must not be logged")

    with pytest.raises(PolicyEnforcementError, match="policy denied"):
        enforce_policy(
            broken_policy, project=tmp_path, operation="simulation_input",
            resource={"project_id": "p1", "resource_ids": ["import-1"]},
        )
    raw = (tmp_path / "data" / "audit_chain.sqlite3").read_bytes()
    assert b"private details must not be logged" not in raw

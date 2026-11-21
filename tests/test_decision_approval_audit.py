from __future__ import annotations

import json

import pytest

from agora.audit_chain import AuditChainStore
from agora.decisions.approval import (
    ApprovalTransitionError, approve, expire, propose, reject, supersede,
)
from agora.decisions.store import DecisionRecordStore
from tests.test_decision_approval import approve_args, draft_record


def _events(audit):
    return [json.loads(row[0]) for row in audit.db.execute(
        "SELECT event_json FROM audit_events ORDER BY rowid")]


def _store_with_proposal(tmp_path, audit):
    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    proposed = propose(
        store, "decision-approval-001", 1, actor="analyst",
        now="2026-11-21T10:00:00Z", audit=audit,
    )
    return store, proposed


def test_lifecycle_events_are_chained_and_allow_listed(tmp_path):
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    store, proposed = _store_with_proposal(tmp_path, audit)
    approved = approve(
        store, proposed.decision_id, proposed.version,
        audit=audit, **approve_args(proposed),
    )
    events = _events(audit)
    assert [event["event_type"] for event in events] == ["decision_proposed", "decision_approved"]
    assert events[1]["subject_id"] == "approver-1"
    assert events[1]["decision"] == "allow"
    assert events[1]["resource_ids"] == ["decision-approval-001", f"version-{approved.version}"]
    assert events[1]["decision_fingerprint"] == approved.fingerprint
    assert audit.verify()["valid"] is True
    # Free-text decision content never enters the audit chain.
    assert "synthetic pilot cohort" not in json.dumps(events)
    store.close(); audit.close()


def test_denied_approval_is_audited_and_changes_nothing(tmp_path):
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    store, proposed = _store_with_proposal(tmp_path, audit)
    with pytest.raises(PermissionError, match="decision approval denied"):
        approve(
            store, proposed.decision_id, proposed.version,
            audit=audit, **approve_args(proposed, role="operator"),
        )
    events = _events(audit)
    assert [event["event_type"] for event in events] == [
        "decision_proposed", "decision_approval_denied",
    ]
    assert events[1]["decision"] == "deny"
    assert events[1]["reason"] == "role_not_permitted"
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    assert audit.verify()["valid"] is True
    store.close(); audit.close()


def test_without_audit_argument_behaviour_is_unchanged(tmp_path):
    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    proposed = propose(store, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
    approved = approve(store, proposed.decision_id, proposed.version, **approve_args(proposed))
    assert approved.status == "approved"
    assert not (tmp_path / "audit.sqlite3").exists()
    store.close()


def test_reject_expire_and_supersede_are_audited(tmp_path):
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    store, proposed = _store_with_proposal(tmp_path, audit)
    rejected = reject(
        store, proposed.decision_id, proposed.version, actor="reviewer-1",
        now="2026-11-21T11:00:00Z", audit=audit,
    )
    supersede(
        store, rejected.decision_id, rejected.version, actor="analyst",
        replacement_fingerprint="sha256:" + "cd" * 32, now="2026-11-21T12:00:00Z", audit=audit,
    )
    assert [e["event_type"] for e in _events(audit)] == [
        "decision_proposed", "decision_rejected", "decision_superseded",
    ]
    store.close()

    expiring = DecisionRecordStore(tmp_path / "expiring.db")
    payload = draft_record() | {"review_date": "2026-11-22"}
    expiring.append(payload)
    p2 = propose(expiring, "decision-approval-001", 1, actor="analyst",
                 now="2026-11-21T10:00:00Z", audit=audit)
    expire(expiring, p2.decision_id, p2.version, now="2026-11-25T00:00:00Z", audit=audit)
    last = _events(audit)[-1]
    assert last["event_type"] == "decision_expired" and last["reason"] == "review_date_elapsed"
    assert audit.verify()["valid"] is True
    expiring.close(); audit.close()


def test_audit_failure_after_store_write_raises_and_is_visible(tmp_path):
    class BrokenAudit:
        def append(self, event):
            raise OSError("audit disk unavailable")

    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    with pytest.raises(ApprovalTransitionError, match="audit event could not be appended"):
        propose(store, "decision-approval-001", 1, actor="analyst",
                now="2026-11-21T10:00:00Z", audit=BrokenAudit())
    # The stored transition remains visible so the gap can be reconciled.
    assert store.versions("decision-approval-001")[-1].status == "proposed"
    store.close()

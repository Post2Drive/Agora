from __future__ import annotations

import sqlite3

import pytest

from agora.decisions.approval import (
    ApprovalTransitionError,
    approve,
    expire,
    propose,
    reject,
    supersede,
)
from agora.decisions.schema import DecisionRecordError, load_decision_record
from agora.decisions.store import DecisionRecordStore


def draft_record():
    return {
        "decision_id": "decision-approval-001",
        "version": 1,
        "project_scope": {"project_id": "pilot-1"},
        "status": "draft",
        "statement": "Choose a synthetic pilot cohort",
        "alternatives": ["A", "B"],
        "evidence_refs": [
            {"kind": "import", "import_id": "import-001", "dataset_id": "synthetic"},
            {"kind": "run", "run_id": "run-001", "mode": "exploratory"},
        ],
        "rationale": "Evidence is exploratory.",
        "assumptions": ["Synthetic data"],
        "uncertainty": ["Small sample"],
        "outcome_measures": ["observed follow-up"],
        "proposer": "analyst",
        "reviewer": "reviewer-1",
        "created_at": "2026-11-21T00:00:00Z",
        "updated_at": "2026-11-21T00:00:00Z",
        "approval_method": "manual",
        "review_date": "2026-12-01",
    }


def prepared_store(tmp_path):
    store = DecisionRecordStore(tmp_path / "approval.db")
    store.append(draft_record())
    proposed = propose(
        store, "decision-approval-001", 1, actor="analyst",
        now="2026-11-21T10:00:00Z",
    )
    return store, proposed


def approve_args(proposed, **overrides):
    args = {
        "actor": "approver-1",
        "role": "approver",
        "subject": {"subject_id": "approver-1", "project_id": "pilot-1"},
        "expected_fingerprint": proposed.fingerprint,
        "expected_scope": {"project_id": "pilot-1"},
        "expected_evidence_refs": proposed.evidence_refs,
        "now": "2026-11-21T11:00:00Z",
    }
    args.update(overrides)
    return args


def test_happy_path_appends_versions_and_audit_events(tmp_path):
    store, proposed = prepared_store(tmp_path)
    approved = approve(
        store, proposed.decision_id, proposed.version, **approve_args(proposed)
    )
    assert [item.status for item in store.versions(proposed.decision_id)] == [
        "draft", "proposed", "approved"
    ]
    assert approved.approver == "approver-1"
    events = store.approval_events(proposed.decision_id)
    assert [event["transition"] for event in events] == ["proposed", "approved"]
    approval_event = events[-1]
    assert approval_event["actor"] == "approver-1"
    assert approval_event["method"] == "manual"
    assert approval_event["occurred_at"] == approved.updated_at
    assert approval_event["decision_fingerprint"] == approved.fingerprint
    assert approval_event["policy_decision"]["decision"] == "allow"
    store.close()


@pytest.mark.parametrize("role", ["operator", "reader", "reviewer"])
def test_non_approver_roles_cannot_approve(tmp_path, role):
    store, proposed = prepared_store(tmp_path)
    with pytest.raises(PermissionError, match="decision approval denied"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(proposed, role=role),
        )
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    store.close()


def test_stale_fingerprint_is_rejected(tmp_path):
    store, proposed = prepared_store(tmp_path)
    with pytest.raises(ApprovalTransitionError, match="stale decision fingerprint"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(proposed, expected_fingerprint="sha256:stale"),
        )
    store.close()


def test_scope_mismatch_is_rejected_before_approval(tmp_path):
    store, proposed = prepared_store(tmp_path)
    with pytest.raises(ApprovalTransitionError, match="scope"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(proposed, expected_scope={"project_id": "other-project"}),
        )
    with pytest.raises(PermissionError, match="cross_scope"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(
                proposed,
                subject={"subject_id": "approver-1", "project_id": "other-project"},
            ),
        )
    store.close()


def test_evidence_mismatch_is_rejected(tmp_path):
    store, proposed = prepared_store(tmp_path)
    changed_refs = [dict(item) for item in proposed.evidence_refs]
    changed_refs[0]["import_id"] = "import-elsewhere"
    with pytest.raises(ApprovalTransitionError, match="evidence"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(proposed, expected_evidence_refs=changed_refs),
        )
    store.close()


def test_expired_proposal_cannot_be_approved_or_proposed(tmp_path):
    store = DecisionRecordStore(tmp_path / "expired.db")
    expired = draft_record()
    expired["review_date"] = "2026-11-20"
    store.append(expired)
    with pytest.raises(ApprovalTransitionError, match="expired"):
        propose(
            store, "decision-approval-001", 1, actor="analyst",
            now="2026-11-21T10:00:00Z",
        )
    store.close()


def test_proposer_and_reviewer_cannot_approve(tmp_path):
    store, proposed = prepared_store(tmp_path)
    with pytest.raises(ApprovalTransitionError, match="approver must differ"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(
                proposed,
                actor="analyst",
                subject={"subject_id": "analyst", "project_id": "pilot-1"},
            ),
        )
    with pytest.raises(ApprovalTransitionError, match="approver must differ"):
        approve(
            store, proposed.decision_id, proposed.version,
            **approve_args(
                proposed,
                actor="reviewer-1",
                subject={"subject_id": "reviewer-1", "project_id": "pilot-1"},
            ),
        )
    store.close()


def test_store_rejects_approved_record_without_valid_transition(tmp_path):
    store = DecisionRecordStore(tmp_path / "direct-approved.db")
    payload = draft_record()
    payload.update(status="approved", approver="approver-1")
    approved = load_decision_record(payload)
    with pytest.raises(DecisionRecordError, match="valid approval transition"):
        store.append(approved)
    store.close()


def test_reject_and_expiry_are_append_only_transitions(tmp_path):
    rejected_store, proposed = prepared_store(tmp_path)
    rejected = reject(
        rejected_store, proposed.decision_id, proposed.version,
        actor="reviewer-1", now="2026-11-21T12:00:00Z",
    )
    assert rejected.status == "rejected"
    assert [event["transition"] for event in rejected_store.approval_events(proposed.decision_id)] == [
        "proposed", "rejected"
    ]
    rejected_store.close()

    expired_store, proposed = prepared_store(tmp_path / "expiry")
    expired = expire(
        expired_store, proposed.decision_id, proposed.version,
        now="2026-12-02T00:00:00Z",
    )
    assert expired.status == "rejected"
    assert expired_store.approval_events(proposed.decision_id)[-1]["transition"] == "expired"
    expired_store.close()


def test_supersession_appends_a_new_version_and_links_replacement(tmp_path):
    store, proposed = prepared_store(tmp_path)
    superseded = supersede(
        store, proposed.decision_id, proposed.version, actor="analyst",
        replacement_fingerprint="sha256:" + "a" * 64,
        now="2026-11-21T12:00:00Z",
    )
    assert superseded.status == "superseded"
    assert [item.version for item in store.versions(proposed.decision_id)] == [1, 2, 3]
    event = store.approval_events(proposed.decision_id)[-1]
    assert event["transition"] == "superseded"
    assert event["details"]["replacement_fingerprint"] == "sha256:" + "a" * 64
    store.close()


def test_audit_events_cannot_be_updated_or_deleted(tmp_path):
    store, proposed = prepared_store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute(
            "UPDATE decision_approval_events SET actor='tampered' WHERE decision_id=?",
            (proposed.decision_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute(
            "DELETE FROM decision_approval_events WHERE decision_id=?",
            (proposed.decision_id,),
        )
    store.close()

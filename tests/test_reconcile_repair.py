from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from agora import reconcile as rc
from agora.audit_anchor import AnchoredAuditChain, AnchorStore, bootstrap_anchor, verify_anchored
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import propose
from agora.decisions.store import DecisionRecordStore
from agora.principal import SyntheticFixtureAdapter
from agora.reconcile_repair import RepairRefused, apply_repairs, repair_id
from tests.test_decision_approval import draft_record

NOW = "2026-11-21T10:00:00Z"
FAR = datetime(2030, 1, 1, tzinfo=timezone.utc)
ADAPTER = SyntheticFixtureAdapter({
    "approver": {"subject_id": "approver-1", "tenant_id": "t", "project_ids": ["pilot-1"],
                 "roles": ["approver"], "assurance": "HIGH", "expires_at": FAR},
    "operator": {"subject_id": "op-1", "tenant_id": "t", "project_ids": ["pilot-1"],
                 "roles": ["operator"], "assurance": "HIGH", "expires_at": FAR},
    "low": {"subject_id": "approver-2", "tenant_id": "t", "project_ids": ["pilot-1"],
            "roles": ["approver"], "assurance": "LOW", "expires_at": FAR},
    "other": {"subject_id": "approver-3", "tenant_id": "t", "project_ids": ["elsewhere"],
              "roles": ["approver"], "assurance": "HIGH", "expires_at": FAR},
})


def _setup(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "anchor.jsonl", "c1")
    bootstrap_anchor(chain, anchors, performed_by="maint")
    audit = AnchoredAuditChain(chain, anchors)
    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    propose(store, "decision-approval-001", 1, actor="analyst", now=NOW)  # no audit: the gap
    return store, audit


def _head(audit):
    return verify_anchored(audit.chain, audit.anchors)["head_hash"]


def _apply(tmp_path, audit, who="approver", head=None, **kw):
    return apply_repairs(tmp_path / "decisions.db", audit, principal=ADAPTER.issue(who),
                         project_id="pilot-1", expected_audit_head=head or _head(audit), **kw)


def test_repair_appends_missing_event_and_reconcile_becomes_intact(tmp_path):
    store, audit = _setup(tmp_path)
    assert rc.reconcile(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", anchor_path=tmp_path / "anchor.jsonl", chain_id="c1")["counts"]["missing"] == 1
    out = _apply(tmp_path, audit)
    assert out["repaired"] == 1
    report = rc.reconcile(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", anchor_path=tmp_path / "anchor.jsonl", chain_id="c1")
    assert report["intact"] is True and report["counts"]["matched"] == 1
    assert audit.verify()["valid"] is True
    event = json.loads(audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq DESC").fetchone()[0])
    assert event["reason"] == "reconciled_from_store" and event["event_id"] == out["repair_ids"][0]


def test_repair_is_idempotent(tmp_path):
    store, audit = _setup(tmp_path)
    _apply(tmp_path, audit)
    again = _apply(tmp_path, audit)
    assert again["repaired"] == 0
    assert audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1


@pytest.mark.parametrize("who", ["operator", "low", "other"])
def test_unauthorized_principals_write_nothing(tmp_path, who):
    store, audit = _setup(tmp_path)
    with pytest.raises(RepairRefused, match="NOT_AUTHORIZED"):
        _apply(tmp_path, audit, who=who)
    assert audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


def test_missing_principal_is_refused(tmp_path):
    store, audit = _setup(tmp_path)
    with pytest.raises(RepairRefused, match="NOT_AUTHORIZED"):
        apply_repairs(tmp_path / "decisions.db", audit, principal=None, project_id="pilot-1",
                      expected_audit_head=_head(audit))


def test_stale_audit_head_is_refused(tmp_path):
    store, audit = _setup(tmp_path)
    with pytest.raises(RepairRefused, match="STALE_AUDIT_HEAD"):
        _apply(tmp_path, audit, head="ab" * 32)
    assert audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


def test_unanchored_tail_blocks_repair(tmp_path):
    store, audit = _setup(tmp_path)
    audit.chain.append({"event_id": "stray", "event_type": "x", "subject_id": "u", "operation": "import",
                        "decision": "allow"})  # chain advanced, anchor did not
    with pytest.raises(RepairRefused, match="ANCHOR_NOT_CLEAN"):
        apply_repairs(tmp_path / "decisions.db", audit, principal=ADAPTER.issue("approver"),
                      project_id="pilot-1", expected_audit_head="0" * 64)


def test_plain_writer_is_refused(tmp_path):
    store, audit = _setup(tmp_path)
    from agora.audit_anchor import AnchorRequiredError
    with pytest.raises(AnchorRequiredError):
        apply_repairs(tmp_path / "decisions.db", audit.chain, principal=ADAPTER.issue("approver"),
                      project_id="pilot-1", expected_audit_head="0" * 64)


def test_orphan_or_conflict_blocks_all_repairs(tmp_path):
    store, audit = _setup(tmp_path)
    # A mismatching event for the same transition makes this a conflict, not a gap.
    audit.append({"event_id": "wrong", "event_type": "decision_proposed", "subject_id": "someone-else",
                  "operation": "decision_lifecycle", "decision": "allow",
                  "resource_ids": ["decision-approval-001", "version-2"], "decision_fingerprint": "sha256:" + "0" * 64})
    store.append  # keep store open
    before = audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    with pytest.raises(RepairRefused, match="NON_REPAIRABLE_FINDINGS"):
        _apply(tmp_path, audit)
    assert audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == before


def test_broken_chain_blocks_repair(tmp_path):
    store, audit = _setup(tmp_path)
    audit.chain.append({"event_id": "e1", "event_type": "x", "subject_id": "u", "operation": "import", "decision": "allow"})
    audit.anchors.advance(1, audit.chain.verify()["last_hash"])
    audit.chain.db.execute("DROP TRIGGER protect_audit_event_update")
    audit.chain.db.execute("UPDATE audit_events SET event_json=? WHERE seq=1", ('{"event_id":"e1","z":1}',))
    audit.chain.db.commit()
    with pytest.raises(RepairRefused):
        _apply(tmp_path, audit, head="0" * 64)


def test_repair_id_is_deterministic_and_input_sensitive():
    a = repair_id("d", 1, "proposed", "sha256:" + "a" * 64)
    assert a == repair_id("d", 1, "proposed", "sha256:" + "a" * 64)
    assert a != repair_id("d", 2, "proposed", "sha256:" + "a" * 64)


def test_repair_does_not_modify_decision_store(tmp_path):
    store, audit = _setup(tmp_path)
    before = store.db.execute("SELECT COUNT(*) FROM decision_approval_events").fetchone()[0]
    _apply(tmp_path, audit)
    assert store.db.execute("SELECT COUNT(*) FROM decision_approval_events").fetchone()[0] == before

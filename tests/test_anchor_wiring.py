from __future__ import annotations

import pytest

from agora.audit_anchor import (
    AnchorError, AnchorRequiredError, AnchorStore, AnchoredAuditChain, bootstrap_anchor,
    open_anchored_audit, verify_anchored,
)
from agora.audit_chain import AuditChainStore
from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
from agora.tabular import TabularIngestError, ingest_csv
from tests.test_tabular_ingest import schema


def _provision(tmp_path):
    chain_path, anchor_path = tmp_path / "chain.sqlite3", tmp_path / "anchors" / "a.jsonl"
    chain = AuditChainStore(chain_path)
    bootstrap_anchor(chain, AnchorStore(anchor_path, "c1"), performed_by="maint-1")
    chain.close()
    return chain_path, anchor_path


def _deny(operation, resource):
    return {"decision": "deny", "reason": "cross_scope", "subject_id": "op-1",
            "policy_version": "v1", "resource_ids": ["people"]}


def test_factory_yields_anchored_writer_and_closes(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        assert isinstance(writer, AnchoredAuditChain)
    with pytest.raises(Exception):
        writer.chain.db.execute("select 1")  # connection closed


def test_factory_never_bootstraps_missing_anchor(tmp_path):
    with pytest.raises(AnchorRequiredError):
        with open_anchored_audit(tmp_path / "c.sqlite3", tmp_path / "a.jsonl", "c1"):
            pass
    assert not (tmp_path / "a.jsonl").exists()


def test_factory_rejects_same_file_and_unclean_pair(tmp_path):
    with pytest.raises(AnchorError):
        with open_anchored_audit(tmp_path / "x", tmp_path / "x", "c1"):
            pass
    chain_path, anchor_path = _provision(tmp_path)
    chain = AuditChainStore(chain_path)
    chain.append({"event_id": "e1", "event_type": "t", "subject_id": "u", "operation": "import", "decision": "allow"})
    chain.close()  # unanchored tail
    with pytest.raises(AnchorRequiredError):
        with open_anchored_audit(chain_path, anchor_path, "c1"):
            pass


def test_denial_goes_through_anchored_writer(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        with pytest.raises(PolicyEnforcementError, match="cross_scope"):
            enforce_policy(_deny, project=tmp_path / "p", operation="import",
                           resource={"resource_ids": ["people"]}, audit=writer)
        assert writer.verify()["status"] == "anchored_verified"
        assert writer.verify()["sequence"] == 1
    assert not (tmp_path / "p" / "data" / "audit_chain.sqlite3").exists()  # no unanchored fallback


def test_anchor_failure_on_denial_still_denies_and_reports(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        def boom(*a, **k):
            raise OSError("disk")
        writer.anchors.advance = boom
        with pytest.raises(PolicyEnforcementError, match="could not be recorded"):
            enforce_policy(_deny, project=tmp_path / "p", operation="import",
                           resource={"resource_ids": ["people"]}, audit=writer)
        assert writer.verify()["status"] == "unanchored_tail"


def test_ingest_denial_anchored_before_source_read(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        with pytest.raises(TabularIngestError) as exc:
            ingest_csv(tmp_path / "project", tmp_path / "missing.csv", schema(),
                       data_role="context", policy=_deny, audit=writer)
        assert exc.value.code == "POLICY_DENIED"
        assert writer.verify()["status"] == "anchored_verified"
        assert writer.verify()["sequence"] == 1
    assert not (tmp_path / "project" / "data" / "audit_chain.sqlite3").exists()


# --- Stage B/C: decision lifecycle and outcomes through the anchored writer ---
import json as _json

from agora.decisions.approval import ApprovalTransitionError, approve, propose
from agora.decisions.outcomes import OutcomeError, _record_outcome as record_outcome, _review_outcome as review_outcome
from agora.decisions.store import DecisionRecordStore
from tests.test_decision_approval import approve_args, draft_record
from tests.test_decision_outcomes import approved_store, outcome_args, review_args


def _types(chain):
    return [_json.loads(r[0])["event_type"] for r in chain.db.execute(
        "SELECT event_json FROM audit_events ORDER BY rowid")]


def test_lifecycle_is_anchored_through_writer(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    store = DecisionRecordStore(tmp_path / "d.db")
    store.append(draft_record())
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        p = propose(store, "decision-approval-001", 1, actor="analyst",
                    now="2026-11-21T10:00:00Z", audit=writer)
        approve(store, p.decision_id, p.version, audit=writer, **approve_args(p))
        assert writer.verify()["status"] == "anchored_verified"
        assert _types(writer.chain) == ["decision_proposed", "decision_approved"]
        assert AnchorStore(anchor_path, "c1").latest()["sequence"] == 2
    store.close()


def test_lifecycle_anchor_failure_is_visible_and_blocks_next_append(tmp_path, monkeypatch):
    chain_path, anchor_path = _provision(tmp_path)
    store = DecisionRecordStore(tmp_path / "d.db")
    store.append(draft_record())
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(writer.anchors, "advance", boom)
        with pytest.raises(ApprovalTransitionError):
            propose(store, "decision-approval-001", 1, actor="analyst",
                    now="2026-11-21T10:00:00Z", audit=writer)
        monkeypatch.undo()
        # chain event persisted but unanchored: next protected append is refused
        with pytest.raises(AnchorRequiredError):
            writer.append({"event_id": "x1", "event_type": "t", "subject_id": "u",
                           "operation": "import", "decision": "allow"})
    store.close()


def test_outcome_record_and_review_are_anchored(tmp_path):
    chain_path, anchor_path = _provision(tmp_path)
    _, store, approved = approved_store(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        out = record_outcome(store, audit=writer, **outcome_args(approved))
        review_outcome(store, approved.decision_id, approved.version, out["outcome_id"],
                       audit=writer, **review_args())
        assert writer.verify()["status"] == "anchored_verified"
        assert _types(writer.chain)[-2:] == ["decision_outcome_recorded", "decision_outcome_reviewed"]
        

def test_outcome_anchor_failure_is_visible_row_remains(tmp_path, monkeypatch):
    chain_path, anchor_path = _provision(tmp_path)
    _, store, approved = approved_store(tmp_path)
    with open_anchored_audit(chain_path, anchor_path, "c1") as writer:
        monkeypatch.setattr(writer.anchors, "advance", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OutcomeError, match="could not be appended"):
            record_outcome(store, audit=writer, **outcome_args(approved, outcome_id="o-1"))
        assert store.get(approved.decision_id, approved.version, "o-1")["outcome_id"] == "o-1"

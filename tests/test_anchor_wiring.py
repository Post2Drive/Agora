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

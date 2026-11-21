from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agora.audit_anchor import (
    AnchorRequiredError, AnchorStore, AnchoredAuditChain, bootstrap_anchor, open_anchored_audit,
    verify_anchored,
)
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import (
    ApprovalTransitionError, approve, approve_as, expire, propose, reject, supersede,
)
from agora.decisions.outcomes import (
    DecisionOutcomeStore, OutcomeError, record_outcome_as, review_outcome_as,
)
from agora.decisions.store import DecisionRecordStore
from agora.principal import SyntheticFixtureAdapter
from tests.test_decision_approval import approve_args, draft_record
from tests.test_decision_outcomes import outcome_args

EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(sid, roles):
    return {"subject_id": sid, "tenant_id": "t1", "project_ids": ["pilot-1"], "roles": roles,
            "assurance": "HIGH", "expires_at": EXP}


ADAPTER = SyntheticFixtureAdapter({"appr": _fx("approver-1", ["approver"]),
                                   "op": _fx("recorder-1", ["operator"]),
                                   "rev": _fx("reviewer-9", ["reviewer"])})


def _provision(tmp_path):
    cp, ap = tmp_path / "chain.sqlite3", tmp_path / "a" / "anchor.jsonl"
    chain = AuditChainStore(cp)
    bootstrap_anchor(chain, AnchorStore(ap, "c1"), performed_by="maint-1")
    chain.close()
    return cp, ap


def _types(chain_path):
    c = AuditChainStore(chain_path)
    out = [json.loads(r[0])["event_type"] for r in c.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]
    c.close()
    return out


@pytest.mark.protected_defaults
def test_every_decision_lifecycle_transition_is_anchored(tmp_path):
    cp, ap = _provision(tmp_path)
    with open_anchored_audit(cp, ap, "c1") as w:
        store = DecisionRecordStore(tmp_path / "d.db")
        store.append(draft_record())
        p = propose(store, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z", audit=w)
        a = approve_as(store, p.decision_id, p.version, principal=ADAPTER.issue("appr"),
                       expected_fingerprint=p.fingerprint, expected_scope={"project_id": "pilot-1"},
                       expected_evidence_refs=p.evidence_refs, now="2026-11-21T11:00:00Z",
                       audit=w)
        supersede(store, a.decision_id, a.version, actor="analyst",
                  replacement_fingerprint="sha256:" + "a" * 64, now="2026-11-21T12:00:00Z", audit=w)
        assert w.verify()["valid"] is True
    types = _types(cp)
    assert types[-3:] == ["decision_proposed", "decision_approved", "decision_superseded"]
    store.close()


def test_reject_and_expire_are_anchored(tmp_path):
    cp, ap = _provision(tmp_path)
    with open_anchored_audit(cp, ap, "c1") as w:
        s1 = DecisionRecordStore(tmp_path / "d1.db"); s1.append(draft_record())
        p = propose(s1, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z", audit=w)
        reject(s1, p.decision_id, p.version, actor="reviewer-1", now="2026-11-21T12:00:00Z", audit=w)
        s2 = DecisionRecordStore(tmp_path / "d2.db"); s2.append(draft_record())
        p2 = propose(s2, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z", audit=w)
        expire(s2, p2.decision_id, p2.version, now="2026-12-02T00:00:00Z", audit=w)
        assert w.verify()["valid"] is True
    assert _types(cp).count("decision_rejected") == 1 and _types(cp).count("decision_expired") == 1


@pytest.mark.protected_defaults
def test_protected_approval_requires_anchored_writer_before_any_change(tmp_path):
    cp, _ = _provision(tmp_path)
    store = DecisionRecordStore(tmp_path / "d.db"); store.append(draft_record())
    p = propose(store, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
    plain = AuditChainStore(cp)
    for bad in (None, plain):
        with pytest.raises(AnchorRequiredError):
            approve_as(store, p.decision_id, p.version, principal=ADAPTER.issue("appr"),
                       expected_fingerprint=p.fingerprint, expected_scope={"project_id": "pilot-1"},
                       expected_evidence_refs=p.evidence_refs, now="2026-11-21T11:00:00Z",
                       audit=bad)
    assert store.versions(p.decision_id)[-1].status == "proposed"
    plain.close(); store.close()


def test_anchor_failure_surfaces_with_committed_transition(tmp_path):
    cp, ap = _provision(tmp_path)
    with open_anchored_audit(cp, ap, "c1") as w:
        w.anchors.advance = lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
        store = DecisionRecordStore(tmp_path / "d.db"); store.append(draft_record())
        with pytest.raises(ApprovalTransitionError, match="stored but its audit"):
            propose(store, "decision-approval-001", 1, actor="analyst",
                    now="2026-11-21T10:00:00Z", audit=w)
        assert store.versions("decision-approval-001")[-1].status == "proposed"
    store.close()


def _approved(tmp_path):
    ds = DecisionRecordStore(tmp_path / "dd.db"); ds.append(draft_record())
    p = propose(ds, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
    a = approve(ds, p.decision_id, p.version, **approve_args(p))
    return ds, DecisionOutcomeStore(ds), a


def _oargs(a):
    x = outcome_args(a)
    for k in ("recorder", "role", "subject"):
        x.pop(k)
    return x


@pytest.mark.protected_defaults
def test_outcome_record_review_are_anchored_and_values_not_in_audit(tmp_path):
    cp, ap = _provision(tmp_path)
    _, os_, a = _approved(tmp_path)
    with open_anchored_audit(cp, ap, "c1") as w:
        out = record_outcome_as(os_, principal=ADAPTER.issue("op"), audit=w,
                                **_oargs(a) | {"observed_value": 987654})
        review_outcome_as(os_, a.decision_id, a.version, out["outcome_id"], principal=ADAPTER.issue("rev"),
                          audit=w, new_state="reviewed",
                          rationale_code="source_checked", now="2026-11-27T00:00:00Z")
        assert w.verify()["valid"] is True
    assert _types(cp)[-2:] == ["decision_outcome_recorded", "decision_outcome_reviewed"]
    assert "987654" not in open(cp, "rb").read().decode("latin1")


@pytest.mark.protected_defaults
def test_protected_outcome_requires_anchored_writer_and_stores_nothing(tmp_path):
    _, os_, a = _approved(tmp_path)
    with pytest.raises(AnchorRequiredError):
        record_outcome_as(os_, principal=ADAPTER.issue("op"), audit=None, **_oargs(a))
    assert os_.outcomes(a.decision_id, a.version) == []


@pytest.mark.protected_defaults
def test_outcome_anchor_failure_is_visible_and_row_stays_stored(tmp_path):
    cp, ap = _provision(tmp_path)
    _, os_, a = _approved(tmp_path)
    with open_anchored_audit(cp, ap, "c1") as w:
        w.anchors.advance = lambda *a_, **k: (_ for _ in ()).throw(OSError("disk"))
        with pytest.raises(OutcomeError, match="stored but its audit"):
            record_outcome_as(os_, principal=ADAPTER.issue("op"), audit=w, **_oargs(a))
    assert len(os_.outcomes(a.decision_id, a.version)) == 1


def test_protected_review_requires_anchored_writer(tmp_path, monkeypatch):
    from agora import protection
    cp, ap = _provision(tmp_path)
    _, os_, a = _approved(tmp_path)
    out = record_outcome_as(os_, principal=ADAPTER.issue("op"), **_oargs(a))  # relaxed setup
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    with pytest.raises(AnchorRequiredError):
        review_outcome_as(os_, a.decision_id, a.version, out["outcome_id"], principal=ADAPTER.issue("rev"),
                          audit=None, new_state="reviewed",
                          rationale_code="source_checked", now="2026-11-27T00:00:00Z")
    assert os_.state(a.decision_id, a.version, out["outcome_id"]) != "reviewed"

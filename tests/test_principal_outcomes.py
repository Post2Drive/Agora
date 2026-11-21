from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from agora.audit_chain import AuditChainStore
from agora.decisions.outcomes import (
    OutcomeError, OutcomePermissionError, record_outcome_as, review_outcome_as,
)
from agora.principal import SyntheticFixtureAdapter
from tests.test_decision_outcomes import approved_store, outcome_args

EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(sid, roles, **kw):
    base = {"subject_id": sid, "tenant_id": "t1", "project_ids": ["pilot-1"], "roles": roles,
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


ADAPTER = SyntheticFixtureAdapter({
    "op": _fx("recorder-1", ["operator"]),
    "rev": _fx("reviewer-9", ["reviewer"]),
    "both": _fx("recorder-1", ["operator", "reviewer"]),
    "reader": _fx("reader-1", ["reader"]),
    "other": _fx("op-2", ["operator"], project_ids=["other"]),
    "expired": _fx("op-3", ["operator"], expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
})


def _rec_args(approved):
    a = outcome_args(approved)
    for k in ("recorder", "role", "subject"):
        a.pop(k)
    return a


REV = dict(new_state="reviewed", rationale_code="source_checked", now="2026-11-27T00:00:00Z")


def test_operator_principal_records_and_reviewer_principal_reviews(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved))
    assert out["recorder"] == "recorder-1"
    r = review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                          principal=ADAPTER.issue("rev"), **REV)
    assert r["reviewer"] == "reviewer-9" and r["new_state"] == "reviewed"


def test_no_caller_authority_parameters_accepted(tmp_path):
    _, store, approved = approved_store(tmp_path)
    for banned in ("recorder", "role", "subject"):
        with pytest.raises(OutcomeError):
            record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved), **{banned: "x"})
    assert "role" not in inspect.signature(record_outcome_as).parameters


@pytest.mark.parametrize("key", ["reader", "other", "expired", None])
def test_record_denied_for_bad_principal_without_store_change(tmp_path, key):
    _, store, approved = approved_store(tmp_path)
    p = ADAPTER.issue(key) if key else None
    with pytest.raises(OutcomePermissionError):
        record_outcome_as(store, principal=p, **_rec_args(approved))
    assert store.outcomes(approved.decision_id, approved.version) == []


def test_reviewer_role_cannot_record_and_operator_cannot_review(tmp_path):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomePermissionError):
        record_outcome_as(store, principal=ADAPTER.issue("rev"), **_rec_args(approved))
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved))
    with pytest.raises(OutcomePermissionError):
        review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                          principal=ADAPTER.issue("op"), **REV)


def test_dual_role_principal_uses_required_role_and_cannot_self_review(tmp_path):
    _, store, approved = approved_store(tmp_path)
    p = ADAPTER.issue("both")
    out = record_outcome_as(store, principal=p, **_rec_args(approved))
    with pytest.raises(OutcomeError, match="differ"):
        review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                          principal=p, **REV)


def test_denial_is_audited_with_identifiers_only(tmp_path):
    import json
    _, store, approved = approved_store(tmp_path)
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    with pytest.raises(OutcomePermissionError):
        record_outcome_as(store, principal=ADAPTER.issue("reader"), audit=audit, **_rec_args(approved))
    events = [json.loads(r[0]) for r in audit.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]
    assert [e["event_type"] for e in events] == ["decision_outcome_denied"]
    assert events[0]["subject_id"] == "reader-1" and events[0]["decision"] == "deny"
    assert "people" not in json.dumps(events) and audit.verify()["valid"] is True
    audit.close()


# --- slice 3d: caller resource ignored; anchored writer required when asked ---
import agora.decisions.outcomes as outcomes_mod
from agora.audit_anchor import AnchorRequiredError

FORGED = [
    {"source_sensitivity": "public"}, {"sensitivity": "public"},
    {"target_sensitivity": "public"}, {"source_sensitivity": "sensitive"},
    {"purpose": "marketing", "retention": "forever", "project_id": "other"},
]


@pytest.fixture
def seen(monkeypatch):
    captured = []
    real = outcomes_mod.decide_principal

    def spy(principal, op, resource, **kw):
        captured.append(dict(resource))
        return real(principal, op, resource, **kw)
    monkeypatch.setattr(outcomes_mod, "decide_principal", spy)
    return captured


@pytest.mark.parametrize("forged", FORGED)
def test_record_outcome_as_ignores_caller_resource(tmp_path, seen, forged):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), resource=forged, **_rec_args(approved))
    assert out["recorder"] == "recorder-1"
    assert seen[-1]["source_sensitivity"] == "internal"
    assert set(seen[-1]) == set(approved.project_scope) | {"resource_ids", "source_sensitivity"}
    assert not {"target_sensitivity", "purpose", "retention", "sensitivity"} & set(seen[-1])


@pytest.mark.parametrize("forged", FORGED)
def test_review_outcome_as_ignores_caller_resource(tmp_path, seen, forged):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved))
    r = review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                          principal=ADAPTER.issue("rev"), resource=forged, **REV)
    assert r["new_state"] == "reviewed"
    assert seen[-1]["source_sensitivity"] == "internal"
    assert not {"target_sensitivity", "purpose", "retention", "sensitivity"} & set(seen[-1])
    assert seen[-1]["project_id"] == approved.project_scope["project_id"]


def test_outcome_as_require_anchored_fails_closed_without_state_change(tmp_path):
    _, store, approved = approved_store(tmp_path)
    plain = AuditChainStore(tmp_path / "audit.sqlite3")
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            record_outcome_as(store, principal=ADAPTER.issue("op"), audit=audit,
                              require_anchored=True, **_rec_args(approved))
    assert store.outcomes(approved.decision_id, approved.version) == []
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved))
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                              principal=ADAPTER.issue("rev"), audit=audit,
                              require_anchored=True, **REV)
    assert store.reviews(approved.decision_id, approved.version, out["outcome_id"]) == []
    assert [e for e in plain.db.execute("SELECT 1 FROM audit_events")] == []
    plain.close()

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from agora.audit_chain import AuditChainStore
from agora.decisions.approval import approve, approve_as, propose
from agora.decisions.permissions import DecisionPermissionError
from agora.decisions.store import DecisionRecordStore
from agora.principal import Assurance, IdentityError, Principal, SyntheticFixtureAdapter, decide_principal
from tests.test_decision_approval import draft_record

NOW = datetime(2026, 11, 21, 11, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)


def _fx(**kw):
    base = {"subject_id": "approver-1", "tenant_id": "t1", "project_ids": ["pilot-1"],
            "roles": ["approver"], "assurance": "HIGH", "expires_at": LATER}
    base.update(kw)
    return base


def _adapter(**fixtures):
    table = {"approver": _fx(), "ordinary": _fx(subject_id="user-1", roles=["reader"]),
             "expired": _fx(expires_at=NOW - timedelta(seconds=1)),
             "low": _fx(assurance="LOW"), "other-project": _fx(project_ids=["other"])}
    table.update(fixtures)
    return SyntheticFixtureAdapter(table)


RES = {"project_id": "pilot-1", "source_sensitivity": "internal", "resource_ids": ["d1"]}


def _decide(principal, op="decision_approval", res=RES):
    return decide_principal(principal, op, res, now=NOW)


def test_valid_fixture_maps_exact_fields():
    p = _adapter().issue("approver")
    assert (p.subject_id, p.tenant_id, p.project_ids, p.roles, p.assurance, p.issuer) == (
        "approver-1", "t1", frozenset({"pilot-1"}), frozenset({"approver"}), Assurance.HIGH,
        "synthetic-fixture-issuer")
    decision, role = _decide(p)
    assert decision["decision"] == "allow" and role == "approver"
    with pytest.raises(Exception):
        p.roles = frozenset({"operator"})  # immutable


def test_ordinary_user_cannot_approve_and_no_role_parameter_exists():
    decision, role = _decide(_adapter().issue("ordinary"))
    assert decision["decision"] == "deny" and role is None
    import inspect
    assert "role" not in inspect.signature(approve_as).parameters


@pytest.mark.parametrize("bad", [{"roles": ["superuser"]}, {"roles": []}, {"subject_id": " "},
                                 {"project_ids": [""]}, {"assurance": "GOD"}])
def test_unknown_or_malformed_fixture_rejected(bad):
    adapter = _adapter(bad=_fx(**bad))
    with pytest.raises((IdentityError, KeyError)):
        adapter.issue("bad")


def test_unknown_fixture_and_production_adapter_refused():
    with pytest.raises(IdentityError):
        _adapter().issue("nobody")
    with pytest.raises(IdentityError, match="production"):
        SyntheticFixtureAdapter({}, production=True)


def test_expired_missing_and_untrusted_issuer_fail_closed():
    assert _decide(_adapter().issue("expired"))[0]["reason"] == "principal_expired"
    assert _decide(None)[0]["reason"] == "principal_missing"
    p = _adapter().issue("approver")
    d, role = decide_principal(p, "decision_approval", RES, now=NOW, trusted_issuers=frozenset({"other"}))
    assert d["reason"] == "issuer_untrusted" and role is None


def test_scope_tenant_and_assurance_enforced():
    assert _decide(_adapter().issue("other-project"))[0]["reason"] == "cross_scope"
    assert _decide(_adapter().issue("approver"), res=RES | {"tenant_id": "t2"})[0]["reason"] == "cross_tenant"
    assert _decide(_adapter().issue("low"))[0]["reason"] == "assurance_insufficient"
    empty = Principal("u", "t1", frozenset(), frozenset({"approver"}), Assurance.HIGH,
                      "synthetic-fixture-issuer", LATER)
    assert _decide(empty)[0]["reason"] == "cross_scope"  # empty scope is not a wildcard
    assert _decide(_adapter().issue("approver"), res={"source_sensitivity": "internal"})[0]["reason"] == "scope_missing"


def _setup(tmp_path):
    store = DecisionRecordStore(tmp_path / "d.db")
    store.append(draft_record())
    proposed = propose(store, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
    args = dict(expected_fingerprint=proposed.fingerprint, expected_scope={"project_id": "pilot-1"},
                expected_evidence_refs=proposed.evidence_refs, now="2026-11-21T11:00:00Z")
    return store, proposed, args


def test_approve_as_approves_with_principal_and_audits_without_leakage(tmp_path):
    audit = AuditChainStore(tmp_path / "a.sqlite3")
    store, proposed, args = _setup(tmp_path)
    p = _adapter().issue("approver")
    out = approve_as(store, proposed.decision_id, proposed.version, principal=p, audit=audit, **args)
    assert out.status == "approved" and out.approver == "approver-1"
    assert audit.verify()["valid"] is True
    store.close(); audit.close()


@pytest.mark.parametrize("key,reason", [("ordinary", "role_not_permitted"), ("expired", "principal_expired"),
                                        ("low", "assurance_insufficient"), ("other-project", "cross_scope")])
def test_approve_as_denials_change_nothing_and_are_audited(tmp_path, key, reason):
    audit = AuditChainStore(tmp_path / "a.sqlite3")
    store, proposed, args = _setup(tmp_path)
    args["now"] = NOW  # approve_as derives expiry from this clock
    with pytest.raises(DecisionPermissionError):
        approve_as(store, proposed.decision_id, proposed.version, principal=_adapter().issue(key),
                   audit=audit, **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    events = [json.loads(r[0]) for r in audit.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]
    assert events[-1]["event_type"] == "decision_approval_denied" and events[-1]["reason"] == reason
    assert audit.verify()["valid"] is True
    store.close(); audit.close()


def test_missing_principal_denied_and_proposer_cannot_self_approve(tmp_path):
    store, proposed, args = _setup(tmp_path)
    with pytest.raises(DecisionPermissionError):
        approve_as(store, proposed.decision_id, proposed.version, principal=None, **args)
    proposer = _adapter(self=_fx(subject_id="analyst")).issue("self")
    with pytest.raises(Exception, match="differ"):
        approve_as(store, proposed.decision_id, proposed.version, principal=proposer, **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    store.close()


def test_stale_version_remains_denied(tmp_path):
    store, proposed, args = _setup(tmp_path)
    with pytest.raises(Exception, match="stale|version"):
        approve_as(store, proposed.decision_id, 99, principal=_adapter().issue("approver"), **args)
    store.close()

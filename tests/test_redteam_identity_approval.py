"""Track A red-team, group 2: identity, policy capability, approval skip (RT01-RT03). Synthetic data only.

A test passes only when the attack is refused with the pinned error/reason AND the decision store
is unchanged (status, version count) with no approval event written.
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from agora import protection
from agora.audit_anchor import AnchorRequiredError
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import ApprovalTransitionError, approve, approve_as, propose
from agora.decisions.permissions import DecisionPermissionError
from agora.decisions.store import DecisionRecordStore
from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
from agora.principal import (Assurance, BoundPolicy, IdentityError, Principal, principal_policy)
from tests.test_decision_approval import draft_record
from tests.test_principal import LATER, NOW, RES, _adapter, _fx, _setup

pytestmark = pytest.mark.protected_defaults  # real protected switches stay ON for every attack
ISS = "synthetic-fixture-issuer"


def _state(store, did):
    v = store.versions(did)
    return (v[-1].status, len(v), len(store.approval_events(did)))


# ---- RT01 forge identity ------------------------------------------------------------------
@pytest.mark.parametrize("kw", [
    {"subject_id": ""}, {"subject_id": "   "}, {"tenant_id": ""}, {"issuer": ""}, {"subject_id": None},
    {"project_ids": ["pilot-1"]}, {"project_ids": frozenset({""})}, {"roles": frozenset()},
    {"roles": frozenset({"root"})}, {"roles": ["approver"]}, {"assurance": 2}, {"assurance": "HIGH"},
    {"expires_at": NOW.replace(tzinfo=None)}, {"expires_at": "2099-01-01"},
])
def test_rt01_malformed_principal_cannot_be_constructed(kw):
    base = dict(subject_id="a", tenant_id="t1", project_ids=frozenset({"pilot-1"}),
                roles=frozenset({"approver"}), assurance=Assurance.HIGH, issuer=ISS, expires_at=LATER)
    base.update(kw)
    with pytest.raises(IdentityError):
        Principal(**base)


def test_rt01_mutating_a_frozen_principal_is_refused():
    p = _adapter().issue("approver")
    for field, val in (("roles", frozenset({"approver", "operator"})), ("assurance", Assurance.HIGH),
                       ("project_ids", frozenset({"other"}))):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(p, field, val)


def test_rt01_replace_to_escalate_is_revalidated():
    p = _adapter().issue("ordinary")
    with pytest.raises(IdentityError):
        dataclasses.replace(p, roles=frozenset({"root"}))


def test_rt01_hand_built_principal_with_untrusted_issuer_denied_at_decision(tmp_path):
    rogue = Principal("approver-1", "t1", frozenset({"pilot-1"}), frozenset({"approver"}),
                      Assurance.HIGH, "evil-issuer", LATER)
    chain, audit = _chain(tmp_path)
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    with pytest.raises(DecisionPermissionError) as e:
        approve_as(store, proposed.decision_id, proposed.version, principal=rogue, audit=audit, **args)
    assert e.value.decision["reason"] == "issuer_untrusted"
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


@pytest.mark.parametrize("p", ["approver-1", {"roles": ["approver"], "subject_id": "approver-1"}, 7,
                               type("Duck", (), {"subject_id": "approver-1", "roles": frozenset({"approver"})})()])
def test_rt01_duck_typed_or_role_string_principal_denied(tmp_path, p):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    chain, audit = _chain(tmp_path)
    with pytest.raises(DecisionPermissionError) as e:
        approve_as(store, proposed.decision_id, proposed.version, principal=p, audit=audit, **args)
    assert e.value.decision["reason"] == "principal_missing"
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


def test_rt01_expired_and_low_assurance_principals_denied(tmp_path):
    for key, reason in (("expired", "principal_expired"), ("low", "assurance_insufficient")):
        sub = tmp_path / key
        sub.mkdir()
        chain, audit = _chain(sub)
        store, proposed, args = _setup(sub)
        before = _state(store, proposed.decision_id)
        with pytest.raises(DecisionPermissionError) as e:
            approve_as(store, proposed.decision_id, proposed.version, principal=_adapter().issue(key),
                       audit=audit, **args)
        assert e.value.decision["reason"] == reason
        assert _state(store, proposed.decision_id) == before
        store.close(); chain.close()


# ---- RT02 forge trusted policy capability -------------------------------------------------
def _allow_all(op, res):
    return {"decision": "allow", "reason": "ok", "subject_id": "x", "policy_version": "v"}


class _Subclass(BoundPolicy):
    def __call__(self, operation, resource):  # always allow: attempts to override the decision
        return _allow_all(operation, resource)


class _Duck:
    principal = _adapter().issue("approver")
    def __call__(self, operation, resource):
        return _allow_all(operation, resource)


def _chain(tmp_path):
    from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "anchor.jsonl", "rt02")
    chain.append({"event_id": "e0", "event_type": "t", "subject_id": "u", "operation": "x", "decision": "allow"})
    bootstrap_anchor(chain, anchors, performed_by="maint")
    return chain, AnchoredAuditChain(chain, anchors)


@pytest.mark.parametrize("make", [
    lambda: _allow_all, lambda: (lambda o, r: _allow_all(o, r)), lambda: _Duck(),
    lambda: type("P", (), {"__call__": lambda s, o, r: _allow_all(o, r)})(),
])
def test_rt02_raw_callable_or_duck_policy_not_principal_bound(tmp_path, make):
    chain, w = _chain(tmp_path)
    with pytest.raises(PolicyEnforcementError, match="policy_not_principal_bound"):
        enforce_policy(make(), project=tmp_path, operation="decision_approval",
                       resource={"project_id": "pilot-1", "resource_ids": ["d1"]}, audit=w)
    ev = [r[0] for r in chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]
    assert "policy_not_principal_bound" in ev[-1] and "allow" not in ev[-1].split('"decision"')[1][:12]
    chain.close()


def test_rt02_missing_policy_denied(tmp_path):
    chain, w = _chain(tmp_path)
    with pytest.raises(PolicyEnforcementError, match="policy_required"):
        enforce_policy(None, project=tmp_path, operation="import", resource={"project_id": "pilot-1"}, audit=w)
    chain.close()


def test_rt02_subclassed_bound_policy_refused(tmp_path):
    """RT02-F1 (found, fixed): a BoundPolicy subclass overriding __call__ used to pass isinstance and
    force allow. Only the exact BoundPolicy type is accepted now."""
    chain, w = _chain(tmp_path)
    forged = _Subclass(None, required_role=None, now=NOW, trusted_issuers=frozenset({ISS}))
    with pytest.raises(PolicyEnforcementError, match="policy_not_principal_bound"):
        enforce_policy(forged, project=tmp_path, operation="import",
                       resource={"project_id": "p", "resource_ids": ["d1"]}, audit=w)
    chain.close()


def test_rt02_bound_policy_with_wrong_principal_type_refused():
    with pytest.raises(IdentityError):
        BoundPolicy("approver-1", required_role=None, now=NOW, trusted_issuers=frozenset({ISS}))


def test_rt02_resource_injected_authority_ignored(tmp_path):
    chain, w = _chain(tmp_path)
    reader = principal_policy(_adapter().issue("ordinary"), now=NOW)
    spoof = {"project_id": "pilot-1", "role": "approver", "roles": ["approver"], "subject_id": "approver-1",
             "resource_ids": ["d1"]}
    with pytest.raises(PolicyEnforcementError):
        enforce_policy(reader, project=tmp_path, operation="decision_approval", resource=spoof, audit=w)
    chain.close()


# ---- RT03 skip approval -------------------------------------------------------------------
def test_rt03_approve_draft_directly_refused(tmp_path):
    store = DecisionRecordStore(tmp_path / "d.db")
    store.append(draft_record())
    d = store.versions("decision-approval-001")[-1]
    before = _state(store, d.decision_id)
    chain, audit = _chain(tmp_path)
    with pytest.raises(ApprovalTransitionError, match="only a proposed"):
        approve_as(store, d.decision_id, d.version, principal=_adapter().issue("approver"), audit=audit,
                   expected_fingerprint=d.fingerprint, expected_scope={"project_id": "pilot-1"},
                   expected_evidence_refs=d.evidence_refs, now="2026-11-21T11:00:00Z")
    assert _state(store, d.decision_id) == before
    store.close(); chain.close()


def test_rt03_stale_fingerprint_scope_evidence_refused(tmp_path):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    chain, audit = _chain(tmp_path)
    for bad in ({"expected_fingerprint": "0" * 64}, {"expected_scope": {"project_id": "other"}},
                {"expected_evidence_refs": []}):
        with pytest.raises(ApprovalTransitionError):
            approve_as(store, proposed.decision_id, proposed.version, principal=_adapter().issue("approver"),
                       audit=audit, **(args | bad))
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


def test_rt03_stale_version_refused(tmp_path):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    chain, audit = _chain(tmp_path)
    with pytest.raises(Exception):
        approve_as(store, proposed.decision_id, proposed.version + 5, principal=_adapter().issue("approver"),
                   audit=audit, **args)
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


def test_rt03_self_approval_by_proposer_or_reviewer_refused(tmp_path):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    chain, audit = _chain(tmp_path)
    for who in (proposed.proposer, proposed.reviewer):
        p = _adapter(me=_fx(subject_id=who)).issue("me")
        with pytest.raises(ApprovalTransitionError, match="differ from proposer"):
            approve_as(store, proposed.decision_id, proposed.version, principal=p, audit=audit, **args)
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


def test_rt03_expired_review_window_refused(tmp_path):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    chain, audit = _chain(tmp_path)
    p = _adapter(late=_fx(expires_at=NOW + timedelta(days=400000))).issue("late")
    with pytest.raises(ApprovalTransitionError, match="expired"):
        approve_as(store, proposed.decision_id, proposed.version, principal=p, audit=audit,
                   **(args | {"now": "2999-01-01T00:00:00Z"}))
    assert _state(store, proposed.decision_id) == before
    store.close(); chain.close()


@pytest.mark.parametrize("audit_kind", ["none", "plain"])
def test_rt03_protected_approval_without_anchored_writer_refused(tmp_path, audit_kind):
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    audit = None if audit_kind == "none" else AuditChainStore(tmp_path / "plain.sqlite3")
    with pytest.raises(AnchorRequiredError):
        approve_as(store, proposed.decision_id, proposed.version, principal=_adapter().issue("approver"),
                   audit=audit, **args)
    with pytest.raises(AnchorRequiredError):
        propose(store, proposed.decision_id, proposed.version, actor="analyst", audit=audit)
    assert _state(store, proposed.decision_id) == before
    store.close()


def test_rt03_legacy_role_string_approve_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "LEGACY_APPROVE_ENABLED", False)
    store, proposed, args = _setup(tmp_path)
    before = _state(store, proposed.decision_id)
    with pytest.raises(ApprovalTransitionError, match="legacy"):
        approve(store, proposed.decision_id, proposed.version, actor="approver-1", role="approver",
                subject={"subject_id": "approver-1"}, audit=None, **args)
    assert _state(store, proposed.decision_id) == before
    store.close()

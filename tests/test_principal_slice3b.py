"""Slice 3b: principal-native approval gate (authority only from the Principal)."""
from __future__ import annotations

import json

import pytest

from agora.audit_anchor import AnchorRequiredError
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import ApprovalTransitionError, approve_as
from agora.decisions.permissions import (
    DecisionPermissionError, authorize_decision_approval_principal,
)
from agora.principal import Assurance, Principal

from tests.test_principal import LATER, NOW, RES, _adapter, _fx, _setup


def _events(audit):
    return [json.loads(r[0]) for r in audit.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]


def test_gate_requires_approver_role_even_when_other_roles_would_allow():
    # reader+operator principal must not pass; approver-only role is required.
    p = _adapter(multi=_fx(subject_id="m-1", roles=["reader", "operator"])).issue("multi")
    with pytest.raises(DecisionPermissionError) as e:
        authorize_decision_approval_principal(p, RES, now=NOW)
    assert e.value.decision["reason"] == "role_not_permitted"


def test_gate_allows_approver_among_many_roles():
    p = _adapter(multi=_fx(subject_id="m-2", roles=["reader", "approver"])).issue("multi")
    decision, role = authorize_decision_approval_principal(p, RES, now=NOW)
    assert decision["decision"] == "allow" and role == "approver"


@pytest.mark.parametrize("p", [None, "approver-1", {"roles": ["approver"]}])
def test_gate_denies_missing_or_non_principal(p):
    with pytest.raises(DecisionPermissionError) as e:
        authorize_decision_approval_principal(p, RES, now=NOW)
    assert e.value.decision["reason"] == "principal_missing"


def test_gate_denies_untrusted_issuer_and_empty_scope():
    rogue = Principal("approver-1", "t1", frozenset({"pilot-1"}), frozenset({"approver"}),
                      Assurance.HIGH, "rogue-issuer", LATER)
    with pytest.raises(DecisionPermissionError) as e:
        authorize_decision_approval_principal(rogue, RES, now=NOW)
    assert e.value.decision["reason"] == "issuer_untrusted"
    ok = _adapter().issue("approver")
    for res in ({}, {"project_id": ""}, RES | {"tenant_id": "other-tenant"}):
        with pytest.raises(DecisionPermissionError):
            authorize_decision_approval_principal(ok, res, now=NOW)


def test_resource_injected_role_and_subject_cannot_grant_authority(tmp_path):
    audit = AuditChainStore(tmp_path / "a.sqlite3")
    store, proposed, args = _setup(tmp_path)
    args["now"] = NOW
    reader = _adapter().issue("ordinary")  # roles: reader only
    spoof = {"role": "approver", "roles": ["approver"], "subject_id": "approver-1", "actor": "approver-1"}
    with pytest.raises(DecisionPermissionError):
        approve_as(store, proposed.decision_id, proposed.version, principal=reader,
                   resource=spoof, audit=audit, **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    ev = _events(audit)
    assert ev[-1]["event_type"] == "decision_approval_denied" and ev[-1]["subject_id"] == "user-1"
    store.close(); audit.close()


def test_actor_is_principal_not_caller_input(tmp_path):
    store, proposed, args = _setup(tmp_path)
    out = approve_as(store, proposed.decision_id, proposed.version,
                     principal=_adapter().issue("approver"), **args)
    assert out.approver == "approver-1"
    store.close()


def test_scope_mismatch_denied_before_state_change(tmp_path):
    audit = AuditChainStore(tmp_path / "a.sqlite3")
    store, proposed, args = _setup(tmp_path)
    args["now"] = NOW
    with pytest.raises(DecisionPermissionError) as e:
        approve_as(store, proposed.decision_id, proposed.version,
                   principal=_adapter().issue("other-project"), audit=audit, **args)
    assert e.value.decision["reason"] == "cross_scope"
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    store.close(); audit.close()


def test_separation_of_duties_still_enforced_for_valid_approver(tmp_path):
    store, proposed, args = _setup(tmp_path)
    same = _adapter(self=_fx(subject_id=proposed.proposer)).issue("self")
    with pytest.raises(ApprovalTransitionError, match="differ"):
        approve_as(store, proposed.decision_id, proposed.version, principal=same, **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    store.close()


@pytest.mark.protected_defaults
def test_require_anchored_without_anchored_writer_fails_closed_no_state_change(tmp_path):
    store, proposed, args = _setup(tmp_path)
    with pytest.raises(AnchorRequiredError):
        approve_as(store, proposed.decision_id, proposed.version,
                   principal=_adapter().issue("approver"), audit=None,
                   **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    store.close()


def test_approve_as_has_no_role_or_subject_parameter():
    import inspect
    params = inspect.signature(approve_as).parameters
    assert not {"role", "subject", "actor"} & set(params)


@pytest.mark.protected_defaults
def test_unanchored_plain_chain_also_fails_closed_with_anchor_error(tmp_path):
    audit = AuditChainStore(tmp_path / "a.sqlite3")
    store, proposed, args = _setup(tmp_path)
    with pytest.raises(AnchorRequiredError):
        approve_as(store, proposed.decision_id, proposed.version,
                   principal=_adapter().issue("approver"), audit=audit,
                   **args)
    assert store.versions(proposed.decision_id)[-1].status == "proposed"
    assert _events(audit) == []
    store.close(); audit.close()


@pytest.mark.parametrize("forged", [
    {"source_sensitivity": "public"},
    {"sensitivity": "public"},
    {"target_sensitivity": "public"},
    {"source_sensitivity": "personal", "purpose": "x", "retention": "y"},
    {"source_sensitivity": "personal"},
    {"source_role": "sealed_holdout"},
])
def test_caller_resource_cannot_alter_policy_inputs(tmp_path, forged):
    from agora.decisions import approval
    seen = {}
    real = approval.authorize_decision_approval_principal

    def spy(principal, resource, **kw):
        seen.update(resource)
        return real(principal, resource, **kw)

    store, proposed, args = _setup(tmp_path)
    args["now"] = NOW
    approval.authorize_decision_approval_principal = spy
    try:
        out = approve_as(store, proposed.decision_id, proposed.version,
                         principal=_adapter().issue("approver"), resource=forged, **args)
    finally:
        approval.authorize_decision_approval_principal = real
    assert out.status == "approved"
    assert seen["source_sensitivity"] == "internal"
    assert not ({"sensitivity", "target_sensitivity", "purpose", "retention", "source_role"} & set(seen))
    assert seen["resource_ids"] == [proposed.decision_id]
    store.close()

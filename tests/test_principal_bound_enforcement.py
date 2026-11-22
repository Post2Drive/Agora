"""Protected enforce_policy() is Principal-bound (M1 gate).

Under protection.PRINCIPAL_BOUND_REQUIRED (production default True), a policy
callable is honoured only when it is a BoundPolicy carrying an adapter-issued
Principal. An always-allow lambda, a bare decide() closure, or None is denied.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agora import protection
from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
from agora.principal import SyntheticFixtureAdapter, principal_policy, BoundPolicy, Principal, Assurance

pytestmark = pytest.mark.protected_defaults

NOW = datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=1)


def _adapter():
    return SyntheticFixtureAdapter({
        "operator": {"subject_id": "op-1", "tenant_id": "t1", "project_ids": ["pilot-1"],
                     "roles": ["operator"], "assurance": "HIGH", "expires_at": LATER},
    })


def _anchor(tmp_path):
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    anchors = AnchorStore(tmp_path / "a.jsonl", "chain-1")
    bootstrap_anchor(chain, anchors, performed_by="maint")
    return AnchoredAuditChain(chain, anchors)


RES = {"project_id": "pilot-1", "source_sensitivity": "internal", "resource_ids": ["r1"]}


def _enforce(tmp_path, policy, op="import", res=RES):
    return enforce_policy(policy, project=tmp_path, operation=op, resource=res,
                          audit=_anchor(tmp_path))


def test_bound_policy_with_valid_principal_is_allowed(tmp_path):
    pol = principal_policy(_adapter().issue("operator"), now=NOW)
    out = enforce_policy(pol, project=tmp_path, operation="import", resource=RES, audit=None)
    assert out["decision"] == "allow"


def test_always_allow_lambda_is_denied_as_not_principal_bound(tmp_path):
    evil = lambda operation, resource: {"decision": "allow", "reason": "ok",
                                        "subject_id": "x", "policy_version": "v"}
    with pytest.raises(PolicyEnforcementError, match="import") as exc:
        _enforce(tmp_path, evil)
    assert "not_principal_bound" in str(exc.value)


def test_bare_decide_closure_is_denied(tmp_path):
    from agora.policy import decide
    closure = lambda operation, resource: decide({"subject_id": "op", "project_id": "pilot-1"},
                                                 "operator", operation, resource)
    with pytest.raises(PolicyEnforcementError):
        _enforce(tmp_path, closure)


def test_none_policy_is_denied_policy_required(tmp_path):
    with pytest.raises(PolicyEnforcementError):
        _enforce(tmp_path, None)


def test_forged_boundpolicy_with_untrusted_issuer_is_denied_at_decision(tmp_path):
    # A hand-built Principal whose issuer is not the adapter's trusted issuer:
    # the BoundPolicy type-check passes, but decide_principal denies it.
    forged = Principal("attacker", "t1", frozenset({"pilot-1"}), frozenset({"operator"}),
                       Assurance.HIGH, "self-signed-issuer", LATER)
    pol = BoundPolicy(forged, required_role=None, now=NOW,
                      trusted_issuers=frozenset({SyntheticFixtureAdapter.ISSUER}))
    with pytest.raises(PolicyEnforcementError):
        _enforce(tmp_path, pol)


def test_denial_event_is_anchored_and_resource_scoped(tmp_path):
    anchor = _anchor(tmp_path)
    evil = lambda operation, resource: {"decision": "allow"}
    with pytest.raises(PolicyEnforcementError):
        enforce_policy(evil, project=tmp_path, operation="binding", resource=RES, audit=anchor)
    rows = [r[0] for r in anchor.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]
    assert any("policy_not_principal_bound" in r and "binding" in r for r in rows)
    assert anchor.verify()["valid"] is True

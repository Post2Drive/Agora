from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agora.audit_chain import AuditChainStore
from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
from agora.principal import SyntheticFixtureAdapter, principal_policy

NOW = datetime(2026, 11, 21, 11, tzinfo=timezone.utc)
EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(**kw):
    base = {"subject_id": "op-1", "tenant_id": "t1", "project_ids": ["pilot-1"], "roles": ["operator"],
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


AD = SyntheticFixtureAdapter({"op": _fx(), "reader": _fx(subject_id="r", roles=["reader"]),
                              "other": _fx(project_ids=["x"]),
                              "old": _fx(expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc))})
RES = {"project_id": "pilot-1", "source_sensitivity": "internal", "resource_ids": ["people"]}


def _run(policy, tmp_path, **kw):
    return enforce_policy(policy, project=tmp_path, operation="import", resource=RES, **kw)


def test_operator_principal_allowed_through_enforce_policy(tmp_path):
    out = _run(principal_policy(AD.issue("op"), now=NOW), tmp_path)
    assert out["decision"] == "allow"


@pytest.mark.parametrize("key,reason", [("reader", "role_not_permitted"), ("other", "cross_scope"),
                                        ("old", "principal_expired")])
def test_bad_principal_denied_and_audited(tmp_path, key, reason):
    with pytest.raises(PolicyEnforcementError, match=reason):
        _run(principal_policy(AD.issue(key), now=NOW), tmp_path)
    c = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    ev = [json.loads(r[0]) for r in c.db.execute("SELECT event_json FROM audit_events")]
    c.close()
    assert ev[0]["event_type"] == "policy_denied" and ev[0]["reason"] == reason


def test_missing_principal_denies(tmp_path):
    with pytest.raises(PolicyEnforcementError, match="principal_missing"):
        _run(principal_policy(None, now=NOW), tmp_path)


def test_resource_cannot_grant_authority(tmp_path):
    forged = dict(RES, role="approver", roles=["operator"], subject_id="op-1")
    with pytest.raises(PolicyEnforcementError, match="role_not_permitted"):
        enforce_policy(principal_policy(AD.issue("reader"), now=NOW), project=tmp_path,
                       operation="import", resource=forged)


def test_policy_none_still_noop_unless_required(tmp_path):
    assert _run(None, tmp_path) is None
    with pytest.raises(PolicyEnforcementError, match="policy_required"):
        _run(None, tmp_path, require_policy=True)
    c = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    n = c.db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    c.close()
    assert n == 1


def test_non_callable_policy_still_denied_when_required(tmp_path):
    with pytest.raises(PolicyEnforcementError, match="policy_not_callable"):
        _run("nope", tmp_path, require_policy=True)


def test_required_role_is_enforced_by_bound_policy(tmp_path):
    with pytest.raises(PolicyEnforcementError, match="role_not_permitted"):
        _run(principal_policy(AD.issue("op"), now=NOW, required_role="reviewer"), tmp_path)

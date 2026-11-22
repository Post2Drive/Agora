"""Production defaults are protected: policy and anchored audit are on unless a
caller explicitly opts out. These tests keep the defaults intact (no relaxation)."""
from __future__ import annotations

import inspect

import pytest

from agora.audit_anchor import AnchorRequiredError
from agora.audit_chain import AuditChainStore
from agora.decisions import approval, outcomes
from agora.decisions.approval import approve_as
from agora.decisions.outcomes import record_outcome_as, review_outcome_as
from agora.ontology.binding import materialize_instances
from agora.scenario_inputs import build_scenario_input
from agora.tabular import TabularIngestError, ingest_csv
from agora.cli import main
from tests.test_data_cli import files
from tests.test_principal_outcomes import ADAPTER, REV, _rec_args
from tests.test_decision_outcomes import approved_store

pytestmark = pytest.mark.protected_defaults

POLICY_FNS = (ingest_csv, materialize_instances, build_scenario_input)
ANCHOR_FNS = (approve_as, record_outcome_as, review_outcome_as)


@pytest.mark.parametrize("fn", POLICY_FNS)
def test_no_policy_opt_out_parameter(fn):
    assert "require_policy" not in inspect.signature(fn).parameters
    with pytest.raises(TypeError):
        fn(require_policy=False)


@pytest.mark.parametrize("fn", ANCHOR_FNS)
def test_no_anchor_opt_out_parameter(fn):
    assert "require_anchored" not in inspect.signature(fn).parameters
    assert "require_anchored" not in inspect.signature(fn).parameters


def test_protection_flags_are_on_in_production():
    """Fresh process: conftest cannot have relaxed anything."""
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c",
                        "from agora import protection as p; print(p.POLICY_REQUIRED, p.ANCHOR_REQUIRED)"],
                       capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "True True", r.stderr


@pytest.mark.protected_defaults
def test_ingest_without_policy_is_denied_and_audited_before_read(tmp_path):
    source, schema = files(tmp_path, personal=False)
    import json
    sch = json.loads(schema.read_text())
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError) as e:
        ingest_csv(project, source, sch, data_role="context")
    assert e.value.code == "POLICY_DENIED"
    assert not (project / "data" / "audit_chain.sqlite3").exists()


def test_enforce_policy_direct_default_denies_missing_policy_without_unanchored_chain(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
    with pytest.raises(PolicyEnforcementError, match="could not be recorded") as e:
        enforce_policy(None, project=tmp_path, operation="import", resource={})
    assert "no anchored audit writer" in str(e.value.__cause__)
    assert not (tmp_path / "data").exists()


def test_data_cli_default_import_is_denied(tmp_path, capsys):
    source, schema = files(tmp_path, personal=False)
    rc = main(["data", "import-csv", "--project", str(tmp_path / "p"), "--csv", str(source),
               "--schema", str(schema), "--role", "context"])
    assert rc == 2
    assert "POLICY_DENIED" in capsys.readouterr().err


def test_outcome_and_approval_wrappers_deny_without_anchored_writer_by_default(tmp_path):
    _, store, approved = approved_store(tmp_path)
    plain = AuditChainStore(tmp_path / "audit.sqlite3")
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            record_outcome_as(store, principal=ADAPTER.issue("op"), audit=audit, **_rec_args(approved))
    assert store.outcomes(approved.decision_id, approved.version) == []
    from agora import protection
    mp = pytest.MonkeyPatch()
    mp.setattr(protection, "ANCHOR_REQUIRED", False)  # relaxed setup only
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_rec_args(approved))
    mp.undo()
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                              principal=ADAPTER.issue("rev"), audit=audit, **REV)
    assert store.reviews(approved.decision_id, approved.version, out["outcome_id"]) == []
    plain.close()


# --- direct enforce_policy hardening: no caller override, anchored writer only ---

def _bound(key="op", **kw):
    from agora.principal import principal_policy
    return principal_policy(ADAPTER.issue(key), **kw)


def _deny_policy(operation, resource):
    return {"decision": "deny", "reason": "cross_scope", "subject_id": "op-1", "policy_version": "v1"}


def _allow_policy(operation, resource):
    return {"decision": "allow", "reason": "ok", "subject_id": "op-1", "policy_version": "v1"}


def _anchored(tmp_path):
    from agora.audit_anchor import AnchorStore, bootstrap_anchor, open_anchored_audit
    chain = AuditChainStore(tmp_path / "c.sqlite3")
    bootstrap_anchor(chain, AnchorStore(tmp_path / "a.jsonl", "c1"), performed_by="maint-1")
    chain.close()
    return open_anchored_audit(tmp_path / "c.sqlite3", tmp_path / "a.jsonl", "c1")


def test_enforce_policy_has_no_require_policy_parameter(tmp_path):
    from agora.policy_enforcement import enforce_policy
    assert "require_policy" not in inspect.signature(enforce_policy).parameters
    for flag in (False, True):
        with pytest.raises(TypeError):
            enforce_policy(None, project=tmp_path, operation="import", resource={}, require_policy=flag)


def test_enforce_policy_rejects_plain_writer_and_writes_nothing(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
    plain = AuditChainStore(tmp_path / "plain.sqlite3")
    with pytest.raises(PolicyEnforcementError, match="could not be recorded"):
        enforce_policy(_deny_policy, project=tmp_path, operation="import", resource={}, audit=plain)
    assert plain.db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
    plain.close()


def test_enforce_policy_rejects_duck_typed_writer(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy

    class Duck:
        calls = 0
        def append(self, event):
            Duck.calls += 1

    with pytest.raises(PolicyEnforcementError):
        enforce_policy(_deny_policy, project=tmp_path, operation="import", resource={}, audit=Duck())
    assert Duck.calls == 0


def test_enforce_policy_denial_appends_to_anchored_writer(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
    with _anchored(tmp_path) as writer:
        with pytest.raises(PolicyEnforcementError, match="scope_missing"):
            enforce_policy(_bound(), project=tmp_path, operation="import", resource={}, audit=writer)
        assert writer.verify()["valid"]
        assert writer.chain.db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1


def test_enforce_policy_missing_policy_with_anchored_writer_is_denied_and_audited(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
    with _anchored(tmp_path) as writer:
        with pytest.raises(PolicyEnforcementError, match="policy_required"):
            enforce_policy(None, project=tmp_path, operation="import", resource={}, audit=writer)
        assert writer.verify()["valid"]


def test_enforce_policy_allow_path_unchanged(tmp_path):
    from agora.policy_enforcement import enforce_policy
    res = {"project_id": "pilot-1", "source_sensitivity": "internal"}
    assert enforce_policy(_bound(), project=tmp_path, operation="import", resource=res)["decision"] == "allow"


def test_enforce_policy_rejects_raw_callables_in_protected_mode_and_audits(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, enforce_policy
    res = {"project_id": "pilot-1", "source_sensitivity": "internal"}
    for i, raw in enumerate((_allow_policy, lambda o, r: {"decision": "allow"}, _bound().__call__)):
        (tmp_path / f"w{i}").mkdir()
        with _anchored(tmp_path / f"w{i}") as writer:
            with pytest.raises(PolicyEnforcementError, match="policy_not_principal_bound"):
                enforce_policy(raw, project=tmp_path, operation="import", resource=res, audit=writer)
            ev = writer.chain.db.execute("SELECT event_json FROM audit_events").fetchall()
            assert len(ev) == 1 and "policy_not_principal_bound" in ev[0][0]


def test_principal_policy_cannot_be_forged_or_subclassed(tmp_path):
    from agora.policy_enforcement import PolicyEnforcementError, PrincipalPolicy, enforce_policy
    with pytest.raises(TypeError):
        PrincipalPolicy(object(), _allow_policy, ADAPTER.issue("op"))
    with pytest.raises(TypeError):
        PrincipalPolicy()
    with pytest.raises(TypeError):
        type("Evil", (PrincipalPolicy,), {})
    good = _bound()
    with pytest.raises(AttributeError):
        good._fn = _allow_policy
    # lookalike duck type is still rejected
    class Duck:
        _principal = ADAPTER.issue("op")
        def __call__(self, o, r): return {"decision": "allow"}
    with pytest.raises(PolicyEnforcementError):
        enforce_policy(Duck(), project=tmp_path, operation="import", resource={})


# --- lifecycle entry points (propose/reject/expire/supersede) are anchored by default ---

def _relaxed_proposed(tmp_path, *, review_date=None):
    from agora import protection
    from agora.decisions.approval import propose
    from agora.decisions.store import DecisionRecordStore
    from tests.test_decision_approval import draft_record
    store = DecisionRecordStore(tmp_path / "life.db")
    store.append(draft_record() | ({"review_date": review_date} if review_date else {}))
    with pytest.MonkeyPatch.context() as mp:  # setup only
        mp.setattr(protection, "ANCHOR_REQUIRED", False)
        proposed = propose(store, "decision-approval-001", 1, actor="analyst",
                           now="2026-11-21T10:00:00Z")
    return store, proposed


def _status(store):
    return store.versions("decision-approval-001")[-1].status


def test_lifecycle_propose_denied_without_anchored_writer_and_stores_nothing(tmp_path):
    from agora.decisions.approval import propose
    from agora.decisions.store import DecisionRecordStore
    from tests.test_decision_approval import draft_record
    store = DecisionRecordStore(tmp_path / "p.db")
    store.append(draft_record())
    plain = AuditChainStore(tmp_path / "plain.sqlite3")
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            propose(store, "decision-approval-001", 1, actor="analyst",
                    now="2026-11-21T10:00:00Z", audit=audit)
    assert _status(store) == "draft"
    assert [e for e in store.approval_events("decision-approval-001")] == []
    plain.close(); store.close()


def test_lifecycle_reject_expire_supersede_denied_without_anchored_writer(tmp_path):
    from agora.decisions.approval import expire, reject, supersede
    store, p = _relaxed_proposed(tmp_path, review_date="2026-11-22")
    plain = AuditChainStore(tmp_path / "plain.sqlite3")
    for audit in (None, plain):
        with pytest.raises(AnchorRequiredError):
            reject(store, p.decision_id, p.version, actor="reviewer-1",
                   now="2026-11-21T10:30:00Z", audit=audit)
        with pytest.raises(AnchorRequiredError):
            expire(store, p.decision_id, p.version, now="2026-11-30T00:00:00Z", audit=audit)
        with pytest.raises(AnchorRequiredError):
            supersede(store, p.decision_id, p.version, actor="analyst",
                      replacement_fingerprint="sha256:" + "ab" * 32,
                      now="2026-11-21T10:30:00Z", audit=audit)
    assert _status(store) == "proposed"
    assert len(store.versions(p.decision_id)) == 2  # no new version written
    plain.close(); store.close()


def test_lifecycle_anchored_writer_succeeds_and_is_audited(tmp_path):
    from agora.audit_anchor import AnchorStore, bootstrap_anchor, open_anchored_audit
    from agora.decisions.approval import propose
    from agora.decisions.store import DecisionRecordStore
    from tests.test_decision_approval import draft_record
    chain = AuditChainStore(tmp_path / "c.sqlite3")
    bootstrap_anchor(chain, AnchorStore(tmp_path / "a.jsonl", "c1"), performed_by="maint-1")
    chain.close()
    store = DecisionRecordStore(tmp_path / "ok.db")
    store.append(draft_record())
    with open_anchored_audit(tmp_path / "c.sqlite3", tmp_path / "a.jsonl", "c1") as w:
        propose(store, "decision-approval-001", 1, actor="analyst",
                now="2026-11-21T10:00:00Z", audit=w)
        assert w.verify()["valid"] is True
    assert _status(store) == "proposed"
    store.close()


# --- role-string authority lockdown (M1 principal call-site migration) ---------

_ROLE_STRING_ALLOWED = {
    "agora/principal.py",             # decide_principal: role comes from the Principal
    "agora/decisions/permissions.py",  # legacy approval gate (test-only approve())
    "agora/decisions/outcomes.py",     # private _authorize used by wrapper-derived roles
}


def _role_string_importers():
    import pathlib
    import re
    root = pathlib.Path(approval.__file__).resolve().parents[1]
    found = set()
    pat = re.compile(r"from\s+(?:agora|\.+)\.?policy\s+import\s+([^\n]+)|import\s+agora\.policy")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            names = m.group(1) or "decide"
            if re.search(r"\b(decide|authorize)\b", names) or m.group(1) is None:
                found.add(path.relative_to(root.parent).as_posix())
    return found


def test_role_string_pdp_is_imported_only_by_allowlisted_modules():
    assert _role_string_importers() <= _ROLE_STRING_ALLOWED


def test_no_public_role_string_approval_authorizer_exported():
    from agora.decisions import permissions
    assert not hasattr(permissions, "authorize_decision_approval")
    assert "authorize_decision_approval" not in permissions.__all__
    assert hasattr(permissions, "authorize_decision_approval_principal")

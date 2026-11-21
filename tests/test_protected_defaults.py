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


def test_ingest_without_policy_is_denied_and_audited_before_read(tmp_path):
    source, schema = files(tmp_path, personal=False)
    import json
    sch = json.loads(schema.read_text())
    project = tmp_path / "project"
    with pytest.raises(TabularIngestError) as e:
        ingest_csv(project, source, sch, data_role="context")
    assert e.value.code == "POLICY_DENIED"
    chain = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    rows = chain.db.execute("SELECT event_json FROM audit_events").fetchall()
    chain.close()
    assert len(rows) == 1 and "policy_required" in rows[0][0]


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

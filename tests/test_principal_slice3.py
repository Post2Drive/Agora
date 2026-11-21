"""require_policy=True: ingest, binding and scenario-input deny a missing policy (fail closed)."""
from __future__ import annotations

import json

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError
from agora.ontology.binding import materialize_instances
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import TabularIngestError, ingest_csv

from tests.test_scenario_inputs import _binding, _import, _pack, _policy, _schema


def _events(project):
    c = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    try:
        return [json.loads(r[0]) for r in c.db.execute("SELECT event_json FROM audit_events")]
    finally:
        c.close()


def _allow(operation, resource):
    return {"decision": "allow", "reason": "ok", "subject_id": "op-1",
            "policy_version": "t", "resource_ids": []}


@pytest.mark.protected_defaults
def test_ingest_require_policy_denies_missing_policy_and_audits(tmp_path):
    src = tmp_path / "c.csv"
    src.write_text("customer_id,email\nC1,a@example.test\n", encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc:
        ingest_csv(tmp_path / "p", src, _schema(), data_role="context")
    assert exc.value.code == "POLICY_DENIED"
    # No anchored writer was supplied: the denial is raised but never written
    # to an unanchored project-local chain.
    assert not (tmp_path / "p" / "data" / "audit_chain.sqlite3").exists()


class _Rec:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)


@pytest.mark.protected_defaults
def test_ingest_policy_denial_goes_to_supplied_writer(tmp_path):
    src = tmp_path / "c.csv"
    src.write_text("customer_id,email\nC1,a@example.test\n", encoding="utf-8")
    rec = _Rec()
    with pytest.raises(TabularIngestError):
        ingest_csv(tmp_path / "p", src, _schema(), data_role="context", audit=rec)
    assert rec.events[0]["event_type"] == "policy_denied"
    assert rec.events[0]["reason"] == "policy_required"


def test_ingest_default_still_legacy_noop(tmp_path):
    src = tmp_path / "c.csv"
    src.write_text("customer_id,email\nC1,a@example.test\n", encoding="utf-8")
    assert ingest_csv(tmp_path / "p", src, _schema(), data_role="context")["import_id"]


def test_ingest_require_policy_with_allowing_policy_works(tmp_path):
    src = tmp_path / "c.csv"
    src.write_text("customer_id,email\nC1,a@example.test\n", encoding="utf-8")
    out = ingest_csv(tmp_path / "p", src, _schema(), data_role="context",
                     policy=_allow)
    assert out["import_id"]


def test_binding_require_policy_denies_missing_policy(tmp_path, monkeypatch):
    from agora import protection
    imported = _import(tmp_path)  # relaxed setup
    monkeypatch.setattr(protection, "POLICY_REQUIRED", True)
    with pytest.raises(OntologyError, match="Policy denied"):
        materialize_instances(_binding(), _pack(), tmp_path, imported["import_id"])
    assert _events(tmp_path)[-1]["reason"] == "policy_required"
    assert materialize_instances(_binding(), _pack(), tmp_path, imported["import_id"],
                                 policy=_allow, purpose="synthetic", retention="one day")


def test_scenario_input_require_policy_denies_missing_policy(tmp_path, monkeypatch):
    from agora import protection
    imported = _import(tmp_path)  # relaxed setup
    monkeypatch.setattr(protection, "POLICY_REQUIRED", True)
    with pytest.raises(ScenarioInputError):
        build_scenario_input(_binding(), _pack(), tmp_path, imported["import_id"],
                             transformation_policy=_policy())
    assert _events(tmp_path)[-1]["reason"] == "policy_required"
    assert build_scenario_input(_binding(), _pack(), tmp_path, imported["import_id"],
                                transformation_policy=_policy(), policy=_allow)

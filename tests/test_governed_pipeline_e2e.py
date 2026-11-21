"""End-to-end governed pipeline on synthetic data only (Block 26).

Flow: ingest -> bind/materialize -> scenario input -> decision -> approval ->
report provenance, with the real policy decision point wired through every
hook that accepts one, a deny case per stage, and the audit chain verified at
the end. No agora/** changes, no simulation, no real data.
"""
from __future__ import annotations

import json

import pytest

from agora.audit_chain import AuditChainStore
from agora.decisions.approval import approve, propose
from agora.decisions.store import DecisionRecordStore
from agora.ontology import parse_domain_pack
from agora.ontology.binding import OntologyError, load_binding, materialize_instances
from agora.policy import decide
from agora.report import writer
from agora.report.writer import _report_provenance
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.store import Store
from agora.tabular import TabularIngestError, ingest_csv

PROJECT_ID = "pilot-1"
SECRET_EMAIL = "synthetic-secret@example.test"


def _pack():
    return parse_domain_pack({
        "pack_id": "e2e-pack", "schema_version": "1.0.0",
        "object_types": [{"type_id": "e2e:Customer", "version": "1.0.0", "name": "Customer",
                          "description": "Synthetic customer",
                          "properties": ["e2e:Customer.id", "e2e:Customer.email"],
                          "identity_strategy": "record_key"}],
        "property_types": [
            {"property_id": "e2e:Customer.id", "version": "1.0.0", "name": "ID", "data_type": "identifier",
             "required": True, "nullable": False, "sensitivity": "personal"},
            {"property_id": "e2e:Customer.email", "version": "1.0.0", "name": "Email", "data_type": "string",
             "required": True, "nullable": False, "sensitivity": "sensitive"},
        ],
        "link_types": [], "action_types": [],
    })


def _schema():
    return {"schema_id": "e2e-customers", "schema_version": "1.0.0", "dataset_name": "e2e_customers", "columns": [
        {"name": "customer_id", "type": "string", "nullable": False, "primary_key": True,
         "sensitivity": "personal", "purpose": "synthetic identity", "retention": "one day"},
        {"name": "email", "type": "string", "nullable": False, "sensitivity": "sensitive"},
    ]}


def _binding():
    return load_binding({
        "binding_id": "e2e.customer.v1", "binding_version": "1.0.0",
        "object_type_id": "e2e:Customer", "object_type_version": "1.0.0",
        "dataset_id": "e2e_customers", "schema_id": "e2e-customers", "schema_version": "1.0.0",
        "column_map": {"customer_id": "e2e:Customer.id", "email": "e2e:Customer.email"},
        "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
        "property_sensitivity": {"e2e:Customer.id": "personal", "e2e:Customer.email": "sensitive"},
    })


def _transformation_policy():
    return {"policy_id": "e2e-transform-v1", "purpose": "synthetic e2e transformation", "retention": "one day",
            "reviewer": "governance-test", "approved_at": "2026-11-21T00:00:00Z", "audit_reference": "AUD-E2E",
            "permitted_sensitivities": ["personal", "sensitive"],
            "authorized_property_ids": ["e2e:Customer.id"]}


def _policy(role):
    """Real central PDP as the enforcement callable, with no help from the test."""
    subject = {"subject_id": "operator-1", "project_id": PROJECT_ID}

    def call(operation, resource):
        return decide(subject, role, operation, dict(resource))

    return call


def _csv(tmp_path):
    source = tmp_path / "customers.csv"
    source.write_text(f"customer_id,email\nC001,{SECRET_EMAIL}\n", encoding="utf-8")
    return source


def _events(project):
    audit = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    try:
        verdict = audit.verify()
        rows = [json.loads(row[0]) for row in audit.db.execute(
            "SELECT event_json FROM audit_events ORDER BY rowid")]
    finally:
        audit.close()
    return verdict, rows


def _decision_record(import_id, scenario_hash):
    return {
        "decision_id": "decision-e2e-001", "version": 1, "project_scope": {"project_id": PROJECT_ID},
        "status": "draft", "statement": "Choose a synthetic pilot cohort", "alternatives": ["A", "B"],
        "evidence_refs": [
            {"kind": "import", "import_id": import_id, "dataset_id": "e2e_customers"},
            {"kind": "scenario", "scenario_hash": scenario_hash, "mode": "exploratory"},
        ],
        "rationale": "Evidence is exploratory.", "assumptions": ["Synthetic data"], "uncertainty": ["Small sample"],
        "outcome_measures": ["observed follow-up"], "proposer": "analyst", "reviewer": "reviewer-1",
        "created_at": "2026-11-21T00:00:00Z", "updated_at": "2026-11-21T00:00:00Z",
        "approval_method": "manual", "review_date": "2026-12-01",
    }


def test_governed_pipeline_happy_path_then_audit_and_provenance(tmp_path):
    project = tmp_path / PROJECT_ID
    project.mkdir()
    operator = _policy("operator")

    imported = ingest_csv(project, _csv(tmp_path), _schema(), data_role="scenario_input", policy=operator)
    instances = materialize_instances(
        _binding(), _pack(), project, imported["import_id"], policy=operator,
        purpose="synthetic e2e transformation", retention="one day",
    )
    assert instances and all("record_key" in item for item in instances)
    built = build_scenario_input(
        _binding(), _pack(), project, imported["import_id"],
        transformation_policy=_transformation_policy(), policy=operator,
    )
    assert built["validated_prediction_enabled"] is False
    assert SECRET_EMAIL not in json.dumps(built)

    store = DecisionRecordStore(project / "decisions.db")
    try:
        store.append(_decision_record(imported["import_id"], built["scenario_hash"]))
        proposed = propose(store, "decision-e2e-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
        approved = approve(
            store, proposed.decision_id, proposed.version,
            actor="approver-1", role="approver",
            subject={"subject_id": "approver-1", "project_id": PROJECT_ID},
            expected_fingerprint=proposed.fingerprint,
            expected_scope={"project_id": PROJECT_ID},
            expected_evidence_refs=proposed.evidence_refs, now="2026-11-21T11:00:00Z",
        )
        assert approved.status == "approved"
        assert [row.status for row in store.versions("decision-e2e-001")] == ["draft", "proposed", "approved"]
    finally:
        store.close()

    run = Store(project / "agora.db")
    try:
        run.set_input_provenance(built["manifest"])
    finally:
        run.close()
    provenance = _report_provenance(project)
    assert provenance["provenance_status"] == "verified"
    assert provenance["scenario_hash"] == built["scenario_hash"]
    assert SECRET_EMAIL not in json.dumps(provenance)

    # Allowed operations write no denial events, so no chain exists yet.
    assert not (project / "data" / "audit_chain.sqlite3").exists()


def test_every_stage_denies_and_the_shared_audit_chain_verifies(tmp_path):
    project = tmp_path / PROJECT_ID
    project.mkdir()
    operator = _policy("operator")
    reader = _policy("reader")

    # Stage 1 import: reader role is not permitted; the source file is never read.
    with pytest.raises(TabularIngestError, match="Policy denied"):
        ingest_csv(project, tmp_path / "never-read.csv", _schema(), data_role="scenario_input", policy=reader)
    assert not (project / "data" / "tabular.sqlite3").exists()

    imported = ingest_csv(project, _csv(tmp_path), _schema(), data_role="scenario_input", policy=operator)

    # Stage 2 binding: reader denied.
    with pytest.raises(OntologyError, match="Policy denied"):
        materialize_instances(_binding(), _pack(), project, imported["import_id"], policy=reader)
    # The real PDP also denies personal data when the caller declares no purpose/retention.
    with pytest.raises(OntologyError, match="Policy denied"):
        materialize_instances(_binding(), _pack(), project, imported["import_id"], policy=operator)

    # Stage 3 scenario input: reader denied.
    with pytest.raises(ScenarioInputError, match="Policy denied"):
        build_scenario_input(
            _binding(), _pack(), project, imported["import_id"],
            transformation_policy=_transformation_policy(), policy=reader,
        )

    # Stage 4 approval: non-approver roles are denied and nothing is approved.
    store = DecisionRecordStore(project / "decisions.db")
    try:
        store.append(_decision_record(imported["import_id"], "sha256:" + "ab" * 32))
        proposed = propose(store, "decision-e2e-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
        for role in ("operator", "reviewer", "reader"):
            with pytest.raises(PermissionError, match="decision approval denied"):
                approve(
                    store, proposed.decision_id, proposed.version,
                    actor="approver-1", role=role,
                    subject={"subject_id": "approver-1", "project_id": PROJECT_ID},
                    expected_fingerprint=proposed.fingerprint,
                    expected_scope={"project_id": PROJECT_ID},
                    expected_evidence_refs=proposed.evidence_refs, now="2026-11-21T11:00:00Z",
                )
        assert store.versions("decision-e2e-001")[-1].status == "proposed"
    finally:
        store.close()

    # Audit chain: four denials from the data stages, hash chain intact.
    verdict, events = _events(project)
    assert verdict["valid"] is True
    assert [event.get("operation") for event in events] == [
        "import", "binding", "binding", "simulation_input",
    ]
    assert SECRET_EMAIL not in json.dumps(events)


def test_sealed_holdout_is_denied_by_the_real_pdp_at_import(tmp_path):
    project = tmp_path / PROJECT_ID
    project.mkdir()
    with pytest.raises(TabularIngestError, match="Policy denied"):
        ingest_csv(project, _csv(tmp_path), _schema(), data_role="sealed_holdout", policy=_policy("operator"))
    verdict, events = _events(project)
    assert verdict["valid"] is True and len(events) == 1


def test_report_gate_fails_before_provenance_is_read(tmp_path, monkeypatch):
    """Validated-prediction gate must be the first operation that can fail."""
    project = tmp_path / "report-gate"
    (project / "validation").mkdir(parents=True)
    (project / "validation" / "scope.json").write_text("{}", encoding="utf-8")

    def provenance_must_not_run(*args, **kwargs):
        raise AssertionError("provenance must not be read before the approval gate")

    monkeypatch.setattr(writer, "_report_provenance", provenance_must_not_run)
    with pytest.raises(PermissionError, match="Validated Prediction requires"):
        writer.write_report(project, None, mode="validated_prediction", registry_id="missing", claims=["claim"])
    assert not (project / "report" / "report.json").exists()

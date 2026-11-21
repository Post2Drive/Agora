from __future__ import annotations

import copy

import pytest

from agora.decisions import DecisionRecordError, load_decision_record


def record():
    return {
        "decision_id": "decision-001", "version": 1, "project_scope": {"project_id": "pilot-1"},
        "status": "draft", "statement": "Choose a synthetic pilot cohort", "alternatives": ["A", "B"],
        "evidence_refs": [{"kind": "import", "import_id": "import-001", "dataset_id": "customers"}, {"kind": "run", "run_id": "run-001", "mode": "exploratory"}],
        "rationale": "Evidence is exploratory.", "assumptions": ["Synthetic data"], "uncertainty": ["Small sample"],
        "outcome_measures": ["observed follow-up"], "proposer": "analyst", "reviewer": "reviewer",
        "created_at": "2026-11-21T00:00:00Z", "updated_at": "2026-11-21T00:00:00Z",
        "approval_method": "manual", "review_date": "2026-12-01",
    }


def test_schema_computes_fingerprint_including_evidence():
    parsed = load_decision_record(record())
    changed = copy.deepcopy(record())
    changed["evidence_refs"][0]["import_id"] = "import-002"
    assert parsed.fingerprint != load_decision_record(changed).fingerprint


def test_latest_and_unknown_or_missing_fields_fail_closed():
    latest = record(); latest["evidence_refs"][0]["import_id"] = "latest"
    with pytest.raises(DecisionRecordError, match="latest"):
        load_decision_record(latest)
    unknown = record(); unknown["unexpected"] = True
    with pytest.raises(DecisionRecordError, match="unknown"):
        load_decision_record(unknown)
    missing = record(); missing.pop("rationale")
    with pytest.raises(DecisionRecordError, match="missing"):
        load_decision_record(missing)


def test_supplied_fingerprint_must_match():
    value = record(); value["fingerprint"] = "sha256:wrong"
    with pytest.raises(DecisionRecordError, match="fingerprint"):
        load_decision_record(value)


def test_empty_refs_timestamps_and_approval_are_rejected():
    empty = record(); empty["evidence_refs"] = []
    with pytest.raises(DecisionRecordError, match="non-empty"):
        load_decision_record(empty)
    bad_time = record(); bad_time["created_at"] = "not-a-date"
    with pytest.raises(DecisionRecordError, match="timestamps"):
        load_decision_record(bad_time)
    approved = record(); approved["status"] = "approved"
    with pytest.raises(DecisionRecordError, match="approver"):
        load_decision_record(approved)


def test_approved_record_rejects_self_approval():
    approved = record()
    approved["status"] = "approved"
    approved["approver"] = approved["proposer"]
    with pytest.raises(DecisionRecordError, match="approver must differ"):
        load_decision_record(approved)


def test_evidence_kind_fields_and_exploratory_mode_are_enforced():
    bad_kind = record(); bad_kind["evidence_refs"][0] = {"kind": "snapshot", "ref": "x"}
    with pytest.raises(DecisionRecordError, match="kind"):
        load_decision_record(bad_kind)
    bad_hash = record(); bad_hash["evidence_refs"][0] = {"kind": "binding", "fingerprint": "sha256:short"}
    with pytest.raises(DecisionRecordError, match="fingerprint"):
        load_decision_record(bad_hash)
    bad_mode = record(); bad_mode["evidence_refs"][1]["mode"] = "validated_prediction"
    with pytest.raises(DecisionRecordError, match="exploratory"):
        load_decision_record(bad_mode)

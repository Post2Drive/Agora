from __future__ import annotations

import copy

import pytest

from agora.decisions import DecisionRecordError, load_decision_record


def record():
    return {
        "decision_id": "decision-001", "version": 1, "project_scope": {"project_id": "pilot-1"},
        "status": "draft", "statement": "Choose a synthetic pilot cohort", "alternatives": ["A", "B"],
        "evidence_refs": [{"kind": "snapshot", "ref": "import-001", "dataset_id": "customers"}, {"kind": "run", "ref": "run-001"}],
        "rationale": "Evidence is exploratory.", "assumptions": ["Synthetic data"], "uncertainty": ["Small sample"],
        "outcome_measures": ["observed follow-up"], "proposer": "analyst", "reviewer": "reviewer",
        "created_at": "2026-11-21T00:00:00Z", "updated_at": "2026-11-21T00:00:00Z",
        "approval_method": "manual", "review_date": "2026-12-01T00:00:00Z",
    }


def test_schema_computes_fingerprint_including_evidence():
    parsed = load_decision_record(record())
    changed = copy.deepcopy(record())
    changed["evidence_refs"][0]["ref"] = "import-002"
    assert parsed.fingerprint != load_decision_record(changed).fingerprint


def test_latest_and_unknown_or_missing_fields_fail_closed():
    latest = record(); latest["evidence_refs"][0]["ref"] = "latest"
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

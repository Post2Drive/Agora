from __future__ import annotations

import json
import sqlite3

import pytest

from agora.decisions import DecisionRecordError, DecisionRecordStore
from agora.decisions.schema import load_decision_record


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


def test_store_appends_versions_and_rejects_replacement(tmp_path):
    store = DecisionRecordStore(tmp_path / "decisions.db")
    first = store.append(record())
    second = load_decision_record(dict(
        record(), version=2, status="proposed", supersedes=first.fingerprint,
        updated_at="2026-11-21T00:01:00Z",
    ))
    store.append_transition(second, {
        "transition": "proposed", "actor": "analyst", "method": "manual",
        "occurred_at": second.updated_at, "decision_fingerprint": second.fingerprint,
    })
    assert [item.version for item in store.versions("decision-001")] == [1, 2]
    changed = dict(record(), statement="changed")
    with pytest.raises(DecisionRecordError, match="already exists"):
        store.append(changed)
    store.close()


def test_store_rejects_update_delete_and_detects_tampering(tmp_path):
    store = DecisionRecordStore(tmp_path / "decisions.db")
    stored = store.append(record())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("UPDATE decision_records SET payload_json=? WHERE decision_id=? AND version=1", ("{}", "decision-001"))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM decision_records WHERE decision_id=? AND version=1", ("decision-001",))
    store.db.execute("DROP TRIGGER protect_decision_record_update")
    payload = stored.as_dict(); payload["statement"] = "tampered"
    store.db.execute("UPDATE decision_records SET payload_json=? WHERE decision_id=? AND version=1", (json.dumps(payload), "decision-001"))
    store.db.commit()
    with pytest.raises(DecisionRecordError, match="fingerprint"):
        store.get("decision-001", 1)
    store.close()

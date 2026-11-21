from __future__ import annotations

import json
import sqlite3

import pytest

from agora.audit_chain import AuditChainStore
from agora.decisions.approval import approve, propose
from agora.decisions.outcomes import (
    DecisionOutcomeStore, OutcomeError, OutcomePermissionError,
    _record_outcome as record_outcome, _review_outcome as review_outcome,
)
from agora.decisions.store import DecisionRecordStore
from tests.test_decision_approval import approve_args, draft_record

HASH = "sha256:" + "ab" * 32
SECRET_NOTE = "customer-private-note-123"


def approved_store(tmp_path, measures=None):
    decisions = DecisionRecordStore(tmp_path / "decisions.db")
    decisions.append(draft_record() | ({"outcome_measures": measures} if measures else {}))
    proposed = propose(decisions, "decision-approval-001", 1, actor="analyst", now="2026-11-21T10:00:00Z")
    approved = approve(decisions, proposed.decision_id, proposed.version, **approve_args(proposed))
    return decisions, DecisionOutcomeStore(decisions), approved


def outcome_args(approved, **over):
    args = dict(
        decision_id=approved.decision_id, decision_version=approved.version,
        measure="observed follow-up", observed_value=42, unit="people",
        observed_at="2026-11-25T00:00:00Z",
        measurement_window={"start": "2026-11-22T00:00:00Z", "end": "2026-11-30T00:00:00Z"},
        source_ref={"source_registry_id": "source-1", "evidence_id": "evidence-1", "content_hash": HASH},
        provenance_class="observed", validation_status="source_verified",
        recorder="recorder-1", role="operator",
        subject={"subject_id": "recorder-1", "project_id": "pilot-1"},
        now="2026-11-26T00:00:00Z",
    )
    args.update(over)
    return args


def review_args(**over):
    args = dict(
        new_state="reviewed", reviewer="reviewer-9", role="reviewer",
        subject={"subject_id": "reviewer-9", "project_id": "pilot-1"},
        rationale_code="source_checked", now="2026-11-27T00:00:00Z",
    )
    args.update(over)
    return args


def test_records_one_outcome_for_exact_approved_version(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved))
    assert out["decision_fingerprint"] == approved.fingerprint
    assert store.outcomes(approved.decision_id, approved.version) == [out]
    assert store.state(approved.decision_id, approved.version, out["outcome_id"]) == "recorded"
    # The decision record itself is untouched.
    assert [r.status for r in decisions.versions(approved.decision_id)] == ["draft", "proposed", "approved"]


@pytest.mark.parametrize("version", [1, 2, 99])
def test_non_approved_or_missing_versions_are_rejected(tmp_path, version):
    decisions, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomeError):
        record_outcome(store, **outcome_args(approved, decision_version=version))


def test_measure_must_exactly_match_decision(tmp_path):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomeError, match="outcome_measures"):
        record_outcome(store, **outcome_args(approved, measure="made up measure"))


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), [1], {"a": 1}, "  "])
def test_observed_value_must_be_a_finite_scalar(tmp_path, value):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomeError):
        record_outcome(store, **outcome_args(approved, observed_value=value))


@pytest.mark.parametrize("value", [0, 3.5, True, "yes"])
def test_valid_scalars_are_accepted(tmp_path, value):
    _, store, approved = approved_store(tmp_path)
    assert record_outcome(store, **outcome_args(approved, observed_value=value))["observed_value"] == value


def test_timestamps_and_window_are_validated(tmp_path):
    _, store, approved = approved_store(tmp_path)
    for over in (
        {"observed_at": "2026-11-25T00:00:00"},
        {"observed_at": "2026-12-05T00:00:00Z"},
        {"observed_at": "2026-11-01T00:00:00Z"},
        {"measurement_window": {"start": "2026-12-01T00:00:00Z", "end": "2026-11-01T00:00:00Z"}},
        {"measurement_window": {"start": "2026-11-22T00:00:00Z"}},
        {"unit": " "},
        {"notes": "x" * 501},
    ):
        with pytest.raises(OutcomeError):
            record_outcome(store, **outcome_args(approved, **over))


@pytest.mark.parametrize("ref", [
    {"source_registry_id": "source-1", "evidence_id": "latest", "content_hash": HASH},
    {"source_registry_id": "source-1", "evidence_id": "e1", "content_hash": "sha256:short"},
    {"source_registry_id": "source-1", "evidence_id": "e1"},
    {"source_registry_id": "source-1", "evidence_id": "e1", "content_hash": HASH, "url": "http://x"},
])
def test_source_reference_must_be_exact_and_immutable(tmp_path, ref):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomeError):
        record_outcome(store, **outcome_args(approved, source_ref=ref))


def test_simulated_output_cannot_be_an_observed_outcome(tmp_path):
    _, store, approved = approved_store(tmp_path)
    for cls in ("exploratory_simulation", "simulated", ""):
        with pytest.raises(OutcomeError, match="simulated output"):
            record_outcome(store, **outcome_args(approved, provenance_class=cls))
    with pytest.raises(OutcomeError, match="validation_status"):
        record_outcome(store, **outcome_args(approved, validation_status="trust_me"))
    assert store.outcomes(approved.decision_id, approved.version) == []


@pytest.mark.parametrize("role", ["approver", "reader", "reviewer"])
def test_only_operator_may_record(tmp_path, role):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomePermissionError):
        record_outcome(store, **outcome_args(approved, role=role))
    assert store.outcomes(approved.decision_id, approved.version) == []


def test_scope_and_subject_are_enforced(tmp_path):
    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomePermissionError, match="cross_scope"):
        record_outcome(store, **outcome_args(
            approved, subject={"subject_id": "recorder-1", "project_id": "other"}))
    with pytest.raises(OutcomeError, match="identify the acting principal"):
        record_outcome(store, **outcome_args(
            approved, subject={"subject_id": "someone-else", "project_id": "pilot-1"}))


def test_review_requires_distinct_reviewer_and_valid_transitions(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved))
    key = (approved.decision_id, approved.version, out["outcome_id"])
    with pytest.raises(OutcomeError, match="differ from the outcome's recorder"):
        review_outcome(store, *key, **review_args(
            reviewer="recorder-1", subject={"subject_id": "recorder-1", "project_id": "pilot-1"}))
    with pytest.raises(OutcomePermissionError):
        review_outcome(store, *key, **review_args(role="operator"))
    review_outcome(store, *key, **review_args(new_state="disputed", rationale_code="source_mismatch",
                                              rationale_text="free text stays in the store"))
    assert store.state(*key) == "disputed"
    with pytest.raises(OutcomeError, match="invalid outcome transition"):
        review_outcome(store, *key, **review_args(new_state="disputed"))
    review_outcome(store, *key, **review_args(new_state="reviewed"))
    assert store.state(*key) == "reviewed"
    history = store.reviews(*key)
    assert [(r["prior_state"], r["new_state"]) for r in history] == [
        ("recorded", "disputed"), ("disputed", "reviewed")]


def test_correction_appends_and_preserves_original(tmp_path):
    _, store, approved = approved_store(tmp_path)
    first = record_outcome(store, **outcome_args(approved))
    before = store.db.execute("SELECT payload_json FROM decision_outcomes").fetchone()[0]
    second = record_outcome(store, **outcome_args(
        approved, observed_value=43, supersedes_outcome_id=first["outcome_id"]))
    assert second["supersedes_outcome_id"] == first["outcome_id"]
    assert len(store.outcomes(approved.decision_id, approved.version)) == 2
    assert store.db.execute("SELECT payload_json FROM decision_outcomes ORDER BY rowid").fetchone()[0] == before
    with pytest.raises(OutcomeError):
        record_outcome(store, **outcome_args(approved, supersedes_outcome_id="missing"))



def test_correction_must_keep_decision_version_and_measure(tmp_path):
    _, store, approved = approved_store(tmp_path, measures=["observed follow-up", "retention"])
    first = record_outcome(store, **outcome_args(approved))
    with pytest.raises(OutcomeError, match="same measure"):
        record_outcome(store, **outcome_args(
            approved, measure="retention", supersedes_outcome_id=first["outcome_id"]))
    with pytest.raises(OutcomeError, match="same measure"):
        record_outcome(store, **outcome_args(
            approved, outcome_id=first["outcome_id"], supersedes_outcome_id=first["outcome_id"]))


def test_tables_are_append_only_and_ids_unique(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved, outcome_id="outcome-1"))
    review_outcome(store, approved.decision_id, approved.version, "outcome-1", **review_args())
    for sql in (
        "UPDATE decision_outcomes SET measure='x'", "DELETE FROM decision_outcomes",
        "UPDATE decision_outcome_reviews SET new_state='disputed'", "DELETE FROM decision_outcome_reviews",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.db.execute(sql)
    with pytest.raises(OutcomeError, match="already exists"):
        record_outcome(store, **outcome_args(approved, outcome_id="outcome-1"))
    assert out["outcome_id"] == "outcome-1"


def test_audit_events_carry_identifiers_only(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    out = record_outcome(store, **outcome_args(approved, notes=SECRET_NOTE, observed_value=987654), audit=audit)
    review_outcome(store, approved.decision_id, approved.version, out["outcome_id"],
                   **review_args(rationale_text=SECRET_NOTE), audit=audit)
    with pytest.raises(OutcomePermissionError):
        record_outcome(store, **outcome_args(approved, role="reader"), audit=audit)
    events = [json.loads(r[0]) for r in audit.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]
    assert [e["event_type"] for e in events] == [
        "decision_outcome_recorded", "decision_outcome_reviewed", "decision_outcome_denied"]
    assert events[0]["resource_ids"] == [approved.decision_id, f"version-{approved.version}", out["outcome_id"]]
    assert events[2]["decision"] == "deny"
    dumped = json.dumps(events)
    assert SECRET_NOTE not in dumped and "987654" not in dumped and "people" not in dumped
    assert audit.verify()["valid"] is True
    audit.close()


def test_audit_failure_is_visible_after_store_write(tmp_path):
    class Broken:
        def append(self, event):
            raise OSError("down")

    _, store, approved = approved_store(tmp_path)
    with pytest.raises(OutcomeError, match="audit event could not be appended"):
        record_outcome(store, **outcome_args(approved, outcome_id="o-1"), audit=Broken())
    assert store.get(approved.decision_id, approved.version, "o-1")["outcome_id"] == "o-1"


def test_public_role_string_outcome_apis_are_retired():
    import agora.decisions.outcomes as m
    for name in ("record_outcome", "review_outcome"):
        assert not hasattr(m, name), name
        assert name not in m.__all__
    assert {"record_outcome_as", "review_outcome_as"} <= set(m.__all__)

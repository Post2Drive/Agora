from __future__ import annotations

import sqlite3

import pytest

from agora import protection
from agora.audit_chain import AuditChainStore
from agora.decisions.outcomes import _record_outcome, _review_outcome, record_outcome_as
from agora.outcome_markers import (
    MarkerError, MarkerPermissionError, MarkerStore, acknowledge_as, check_source_hash_as,
    open_markers_as, outcome_ref, register_dependency_as, resolve_as, sweep_outcome_triggers_as,
    start_review_as, supersede_as,
)
from tests.test_decision_outcomes import HASH, approved_store, outcome_args, review_args
from tests.test_principal_outcomes import ADAPTER

NEW = "sha256:" + "cd" * 32
NOW = "2026-11-28T00:00:00Z"


def _setup(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = _record_outcome(store, **outcome_args(approved))
    ms = MarkerStore(store)
    scope = dict(decision_id=approved.decision_id, decision_version=approved.version, now=NOW)
    return store, ms, approved, out, scope


def _p(key):
    return ADAPTER.issue(key)


def _dispute(store, approved, out):
    _review_outcome(store, approved.decision_id, approved.version, out["outcome_id"],
                    **review_args(new_state="disputed"))


def test_dispute_creates_one_marker_and_flags_only_explicit_dependents(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    root = outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    register_dependency_as(ms, root, "report:r-1", principal=_p("op"), **scope)
    register_dependency_as(ms, "report:r-1", "decision:d-next/1", principal=_p("op"), **scope)
    _dispute(store, approved, out)
    made = sweep_outcome_triggers_as(ms, principal=_p("rev"), **scope)
    assert {m["affected_ref"] for m in made} == {root, "report:r-1", "decision:d-next/1"}
    chain = next(m for m in made if m["affected_ref"] == "decision:d-next/1")
    assert chain["dependency_path"] == [root, "report:r-1", "decision:d-next/1"]
    held = ms.held_refs()
    assert "report:r-1" in held and "report:unrelated" not in held and not ms.is_held("report:other")
    # outcome row itself untouched
    assert store.get(approved.decision_id, approved.version, out["outcome_id"]) == out


def test_sweep_is_idempotent(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    _dispute(store, approved, out)
    first = sweep_outcome_triggers_as(ms, principal=_p("rev"), **scope)
    again = sweep_outcome_triggers_as(ms, principal=_p("rev"), **scope)
    assert len(first) == 1 and again == []
    assert ms.db.execute("select count(*) from outcome_markers").fetchone()[0] == 1


def test_clean_outcome_opens_nothing(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    assert sweep_outcome_triggers_as(ms, principal=_p("rev"), **scope) == []


def test_correction_marks_superseded_outcome_only(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    new = _record_outcome(store, **outcome_args(approved, outcome_id="fix-1",
                                                supersedes_outcome_id=out["outcome_id"]))
    made = sweep_outcome_triggers_as(ms, principal=_p("rev"), **scope)
    assert [m["affected_ref"] for m in made] == [outcome_ref(approved.decision_id, approved.version, out["outcome_id"])]
    assert made[0]["trigger_type"] == "outcome_corrected"
    assert store.get(approved.decision_id, approved.version, new["outcome_id"])


def test_source_hash_change_flags_only_matching_source(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    other = _record_outcome(store, **outcome_args(approved, outcome_id="o-other", source_ref={
        "source_registry_id": "source-2", "evidence_id": "evidence-9", "content_hash": HASH}))
    assert check_source_hash_as(ms, "source-1", "evidence-1", HASH, principal=_p("rev"), **scope) == []
    made = check_source_hash_as(ms, "source-1", "evidence-1", NEW, principal=_p("rev"), **scope)
    refs = {m["affected_ref"] for m in made}
    assert outcome_ref(approved.decision_id, approved.version, out["outcome_id"]) in refs
    assert outcome_ref(approved.decision_id, approved.version, other["outcome_id"]) not in refs
    assert all(m["trigger_type"] == "source_hash_mismatch" for m in made)
    assert check_source_hash_as(ms, "source-1", "evidence-1", NEW, principal=_p("rev"), **scope) == []


def test_unknown_source_opens_nothing_and_bad_hash_rejected(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    assert check_source_hash_as(ms, "nope", "nope", NEW, principal=_p("rev"), **scope) == []
    with pytest.raises(MarkerError):
        check_source_hash_as(ms, "source-1", "evidence-1", "abc", principal=_p("rev"), **scope)


def test_cycle_and_duplicate_edges_terminate(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    register_dependency_as(ms, "report:a", "report:b", principal=_p("op"), **scope)
    register_dependency_as(ms, "report:b", "report:a", principal=_p("op"), **scope)
    register_dependency_as(ms, "report:a", "report:b", principal=_p("op"), **scope)
    made = open_markers_as(ms, "source_revoked", "report:a", "evt-1", principal=_p("rev"), **scope)
    assert sorted(m["affected_ref"] for m in made) == ["report:a", "report:b"]
    with pytest.raises(MarkerError):
        register_dependency_as(ms, "report:a", "report:a", principal=_p("op"), **scope)


def test_unresolvable_ref_gets_root_level_marker_only(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    made = open_markers_as(ms, "source_erased", "source:s/e/h", "evt-2", principal=_p("rev"), **scope)
    assert len(made) == 1 and made[0]["dependency_path"] == ["source:s/e/h"]


def test_input_validation(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    for kw in (dict(trigger_type="made_up", root_ref="report:a", trigger_event_id="e"),
               dict(trigger_type="source_revoked", root_ref="free text", trigger_event_id="e"),
               dict(trigger_type="source_revoked", root_ref="report:a", trigger_event_id="bad id!")):
        with pytest.raises(MarkerError):
            open_markers_as(ms, principal=_p("rev"), **kw, **scope)


def test_lifecycle_and_hold_release(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    m = open_markers_as(ms, "source_revoked", "report:a", "evt-3", principal=_p("rev"), **scope)[0]
    mid, fp = m["marker_id"], m["fingerprint"]
    assert ms.state(mid) == "open" and ms.is_held("report:a")
    with pytest.raises(MarkerError):  # cannot skip states
        resolve_as(ms, mid, disposition="still_valid", evidence_ref="ev-1", marker_fingerprint=fp,
                   principal=_p("rev"), now=NOW)
    acknowledge_as(ms, mid, principal=_p("rev"), now=NOW)
    start_review_as(ms, mid, principal=_p("rev"), now=NOW)
    with pytest.raises(MarkerError):  # wrong fingerprint
        resolve_as(ms, mid, disposition="still_valid", evidence_ref="ev-1", marker_fingerprint="x",
                   principal=_p("rev"), now=NOW)
    with pytest.raises(MarkerError):  # free-text evidence ref
        resolve_as(ms, mid, disposition="still_valid", evidence_ref="see my notes!", marker_fingerprint=fp,
                   principal=_p("rev"), now=NOW)
    resolve_as(ms, mid, disposition="remains_blocked", evidence_ref="ev-1", marker_fingerprint=fp,
               principal=_p("rev"), now=NOW)
    assert ms.state(mid) == "resolved" and ms.is_held("report:a")  # blocking disposition keeps the hold
    # resolved is terminal: no rewrite, a new trigger needs a new marker
    with pytest.raises(MarkerError):
        acknowledge_as(ms, mid, principal=_p("rev"), now=NOW)
    m2 = open_markers_as(ms, "source_revoked", "report:z", "evt-4", principal=_p("rev"), **scope)[0]
    for step in (acknowledge_as, start_review_as):
        step(ms, m2["marker_id"], principal=_p("rev"), now=NOW)
    resolve_as(ms, m2["marker_id"], disposition="still_valid", evidence_ref="ev-2",
               marker_fingerprint=m2["fingerprint"], principal=_p("rev"), now=NOW)
    assert not ms.is_held("report:z")


def test_supersede_needs_real_replacement(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    a = open_markers_as(ms, "source_revoked", "report:a", "e1", principal=_p("rev"), **scope)[0]
    b = open_markers_as(ms, "source_revoked", "report:b", "e2", principal=_p("rev"), **scope)[0]
    for bad in (a["marker_id"], "marker-missing"):
        with pytest.raises(MarkerError):
            supersede_as(ms, a["marker_id"], bad, principal=_p("rev"), now=NOW)
    supersede_as(ms, a["marker_id"], b["marker_id"], principal=_p("rev"), now=NOW)
    assert ms.state(a["marker_id"]) == "superseded" and not ms.is_held("report:a")


def test_recorder_cannot_resolve_marker_on_own_outcome(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)  # recorder-1 recorded the outcome
    root = outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    m = open_markers_as(ms, "outcome_disputed", root, "evt-5", principal=_p("rev"), **scope)[0]
    ADAPTER_BOTH = _p("both")  # subject recorder-1 with reviewer role
    with pytest.raises(MarkerError, match="differ from the recorder"):
        acknowledge_as(ms, m["marker_id"], principal=ADAPTER_BOTH, now=NOW)
    assert ms.state(m["marker_id"]) == "open"


@pytest.mark.parametrize("key", ["reader", "other", "expired", None])
def test_bad_principals_denied_with_no_state_change(tmp_path, key):
    store, ms, approved, out, scope = _setup(tmp_path)
    p = _p(key) if key else None
    with pytest.raises(MarkerPermissionError):
        open_markers_as(ms, "source_revoked", "report:a", "e", principal=p, **scope)
    with pytest.raises(MarkerPermissionError):
        register_dependency_as(ms, "report:a", "report:b", principal=p, **scope)
    assert ms.db.execute("select count(*) from outcome_markers").fetchone()[0] == 0
    assert ms.db.execute("select count(*) from outcome_dependency_edges").fetchone()[0] == 0


def test_role_boundaries(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    with pytest.raises(MarkerPermissionError):  # operator may not open/review markers
        open_markers_as(ms, "source_revoked", "report:a", "e", principal=_p("op"), **scope)
    with pytest.raises(MarkerPermissionError):  # reviewer may not register lineage
        register_dependency_as(ms, "report:a", "report:b", principal=_p("rev"), **scope)


def test_tables_are_append_only(tmp_path):
    store, ms, approved, out, scope = _setup(tmp_path)
    m = open_markers_as(ms, "source_revoked", "report:a", "e", principal=_p("rev"), **scope)[0]
    acknowledge_as(ms, m["marker_id"], principal=_p("rev"), now=NOW)
    register_dependency_as(ms, "report:a", "report:b", principal=_p("op"), **scope)
    for sql in ("UPDATE outcome_markers SET reason_code='x'", "DELETE FROM outcome_markers",
                "UPDATE outcome_dependency_edges SET dependent_ref='x'", "DELETE FROM outcome_dependency_edges",
                "DELETE FROM outcome_marker_events", "UPDATE outcome_marker_events SET actor='x'"):
        with pytest.raises(sqlite3.DatabaseError):
            ms.db.execute(sql)


@pytest.mark.protected_defaults
def test_protected_mode_requires_anchored_writer_and_audits_events(tmp_path):
    from agora.audit_anchor import AnchorRequiredError
    from tests.test_protected_defaults import _anchored
    store, ms, approved, out, scope = _setup(tmp_path)
    with pytest.raises(AnchorRequiredError):
        open_markers_as(ms, "source_revoked", "report:a", "e", principal=_p("rev"), audit=None, **scope)
    plain = AuditChainStore(tmp_path / "plain.sqlite3")
    with pytest.raises(AnchorRequiredError):
        open_markers_as(ms, "source_revoked", "report:a", "e", principal=_p("rev"), audit=plain, **scope)
    assert ms.db.execute("select count(*) from outcome_markers").fetchone()[0] == 0
    with _anchored(tmp_path) as writer:
        open_markers_as(ms, "source_revoked", "report:a", "e", principal=_p("rev"), audit=writer, **scope)
        with pytest.raises(MarkerPermissionError):
            open_markers_as(ms, "source_revoked", "report:a", "e2", principal=_p("reader"), audit=writer, **scope)
        evs = [r[0] for r in writer.chain.db.execute("SELECT event_json FROM audit_events")]
    assert any("outcome_marker_opened" in e for e in evs) and any("outcome_marker_denied" in e for e in evs)
    assert not any("report:a" in e or HASH in e for e in evs)  # opaque ids only

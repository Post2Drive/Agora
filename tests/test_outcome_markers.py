from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decisions.markers import (
    MarkerError, advance_marker_as, blocking_markers, flag_corrected_outcome_as, flag_disputed_outcome_as,
    flag_source_hash_mismatch_as, marker_view, outcome_ref, register_dependency_as, source_ref,
)
from agora.decisions.outcomes import OutcomePermissionError, record_outcome_as, review_outcome_as
from agora.principal import SyntheticFixtureAdapter
from tests.test_decision_outcomes import HASH, approved_store, outcome_args

EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)
NEW_HASH = "sha256:" + "cd" * 32
EVIDENCE = {"source_registry_id": "source-2", "evidence_id": "evidence-9", "content_hash": "sha256:" + "ef" * 32}


def _fx(sid, roles, **kw):
    base = {"subject_id": sid, "tenant_id": "t1", "project_ids": ["pilot-1"], "roles": roles,
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


ADAPTER = SyntheticFixtureAdapter({
    "op": _fx("recorder-1", ["operator"]),
    "rev": _fx("reviewer-9", ["reviewer"]),
    "rev2": _fx("reviewer-8", ["reviewer"]),
    "recorder_as_reviewer": _fx("recorder-1", ["reviewer"]),
    "reader": _fx("reader-1", ["reader"]),
    "other": _fx("rev-x", ["reviewer"], project_ids=["other"]),
})
NOW = "2026-11-27T00:00:00Z"


def _args(approved, **over):
    a = outcome_args(approved, **over)
    for k in ("recorder", "role", "subject"):
        a.pop(k)
    return a


def _disputed(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_args(approved))
    review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                      principal=ADAPTER.issue("rev"), new_state="disputed", rationale_code="later_evidence", now=NOW)
    return store, approved, out


def _anchored(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "anchor.jsonl", "c1")
    bootstrap_anchor(chain, anchors, performed_by="maint")
    return AnchoredAuditChain(chain, anchors)


def _edge(store, approved, root_type, root_ref, dtype, dref, dhash=None):
    return register_dependency_as(store, principal=ADAPTER.issue("op"), decision_id=approved.decision_id,
                                  decision_version=approved.version, root_type=root_type, root_ref=root_ref,
                                  dependent_type=dtype, dependent_ref=dref, dependent_hash=dhash, now=NOW)


def _flag(store, approved, out, who="rev", **kw):
    return flag_disputed_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                    principal=ADAPTER.issue(who), now=NOW, **kw)


def test_disputed_outcome_creates_exact_root_marker_and_no_other_state_changes(tmp_path):
    store, approved, out = _disputed(tmp_path)
    before = (store.get(approved.decision_id, approved.version, out["outcome_id"]),
              store.decisions.versions(approved.decision_id)[-1].status,
              store.db.execute("SELECT COUNT(*) FROM decision_outcomes").fetchone()[0])
    markers = _flag(store, approved, out)
    assert len(markers) == 1
    m = markers[0]
    assert m["trigger_type"] == "outcome_disputed" and m["state"] == "open"
    assert m["affected_ref"] == outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    after = (store.get(approved.decision_id, approved.version, out["outcome_id"]),
             store.decisions.versions(approved.decision_id)[-1].status,
             store.db.execute("SELECT COUNT(*) FROM decision_outcomes").fetchone()[0])
    assert before == after  # nothing rewritten


def test_not_disputed_outcome_is_not_flagged(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_args(approved))
    with pytest.raises(MarkerError, match="not currently disputed"):
        _flag(store, approved, out)


def test_explicit_dependents_are_flagged_with_path_and_unrelated_objects_are_not(tmp_path):
    store, approved, out = _disputed(tmp_path)
    root = outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    _edge(store, approved, "outcome", root, "report", "report-A", "sha256:" + "11" * 32)
    _edge(store, approved, "outcome", "outcome:other:1:zzz", "report", "report-UNRELATED")
    _edge(store, approved, "report", "report-A", "decision", "decision-next")  # transitive
    markers = _flag(store, approved, out)
    affected = {m["affected_ref"]: m for m in markers}
    assert set(affected) == {root, "report-A", "decision-next"}
    assert affected["decision-next"]["dependency_path"] == [f"outcome:{root}", "report:report-A", "decision:decision-next"]
    assert blocking_markers(store, "report", "report-UNRELATED") == []


def test_missing_edges_produce_only_a_root_level_marker(tmp_path):
    store, approved, out = _disputed(tmp_path)
    assert len(_flag(store, approved, out)) == 1


def test_duplicate_trigger_delivery_is_idempotent(tmp_path):
    store, approved, out = _disputed(tmp_path)
    first = _flag(store, approved, out)
    second = _flag(store, approved, out)
    assert [m["marker_id"] for m in first] == [m["marker_id"] for m in second]
    assert store.db.execute("SELECT COUNT(*) FROM outcome_markers").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM outcome_marker_events").fetchone()[0] == 1


def test_correction_marks_the_superseded_outcome_and_leaves_both_rows_intact(tmp_path):
    _, store, approved = approved_store(tmp_path)
    old = record_outcome_as(store, principal=ADAPTER.issue("op"), **_args(approved))
    new = record_outcome_as(store, principal=ADAPTER.issue("op"),
                            **_args(approved, supersedes_outcome_id=old["outcome_id"], observed_value=43))
    ms = flag_corrected_outcome_as(store, approved.decision_id, approved.version, new["outcome_id"],
                                   principal=ADAPTER.issue("rev"), now=NOW)
    assert ms[0]["trigger_type"] == "outcome_corrected"
    assert ms[0]["affected_ref"].endswith(old["outcome_id"])
    assert store.get(approved.decision_id, approved.version, old["outcome_id"])["observed_value"] == 42
    with pytest.raises(MarkerError, match="not a correction"):
        flag_corrected_outcome_as(store, approved.decision_id, approved.version, old["outcome_id"],
                                  principal=ADAPTER.issue("rev"), now=NOW)


def test_source_hash_mismatch_flags_only_objects_citing_that_exact_hash(tmp_path):
    _, store, approved = approved_store(tmp_path)
    out = record_outcome_as(store, principal=ADAPTER.issue("op"), **_args(approved))
    _edge(store, approved, "source", source_ref(HASH), "report", "cites-source")
    _edge(store, approved, "source", source_ref("sha256:" + "77" * 32), "report", "cites-other-source")
    with pytest.raises(MarkerError, match="matches the recorded"):
        flag_source_hash_mismatch_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                     current_content_hash=HASH, principal=ADAPTER.issue("rev"), now=NOW)
    ms = flag_source_hash_mismatch_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                      current_content_hash=NEW_HASH, principal=ADAPTER.issue("rev"), now=NOW)
    assert {m["affected_ref"] for m in ms} == {
        outcome_ref(approved.decision_id, approved.version, out["outcome_id"]), "cites-source"}
    assert all(m["trigger_type"] == "source_hash_mismatch" for m in ms)


def test_marker_tables_are_append_only(tmp_path):
    store, approved, out = _disputed(tmp_path)
    _flag(store, approved, out)
    _edge(store, approved, "outcome", "outcome:x:1:y", "report", "r")
    for sql in ("UPDATE outcome_markers SET severity='low'", "DELETE FROM outcome_markers",
                "UPDATE outcome_marker_events SET actor='x'", "DELETE FROM outcome_marker_events",
                "DELETE FROM marker_edges", "UPDATE marker_edges SET dependent_ref='z'"):
        with pytest.raises(Exception, match="append-only"):
            store.db.execute(sql)


def _lifecycle_ready(tmp_path):
    store, approved, out = _disputed(tmp_path)
    m = _flag(store, approved, out)[0]
    return store, approved, out, m


def _adv(store, m, state, who="rev2", **kw):
    cur = marker_view(store, m["marker_id"])
    return advance_marker_as(store, m["marker_id"], state, principal=ADAPTER.issue(who),
                             expected_fingerprint=cur["fingerprint"], expected_event_seq=cur["event_seq"],
                             now=NOW, **kw)


def test_full_lifecycle_and_blocking_semantics(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    assert blocking_markers(store, m["affected_type"], m["affected_ref"])
    _adv(store, m, "acknowledged")
    _adv(store, m, "under_review")
    # A "reviewed" outcome review does NOT resolve the marker.
    review_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                      principal=ADAPTER.issue("rev"), new_state="reviewed", rationale_code="rechecked", now=NOW)
    assert blocking_markers(store, m["affected_type"], m["affected_ref"])
    done = _adv(store, m, "resolved", disposition="needs_reissue", evidence_ref=EVIDENCE)
    assert done["state"] == "resolved" and blocking_markers(store, m["affected_type"], m["affected_ref"])  # still blocked
    # a valid disposition releases it
    store2, approved2, out2, m2 = _lifecycle_ready(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    for s in ("acknowledged", "under_review"):
        _adv(store2, m2, s)
    _adv(store2, m2, "resolved", disposition="valid", evidence_ref=EVIDENCE)
    assert blocking_markers(store2, m2["affected_type"], m2["affected_ref"]) == []


def test_invalid_transitions_and_bad_resolution_are_refused(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    with pytest.raises(MarkerError, match="invalid marker transition"):
        _adv(store, m, "resolved", disposition="valid", evidence_ref=EVIDENCE)
    with pytest.raises(MarkerError, match="only to resolution"):
        _adv(store, m, "acknowledged", disposition="valid")
    _adv(store, m, "acknowledged"); _adv(store, m, "under_review")
    with pytest.raises(MarkerError, match="disposition"):
        _adv(store, m, "resolved", evidence_ref=EVIDENCE)
    with pytest.raises(MarkerError, match="evidence"):
        _adv(store, m, "resolved", disposition="valid", evidence_ref={"evidence_id": "e"})
    with pytest.raises(MarkerError, match="evidence"):
        _adv(store, m, "resolved", disposition="valid", evidence_ref=EVIDENCE | {"content_hash": "latest"})


def test_stale_fingerprint_and_stale_history_are_refused(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    cur = marker_view(store, m["marker_id"])
    with pytest.raises(MarkerError, match="fingerprint"):
        advance_marker_as(store, m["marker_id"], "acknowledged", principal=ADAPTER.issue("rev2"),
                          expected_fingerprint="sha256:" + "00" * 32, expected_event_seq=cur["event_seq"], now=NOW)
    _adv(store, m, "acknowledged")
    with pytest.raises(MarkerError, match="stale marker event history"):
        advance_marker_as(store, m["marker_id"], "under_review", principal=ADAPTER.issue("rev2"),
                          expected_fingerprint=cur["fingerprint"], expected_event_seq=cur["event_seq"], now=NOW)


def test_recorder_cannot_act_on_its_own_outcome_marker(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    with pytest.raises(MarkerError, match="recorder"):
        _adv(store, m, "acknowledged", who="recorder_as_reviewer")
    assert marker_view(store, m["marker_id"])["state"] == "open"


@pytest.mark.parametrize("who", ["reader", "other", "op", None])
def test_bad_principals_are_denied_for_flagging_and_lifecycle(tmp_path, who):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    p = ADAPTER.issue(who) if who else None
    with pytest.raises(OutcomePermissionError):
        flag_disputed_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                 principal=p, now=NOW)
    cur = marker_view(store, m["marker_id"])
    with pytest.raises(OutcomePermissionError):
        advance_marker_as(store, m["marker_id"], "acknowledged", principal=p,
                          expected_fingerprint=cur["fingerprint"], expected_event_seq=cur["event_seq"], now=NOW)
    assert marker_view(store, m["marker_id"])["state"] == "open"


def test_supersession_requires_a_different_existing_replacement(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    with pytest.raises(MarkerError, match="replacement"):
        _adv(store, m, "superseded")
    with pytest.raises(MarkerError, match="not found"):
        _adv(store, m, "superseded", replacement_marker_id="marker-missing")
    _, _, _, other = _lifecycle_ready(tmp_path / "c" if (tmp_path / "c").mkdir() is None else tmp_path)
    store.db.execute("SELECT 1")  # replacement must exist in THIS store
    with pytest.raises(MarkerError):
        _adv(store, m, "superseded", replacement_marker_id=m["marker_id"])


def test_audit_events_are_allow_listed_anchored_and_free_of_values(tmp_path):
    store, approved, out = _disputed(tmp_path)
    audit = _anchored(tmp_path)
    m = flag_disputed_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                 principal=ADAPTER.issue("rev"), audit=audit, now=NOW)[0]
    _adv(store, m, "acknowledged", audit=audit)
    rows = [json.loads(r[0]) for r in audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]
    assert [e["event_type"] for e in rows] == ["decision_marker_opened", "decision_marker_acknowledged"]
    blob = json.dumps(rows)
    assert "observed_value" not in blob and "people" not in blob and "later_evidence" not in blob
    assert rows[0]["resource_ids"][-1] == m["marker_id"] and audit.verify()["valid"] is True


def test_audit_failure_is_visible_and_marker_stays_stored(tmp_path):
    store, approved, out = _disputed(tmp_path)

    class Broken:
        def append(self, event):
            raise OSError("down")
    with pytest.raises(MarkerError, match="audit event could not be appended"):
        flag_disputed_outcome_as(store, approved.decision_id, approved.version, out["outcome_id"],
                                 principal=ADAPTER.issue("rev"), audit=Broken(), now=NOW)
    assert store.db.execute("SELECT COUNT(*) FROM outcome_markers").fetchone()[0] == 1


def test_edges_reject_self_dependency_bad_types_and_unscoped_principals(tmp_path):
    store, approved, out = _disputed(tmp_path)
    with pytest.raises(MarkerError):
        _edge(store, approved, "outcome", "x", "outcome", "x")
    with pytest.raises(MarkerError):
        _edge(store, approved, "banana", "x", "report", "y")
    with pytest.raises(OutcomePermissionError):
        register_dependency_as(store, principal=ADAPTER.issue("other"), decision_id=approved.decision_id,
                               decision_version=approved.version, root_type="outcome", root_ref="a",
                               dependent_type="report", dependent_ref="b", now=NOW)


def test_cycles_in_edges_terminate(tmp_path):
    store, approved, out = _disputed(tmp_path)
    root = outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    _edge(store, approved, "outcome", root, "report", "A")
    _edge(store, approved, "report", "A", "decision", "B")
    _edge(store, approved, "decision", "B", "report", "A")  # cycle back
    assert {m["affected_ref"] for m in _flag(store, approved, out)} == {root, "A", "B"}


class _BrokenAudit:
    def append(self, event):
        raise OSError("down")


def _clone_marker(store, m, suffix="dup"):
    """A second marker on the SAME decision version and affected object (distinct id and key)."""
    row = list(store.db.execute("SELECT * FROM outcome_markers WHERE marker_id=?", (m["marker_id"],)).fetchone())
    row[0], row[1] = f"marker-{suffix}", f"key-{suffix}"
    store.db.execute("INSERT INTO outcome_markers VALUES (" + ",".join("?" * len(row)) + ")", row)
    store.db.execute("INSERT INTO outcome_marker_events VALUES (?,?,?,?,?,?,?,?,?)",
                     (f"marker-{suffix}", 1, "none", "open", "x", NOW, None, None, None))
    store.db.commit()
    return marker_view(store, f"marker-{suffix}")


@pytest.mark.parametrize("path", ["acknowledged", "resolved_valid", "superseded"])
def test_broken_audit_leaves_prior_blocking_state_and_no_event(tmp_path, path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    repl = _clone_marker(store, m)
    if path == "resolved_valid":
        _adv(store, m, "acknowledged")
        _adv(store, m, "under_review")
    before = marker_view(store, m["marker_id"])
    kw = {"acknowledged": {}, "resolved_valid": {"disposition": "valid", "evidence_ref": EVIDENCE},
          "superseded": {"replacement_marker_id": repl["marker_id"], "supersession_reason": "replaced_by_clone"}}[path]
    state = "resolved" if path == "resolved_valid" else path
    with pytest.raises(MarkerError, match="audit event could not be appended"):
        _adv(store, m, state, audit=_BrokenAudit(), **kw)
    after = marker_view(store, m["marker_id"])
    assert (after["state"], after["event_seq"]) == (before["state"], before["event_seq"])
    assert blocking_markers(store, m["affected_type"], m["affected_ref"])


def test_supersession_replacement_must_match_scope_and_carry_a_reason(tmp_path):
    store, approved, out, m = _lifecycle_ready(tmp_path)
    root = outcome_ref(approved.decision_id, approved.version, out["outcome_id"])
    _edge(store, approved, "outcome", root, "report", "A")
    other = [x for x in _flag(store, approved, out) if x["affected_ref"] == "A"][0]
    with pytest.raises(MarkerError, match="same decision version and affected object"):
        _adv(store, m, "superseded", replacement_marker_id=other["marker_id"], supersession_reason="wrong_target")
    twin = _clone_marker(store, m)
    for bad in (None, "", "Bad Reason", "x" * 80):
        with pytest.raises(MarkerError, match="bounded reason"):
            _adv(store, m, "superseded", replacement_marker_id=twin["marker_id"], supersession_reason=bad)
    with pytest.raises(MarkerError, match="only to supersession"):
        _adv(store, m, "acknowledged", supersession_reason="stray_reason")
    done = _adv(store, m, "superseded", replacement_marker_id=twin["marker_id"],
                supersession_reason="replaced_by_twin")
    assert done["state"] == "superseded"
    ev = store.db.execute("SELECT evidence_json FROM outcome_marker_events WHERE marker_id=? ORDER BY seq DESC",
                          (m["marker_id"],)).fetchone()[0]
    assert json.loads(ev) == {"supersession_reason": "replaced_by_twin"}

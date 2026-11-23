from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from agora import reconcile as rc
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import propose
from agora.decisions.store import DecisionRecordStore
from tests.test_decision_approval import draft_record

NOW = "2026-11-21T10:00:00Z"


def _setup(tmp_path, *, audited=True):
    audit = AuditChainStore(tmp_path / "audit.sqlite3")
    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    propose(store, "decision-approval-001", 1, actor="analyst", now=NOW,
            audit=audit if audited else None)
    return store, audit


def _anchor(tmp_path):
    """Fresh clean sidecar anchor for the chain as it stands (simulates a clean anchored pair)."""
    from agora.audit_anchor import AnchorStore, bootstrap_anchor
    (tmp_path / "anchor.jsonl").unlink(missing_ok=True)
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    bootstrap_anchor(chain, AnchorStore(tmp_path / "anchor.jsonl", "c1"), performed_by="maint")
    chain.close()


def _run(tmp_path, anchor=True):
    if anchor:
        _anchor(tmp_path)
    return rc.reconcile(tmp_path / "decisions.db", tmp_path / "audit.sqlite3",
                        anchor_path=tmp_path / "anchor.jsonl", chain_id="c1")


def _rewrite_chain(audit, mutate):
    """Rewrite audit rows with a valid hash chain (an attacker-free test helper)."""
    rows = audit.db.execute("SELECT event_json FROM audit_events ORDER BY seq").fetchall()
    events = mutate([json.loads(r[0]) for r in rows])
    audit.db.execute("DROP TRIGGER protect_audit_event_update")
    audit.db.execute("DROP TRIGGER protect_audit_event_delete")
    audit.db.execute("DELETE FROM audit_events")
    prev = "0" * 64
    for n, ev in enumerate(events, 1):
        raw = json.dumps(ev, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        h = hashlib.sha256(json.dumps({"previous_hash": prev, "event": ev}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        audit.db.execute("INSERT INTO audit_events(event_id,previous_hash,event_json,event_hash,recorded_at)"
                         " VALUES (?,?,?,?,?)", (ev["event_id"], prev, raw, h, ev["recorded_at"]))
        prev = h
    audit.db.commit()


def test_matched_transition_is_intact(tmp_path):
    store, audit = _setup(tmp_path)
    report = _run(tmp_path)
    assert report["intact"] is True
    assert report["counts"]["matched"] == 1 and report["findings"] == []


def test_transition_without_audit_event_is_missing(tmp_path):
    _setup(tmp_path, audited=False)
    report = _run(tmp_path)
    assert report["intact"] is False
    assert report["counts"]["missing"] == 1
    assert report["findings"][0] == {
        "status": "missing", "code": "AUDIT_EVENT_MISSING", "decision_id": "decision-approval-001",
        "version": 2, "transition": "proposed"}


def test_event_for_other_version_does_not_match(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "resource_ids": [e["resource_ids"][0], "version-9"]} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["missing"] == 1 and report["counts"]["orphan"] == 1


def test_event_for_other_decision_does_not_match(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "resource_ids": ["other-decision", e["resource_ids"][1]]} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["missing"] == 1 and report["counts"]["orphan"] == 1


def test_fingerprint_mismatch_is_conflict(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "decision_fingerprint": "f" * 64} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["conflict"] == 1
    assert report["findings"][0]["code"] == "AUDIT_EVENT_MISMATCH"


def test_actor_mismatch_is_conflict(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "subject_id": "someone-else"} for e in evs])
    assert _run(tmp_path)["counts"]["conflict"] == 1


def test_duplicate_events_are_conflict(tmp_path):
    store, audit = _setup(tmp_path)
    def dup(evs):
        return evs + [{**evs[0], "event_id": "dup-1"}]
    _rewrite_chain(audit, dup)
    report = _run(tmp_path)
    assert report["counts"]["conflict"] == 1
    assert report["findings"][0]["code"] == "DUPLICATE_AUDIT_EVENTS"


def test_orphan_audit_event_is_surfaced_not_deleted(tmp_path):
    store, audit = _setup(tmp_path)
    audit.append({"event_id": "x1", "event_type": "decision_approved", "subject_id": "a",
                  "resource_ids": ["ghost-decision", "version-3"], "decision_fingerprint": "a" * 64})
    before = audit.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    report = _run(tmp_path)
    assert report["counts"]["orphan"] == 1
    assert audit.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == before


def test_non_lifecycle_events_are_not_orphans(tmp_path):
    store, audit = _setup(tmp_path)
    audit.append({"event_id": "d1", "event_type": "decision_approval_denied", "subject_id": "a",
                  "resource_ids": ["decision-approval-001", "version-2"]})
    audit.append({"event_id": "i1", "event_type": "import", "count": 1})
    assert _run(tmp_path)["intact"] is True


def test_invalid_chain_blocks_classification(tmp_path):
    store, audit = _setup(tmp_path, audited=False)  # would otherwise report 'missing'
    audit.append({"event_id": "e1", "event_type": "import"})
    audit.append({"event_id": "e2", "event_type": "import"})
    _anchor(tmp_path)
    audit.db.execute("DROP TRIGGER protect_audit_event_update")
    audit.db.execute("UPDATE audit_events SET event_json=? WHERE seq=2",
                     (json.dumps({"event_id": "e2", "event_type": "tampered"}),))
    audit.db.commit()
    with pytest.raises(rc.ReconcileBlocked) as err:
        _run(tmp_path, anchor=False)
    assert err.value.code == "CHAIN_INVALID"


def test_missing_store_is_blocked_and_not_created(tmp_path):
    with pytest.raises(rc.ReconcileBlocked) as err:
        rc.reconcile(tmp_path / "nope.db", tmp_path / "nope2.db", anchor_path=tmp_path / "a", chain_id="c1")
    assert err.value.code == "STORE_NOT_FOUND"
    assert not (tmp_path / "nope.db").exists() and not (tmp_path / "nope2.db").exists()


def test_source_fingerprint_mismatch_is_source_invalid(tmp_path):
    store, audit = _setup(tmp_path)
    store.db.execute("DROP TRIGGER protect_decision_approval_event_update")
    store.db.execute("UPDATE decision_approval_events SET decision_fingerprint='bad'")
    store.db.commit()
    report = _run(tmp_path)
    assert report["counts"]["source_invalid"] == 1


def test_version_gap_is_source_invalid(tmp_path):
    store, audit = _setup(tmp_path)
    store.db.execute("DROP TRIGGER protect_decision_record_update")
    store.db.execute("UPDATE decision_records SET version=5 WHERE version=2")
    store.db.commit()
    report = _run(tmp_path)
    assert any(f["code"] == "VERSION_HISTORY_GAP" for f in report["findings"])


def test_scan_is_read_only_and_deterministic(tmp_path):
    _setup(tmp_path, audited=False)
    paths = [tmp_path / "decisions.db", tmp_path / "audit.sqlite3"]
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    first, second = _run(tmp_path), _run(tmp_path)
    assert first == second
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_report_has_no_free_text(tmp_path):
    _setup(tmp_path, audited=False)
    assert "synthetic pilot cohort" not in json.dumps(_run(tmp_path))


def test_cli_exit_codes_and_wording(tmp_path, capsys):
    from agora import cli
    _setup(tmp_path, audited=False)
    _anchor(tmp_path)
    args = ["reconcile", "--decisions", str(tmp_path / "decisions.db"), "--audit", str(tmp_path / "audit.sqlite3"),
            "--anchor", str(tmp_path / "anchor.jsonl"), "--chain-id", "c1"]
    assert cli.main(args) == 1
    out = capsys.readouterr().out
    assert "AUDIT_EVENT_MISSING" in out and "does not repair" in out
    assert cli.main(["reconcile", "--decisions", str(tmp_path / "x"), "--audit", str(tmp_path / "y"),
                     "--anchor", str(tmp_path / "z"), "--chain-id", "c1"]) == 2
    assert "RECONCILE_BLOCKED: STORE_NOT_FOUND" in capsys.readouterr().err


def test_cli_ok_exit_zero(tmp_path, capsys):
    from agora import cli
    _setup(tmp_path)
    _anchor(tmp_path)
    args = ["reconcile", "--decisions", str(tmp_path / "decisions.db"), "--audit", str(tmp_path / "audit.sqlite3"),
            "--anchor", str(tmp_path / "anchor.jsonl"), "--chain-id", "c1"]
    assert cli.main(args) == 0
    assert "OK:" in capsys.readouterr().out


def test_reconcile_dispatch_does_not_load_engine():
    import subprocess, sys
    code = ("import sys\nfrom agora import cli\n"
            "try:\n    cli.main(['reconcile','--help'])\nexcept SystemExit:\n    pass\n"
            "print('agora.sim.engine' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
    assert out.splitlines()[-1] == "False"


def test_event_of_wrong_transition_type_does_not_match(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "event_type": "decision_rejected"} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["missing"] == 1 and report["counts"]["orphan"] == 1


def _mutate_event(tmp_path, column, value):
    store, audit = _setup(tmp_path)
    store.db.execute("DROP TRIGGER protect_decision_approval_event_update")
    store.db.execute(f"UPDATE decision_approval_events SET {column}=?", (value,))
    store.db.commit()
    return _run(tmp_path)


@pytest.mark.parametrize("column,value,code", [
    ("transition", "rejected", "TRANSITION_STATUS_MISMATCH"),
    ("actor", "intruder", "ACTOR_MISMATCH"),
    ("method", "other-method", "METHOD_MISMATCH"),
    ("occurred_at", "2020-01-01T00:00:00Z", "TIMESTAMP_MISMATCH"),
])
def test_source_metadata_mismatch_is_source_invalid(tmp_path, column, value, code):
    report = _mutate_event(tmp_path, column, value)
    assert report["intact"] is False
    assert report["counts"]["source_invalid"] == 1
    assert [f["code"] for f in report["findings"] if f["status"] == "source_invalid"] == [code]


def test_wrong_audit_operation_is_conflict(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "operation": "decision_approval"} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["conflict"] == 1 and report["findings"][0]["code"] == "AUDIT_EVENT_MISMATCH"


def test_extra_resource_ids_is_conflict(tmp_path):
    store, audit = _setup(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "resource_ids": e["resource_ids"] + ["extra"]} for e in evs])
    report = _run(tmp_path)
    assert report["counts"]["conflict"] == 1 and report["findings"][0]["code"] == "AUDIT_EVENT_MISMATCH"


def test_partial_open_closes_audit_connection(tmp_path, monkeypatch):
    _setup(tmp_path)
    _anchor(tmp_path)
    opened = []
    real = rc._ro

    def tracking(path):
        conn = real(path)
        opened.append(conn)
        return conn

    monkeypatch.setattr(rc, "_ro", tracking)
    with pytest.raises(rc.ReconcileBlocked) as err:
        rc.reconcile(tmp_path / "missing.db", tmp_path / "audit.sqlite3", anchor_path=tmp_path / "anchor.jsonl", chain_id="c1")
    assert err.value.code == "STORE_NOT_FOUND"
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


# --- sidecar-anchor verification (M1): classify only an anchored_verified chain ---

def _blocked(tmp_path, **kw):
    args = dict(anchor_path=tmp_path / "anchor.jsonl", chain_id="c1") | kw
    with pytest.raises(rc.ReconcileBlocked) as err:
        rc.reconcile(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", **args)
    return err.value.code


def _snapshot(tmp_path):
    return [hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
            for p in (tmp_path / "decisions.db", tmp_path / "audit.sqlite3", tmp_path / "anchor.jsonl")]


def test_anchored_pair_is_classified(tmp_path):
    _setup(tmp_path)
    assert _run(tmp_path)["intact"] is True


def test_missing_anchor_blocks_and_is_not_created(tmp_path):
    _setup(tmp_path)
    assert _blocked(tmp_path) == "ANCHOR_INVALID"
    assert not (tmp_path / "anchor.jsonl").exists()


def test_malformed_anchor_blocks(tmp_path):
    _setup(tmp_path)
    (tmp_path / "anchor.jsonl").write_text("not json\n", encoding="utf-8")
    assert _blocked(tmp_path) == "ANCHOR_INVALID"


def test_wrong_chain_id_blocks(tmp_path):
    _setup(tmp_path)
    _anchor(tmp_path)
    assert _blocked(tmp_path, chain_id="other-chain") == "ANCHOR_INVALID"


def test_unanchored_tail_blocks_without_classifying(tmp_path):
    store, audit = _setup(tmp_path, audited=False)
    _anchor(tmp_path)
    audit.append({"event_id": "late", "event_type": "import"})
    before = _snapshot(tmp_path)
    assert _blocked(tmp_path) == "ANCHOR_UNANCHORED_TAIL"
    assert before == _snapshot(tmp_path)


def test_truncated_chain_blocks(tmp_path):
    store, audit = _setup(tmp_path)
    audit.append({"event_id": "e2", "event_type": "import"})
    _anchor(tmp_path)
    audit.db.execute("DROP TRIGGER protect_audit_event_delete")
    audit.db.execute("DELETE FROM audit_events WHERE seq=2")
    audit.db.commit()
    assert _blocked(tmp_path) == "ANCHOR_TRUNCATION"


def test_rewritten_history_with_valid_hashes_is_anchor_mismatch(tmp_path):
    store, audit = _setup(tmp_path)
    _anchor(tmp_path)
    _rewrite_chain(audit, lambda evs: [{**e, "reason": "doctored"} for e in evs])  # chain self-consistent
    assert _blocked(tmp_path) == "ANCHOR_MISMATCH"


def test_reconcile_never_bootstraps_or_writes(tmp_path):
    _setup(tmp_path, audited=False)
    _anchor(tmp_path)
    before = _snapshot(tmp_path)
    _run(tmp_path, anchor=False)
    assert before == _snapshot(tmp_path)


def test_cli_requires_anchor_arguments(tmp_path, capsys):
    from agora import cli
    _setup(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["reconcile", "--decisions", str(tmp_path / "decisions.db"), "--audit", str(tmp_path / "audit.sqlite3")])
    assert exc.value.code == 2
    assert cli.main(["reconcile", "--decisions", str(tmp_path / "decisions.db"), "--audit",
                     str(tmp_path / "audit.sqlite3"), "--anchor", str(tmp_path / "anchor.jsonl"),
                     "--chain-id", "c1"]) == 2
    assert "RECONCILE_BLOCKED: ANCHOR_INVALID" in capsys.readouterr().err


def test_anchor_verification_opens_audit_read_only(tmp_path, monkeypatch):
    import sqlite3
    _setup(tmp_path)
    _anchor(tmp_path)
    uris = []
    real = sqlite3.connect

    def spy(target, *a, **k):
        uris.append(str(target))
        return real(target, *a, **k)

    monkeypatch.setattr(sqlite3, "connect", spy)
    _run(tmp_path, anchor=False)
    # audit is now read via a held-descriptor snapshot (":memory:" + deserialize); any path open stays mode=ro
    assert uris and all(u == ":memory:" or "mode=ro" in u for u in uris)
    assert not any("audit.sqlite3" in u and "mode=ro" not in u for u in uris)


def test_concurrent_append_is_blocked_between_verification_and_classification(tmp_path, monkeypatch):
    """A writer racing the two phases must wait for the anchor lock; the verdict covers one snapshot."""
    import threading
    import time
    from agora.audit_anchor import AnchoredAuditChain, AnchorStore
    store, audit = _setup(tmp_path)
    audit.close()
    _anchor(tmp_path)
    done = threading.Event()

    def _append():
        chain = AuditChainStore(tmp_path / "audit.sqlite3")  # sqlite objects are per-thread
        anchored = AnchoredAuditChain(chain, AnchorStore(tmp_path / "anchor.jsonl", "c1"))
        anchored.append({"event_id": "late-1", "event_type": "decision_approved", "subject_id": "x",
                         "resource_ids": ["d", "version-1"]})
        done.set()

    worker = threading.Thread(target=_append, daemon=True)
    real_ro, state = rc._ro, {"started": False}

    def racing_ro(path):
        if not state["started"]:  # first classification read: verification has already passed
            state["started"] = True
            worker.start()
            time.sleep(0.5)
            state["finished_early"] = done.is_set()
        return real_ro(path)

    monkeypatch.setattr(rc, "_ro", racing_ro)
    report = rc.reconcile(tmp_path / "decisions.db", tmp_path / "audit.sqlite3",
                          anchor_path=tmp_path / "anchor.jsonl", chain_id="c1")
    assert state["started"] and state["finished_early"] is False
    worker.join(timeout=20)
    assert done.is_set()  # the append proceeds only after reconciliation released the lock
    assert report is not None

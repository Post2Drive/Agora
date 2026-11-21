from __future__ import annotations

import json
import shutil

import pytest

from agora.audit_anchor import (
    AnchorError, AnchoredAuditChain, AnchorRequiredError, AnchorStore, AnchorWriteError,
    bootstrap_anchor, verify_anchored,
)
from agora.audit_chain import AuditChainStore


def _evt(i):
    return {"event_id": f"e{i}", "event_type": "t", "subject_id": "u", "operation": "import", "decision": "allow"}


def _setup(tmp_path, events=0):
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    for i in range(events):
        chain.append(_evt(i))
    anchors = AnchorStore(tmp_path / "anchors" / "a.jsonl", "chain-1")
    bootstrap_anchor(chain, anchors, performed_by="maint-1")
    return chain, anchors, AnchoredAuditChain(chain, anchors)


def _raw_truncate(chain, keep):
    chain.db.execute("DROP TRIGGER protect_audit_event_delete")
    chain.db.execute("DELETE FROM audit_events WHERE seq>?", (keep,))
    chain.db.commit()


def test_valid_chain_and_anchor_verify_and_anchor_is_separate_file(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    for i in range(3):
        anchored.append(_evt(i))
    out = anchored.verify()
    assert out["valid"] and out["status"] == "anchored_verified" and out["trust_level"] == "local_sidecar"
    assert anchors.path != chain.path
    assert len(anchors.read()) == 4  # bootstrap + 3 appends
    tables = {r[0] for r in chain.db.execute("SELECT name FROM sqlite_master")}
    assert not any("anchor" in t for t in tables)  # anchor is not stored in the chain DB


def test_truncation_of_newest_events_is_detected(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    for i in range(4):
        anchored.append(_evt(i))
    _raw_truncate(chain, 2)
    assert chain.verify()["valid"] is True  # the hash chain alone cannot see this
    assert verify_anchored(chain, anchors)["status"] == "truncation_detected"


def test_hash_mismatch_at_anchored_sequence_is_detected(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    for i in range(3):
        anchored.append(_evt(i))
    # Replace the last event with a different, self-consistent one at the same seq.
    _raw_truncate(chain, 2)
    chain.append(_evt(99))
    out = verify_anchored(chain, anchors)
    assert out["status"] == "anchor_mismatch" and out["valid"] is False


def test_unanchored_tail_fails_closed_and_blocks_protected_appends(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    chain.append(_evt(1))  # crash window: chain advanced, anchor did not
    assert verify_anchored(chain, anchors)["status"] == "unanchored_tail"
    with pytest.raises(AnchorRequiredError):
        anchored.append(_evt(2))
    assert chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 2  # nothing added or removed


@pytest.mark.parametrize("damage", ["missing", "malformed", "wrong_chain", "tampered", "torn", "empty"])
def test_missing_or_invalid_anchor_history_fails_closed(tmp_path, damage):
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    path = anchors.path
    text = path.read_text()
    if damage == "missing":
        path.unlink()
    elif damage == "malformed":
        path.write_text("not json\n")
    elif damage == "wrong_chain":
        anchors = AnchorStore(path, "other-chain")
    elif damage == "tampered":
        path.write_text(text.replace('"sequence":1', '"sequence":5'))
    elif damage == "torn":
        path.write_text(text[:-20])
    elif damage == "empty":
        path.write_text("")
    out = verify_anchored(chain, anchors)
    assert out["valid"] is False and out["status"] == "anchor_invalid"
    assert not (damage == "missing" and path.exists())  # verifier did not auto-create it


def test_deleted_middle_record_breaks_history_linkage(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    for i in range(3):
        anchored.append(_evt(i))
    lines = anchors.path.read_text().splitlines()
    anchors.path.write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n")
    assert verify_anchored(chain, anchors)["status"] == "anchor_invalid"


def test_chain_integrity_failure_reported_even_with_anchor(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    chain.db.execute("DROP TRIGGER protect_audit_event_update")
    chain.db.execute("UPDATE audit_events SET event_json=? WHERE seq=1", ('{"event_id":"e0","x":1}',))
    chain.db.commit()
    assert verify_anchored(chain, anchors)["status"] == "chain_integrity_failure"


def test_anchor_sequence_cannot_move_backward_or_repeat(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    for i in range(2):
        anchored.append(_evt(i))
    for seq in (0, 1, 2):
        with pytest.raises(AnchorError, match="increase"):
            anchors.advance(seq, "ab" * 32)


def test_anchor_write_failure_raises_dedicated_error_and_preserves_event(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")
    anchors.advance = boom
    with pytest.raises(AnchorWriteError):
        anchored.append(_evt(0))
    assert chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 1
    assert verify_anchored(chain, anchors)["status"] == "unanchored_tail"


def test_restart_after_chain_append_before_anchor_detects_tail(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    chain.append(_evt(1))
    chain.close()
    reopened = AuditChainStore(tmp_path / "chain.sqlite3")
    assert verify_anchored(reopened, AnchorStore(anchors.path, "chain-1"))["status"] == "unanchored_tail"


def test_bootstrap_refuses_invalid_chain_and_existing_history_and_records_metadata(tmp_path):
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    chain.append(_evt(0))
    chain.db.execute("DROP TRIGGER protect_audit_event_update")
    chain.db.execute("UPDATE audit_events SET event_json=? WHERE seq=1", ('{"event_id":"e0","x":1}',))
    chain.db.commit()
    anchors = AnchorStore(tmp_path / "a.jsonl", "chain-1")
    with pytest.raises(AnchorError, match="integrity"):
        bootstrap_anchor(chain, anchors, performed_by="maint-1")
    assert not anchors.path.exists()  # nothing written for a bad chain

    ok = tmp_path / "ok"
    ok.mkdir()
    good, good_anchors, _ = _setup(ok)
    first = good_anchors.read()[0]
    assert first["kind"] == "bootstrap" and first["performed_by"] == "maint-1"
    with pytest.raises(AnchorError, match="already exists"):
        bootstrap_anchor(good, good_anchors, performed_by="maint-2")
    with pytest.raises(AnchorError, match="performed_by"):
        bootstrap_anchor(good, AnchorStore(tmp_path / "other.jsonl", "chain-1"), performed_by=" ")


def test_verifier_does_not_mutate_either_store(tmp_path):
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    chain.append(_evt(1))
    before_anchor = anchors.path.read_bytes()
    before_chain = chain.db.execute("SELECT * FROM audit_events").fetchall()
    verify_anchored(chain, anchors)
    assert anchors.path.read_bytes() == before_anchor
    assert chain.db.execute("SELECT * FROM audit_events").fetchall() == before_chain


def test_unwritable_anchor_location_fails_closed(tmp_path):
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not directory")
    anchors = AnchorStore(blocker / "a.jsonl", "chain-1")
    with pytest.raises((OSError, AnchorError)):
        bootstrap_anchor(chain, anchors, performed_by="maint-1")
    assert verify_anchored(chain, anchors)["status"] == "anchor_invalid"


def test_local_sidecar_limitation_consistent_older_pair_is_not_detected(tmp_path):
    """Documented residual risk: replacing BOTH stores with an older consistent pair passes."""
    chain, anchors, anchored = _setup(tmp_path)
    anchored.append(_evt(0))
    chain.db.commit()
    shutil.copy(tmp_path / "chain.sqlite3", tmp_path / "old-chain.sqlite3")
    shutil.copy(anchors.path, tmp_path / "old-anchor.jsonl")
    for i in range(1, 4):
        anchored.append(_evt(i))
    chain.close()
    shutil.copy(tmp_path / "old-chain.sqlite3", tmp_path / "chain.sqlite3")
    shutil.copy(tmp_path / "old-anchor.jsonl", anchors.path)
    rolled = AuditChainStore(tmp_path / "chain.sqlite3")
    out = verify_anchored(rolled, AnchorStore(anchors.path, "chain-1"))
    assert out["valid"] is True and out["trust_level"] == "local_sidecar"


def _worker(chain_path, anchor_path, worker, count):
    from agora.audit_anchor import AnchoredAuditChain, AnchorStore
    from agora.audit_chain import AuditChainStore
    chain = AuditChainStore(chain_path)
    wrapped = AnchoredAuditChain(chain, AnchorStore(anchor_path, "c1"))
    for i in range(count):
        wrapped.append({"event_id": f"w{worker}-{i}", "event_type": "t"})
    wrapped.close()


def test_concurrent_processes_keep_chain_and_anchor_consistent(tmp_path):
    import multiprocessing
    from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
    from agora.audit_chain import AuditChainStore
    cp, ap = str(tmp_path / "c.db"), str(tmp_path / "a.jsonl")
    chain = AuditChainStore(cp)
    bootstrap_anchor(chain, AnchorStore(ap, "c1"), performed_by="test")
    chain.close()
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_worker, args=(cp, ap, w, 6)) for w in range(3)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert all(p.exitcode == 0 for p in procs)
    chain = AuditChainStore(cp)
    verdict = AnchoredAuditChain(chain, AnchorStore(ap, "c1")).verify()
    assert verdict["status"] == "anchored_verified" and verdict["sequence"] == 18
    chain.close()


def test_anchor_file_is_owner_only_and_close_closes_chain(tmp_path):
    import os, sqlite3, stat
    import pytest
    from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
    from agora.audit_chain import AuditChainStore
    chain = AuditChainStore(tmp_path / "c.db")
    anchors = AnchorStore(tmp_path / "a.jsonl", "c1")
    bootstrap_anchor(chain, anchors, performed_by="test")
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(anchors.path).st_mode) == 0o600
    wrapped = AnchoredAuditChain(chain, anchors)
    wrapped.close()
    with pytest.raises(sqlite3.ProgrammingError):
        chain.verify()

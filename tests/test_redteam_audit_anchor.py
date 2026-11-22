"""Track A red-team, group 1: audit chain / anchor attacks (RT06, RT07, RT14). Synthetic data only.

Each attack runs on a disposable copy in tmp_path. A test passes only when the attack is detected
(verifier status, CLI exit 1, reconcile block), the protected append is refused, and the attacked
files are left byte-identical (no repair, no re-anchor). RT07f documents a TRUST LIMITATION: a
coordinated rollback of chain AND anchor is NOT detected by a local sidecar anchor.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from agora import audit_cli, reconcile as rc
from agora.audit_anchor import (AnchoredAuditChain, AnchorRequiredError, AnchorStore, bootstrap_anchor,
                                verify_anchored_readonly, _record_hash)
from agora.audit_chain import AuditChainStore

CID = "rt-chain"


def _evt(i):
    return {"event_id": f"e{i}", "event_type": "t", "subject_id": "u", "operation": "import", "decision": "allow"}


@pytest.fixture
def pair(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "anchor.jsonl", CID)
    chain.append(_evt(0))
    bootstrap_anchor(chain, anchors, performed_by="maint")
    w = AnchoredAuditChain(chain, anchors)
    for i in (1, 2, 3):
        w.append(_evt(i))
    chain.close()
    return tmp_path


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rows_hash(db_path):
    """Hash of every audit row. Opening the writer re-creates dropped append-only TRIGGERS (schema only,
    benign); it must never change, add or remove an event, so rows (not file bytes) are compared."""
    import sqlite3
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return hashlib.sha256(repr(con.execute("SELECT * FROM audit_events ORDER BY seq").fetchall()).encode()).hexdigest()
    finally:
        con.close()


def _hashes(root):
    return {"audit_rows": _rows_hash(root / "audit.sqlite3"), "anchor": _sha(root / "anchor.jsonl")}


def _status(root, chain_id=CID):
    return verify_anchored_readonly(root / "audit.sqlite3", root / "anchor.jsonl", chain_id)


def _try_append(root):
    chain = AuditChainStore(root / "audit.sqlite3")
    try:
        with pytest.raises(AnchorRequiredError):
            AnchoredAuditChain(chain, AnchorStore(root / "anchor.jsonl", CID)).append(_evt(99))
    finally:
        chain.close()


def _delete_tail(root, keep):
    c = AuditChainStore(root / "audit.sqlite3")
    c.db.execute("DROP TRIGGER protect_audit_event_delete")
    c.db.execute("DELETE FROM audit_events WHERE seq>?", (keep,))
    c.db.commit()
    c.close()


def _anchor_lines(root):
    return (root / "anchor.jsonl").read_text(encoding="utf-8").splitlines()


def _write_anchor(root, lines):
    (root / "anchor.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _detected(root, status):
    """Common proof: verifier status, CLI NOT INTACT (exit 1), append refused, files untouched."""
    before = _hashes(root)
    out = _status(root)
    assert out["valid"] is False and out["status"] == status
    assert audit_cli.main(["verify", "--audit", str(root / "audit.sqlite3"),
                           "--anchor", str(root / "anchor.jsonl"), "--chain-id", CID]) == 1
    _try_append(root)
    assert before == _hashes(root)  # nothing repaired, re-anchored or rewritten


def test_clean_baseline_is_verified(pair):
    assert _status(pair)["status"] == "anchored_verified"


def test_rt06_truncate_chain_tail_detected(pair):
    _delete_tail(pair, keep=2)
    _detected(pair, "truncation_detected")


def test_rt06_wipe_chain_to_empty_detected(pair):
    _delete_tail(pair, keep=0)
    _detected(pair, "truncation_detected")


def test_rt06_reconcile_blocks_on_truncation(pair):
    _delete_tail(pair, keep=2)
    before = _hashes(pair)
    with pytest.raises(rc.ReconcileBlocked) as e:
        rc.reconcile(pair / "decisions.db", pair / "audit.sqlite3", anchor_path=pair / "anchor.jsonl", chain_id=CID)
    assert e.value.args[0] == "ANCHOR_TRUNCATION" or getattr(e.value, "code", None) == "ANCHOR_TRUNCATION"
    assert before == _hashes(pair)


def test_rt07_rollback_anchor_to_older_checkpoint_detected(pair):
    lines = _anchor_lines(pair)
    _write_anchor(pair, lines[:2])  # older, internally valid checkpoint; chain is ahead
    _detected(pair, "unanchored_tail")


def test_rt07_edit_anchor_head_hash_breaks_linkage(pair):
    lines = _anchor_lines(pair)
    rec = json.loads(lines[-1])
    rec["head_hash"] = "f" * 64
    lines[-1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    _write_anchor(pair, lines)
    _detected(pair, "anchor_invalid")


def test_rt07_self_consistent_forged_anchor_is_mismatch(pair):
    lines = _anchor_lines(pair)
    rec = json.loads(lines[-1])
    rec.pop("record_hash")
    rec["head_hash"] = "e" * 64
    rec["record_hash"] = _record_hash(rec)  # attacker recomputes the record hash
    lines[-1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    _write_anchor(pair, lines)
    _detected(pair, "anchor_mismatch")


def test_rt07_delete_middle_anchor_record_detected(pair):
    lines = _anchor_lines(pair)
    del lines[1]
    _write_anchor(pair, lines)
    _detected(pair, "anchor_invalid")


def test_rt07_chain_id_swap_detected(pair):
    before = _hashes(pair)
    out = _status(pair, chain_id="other-chain")
    assert out["valid"] is False and out["status"] == "anchor_invalid"
    assert before == _hashes(pair)


def test_rt07_tamper_event_content_detected(pair):
    c = AuditChainStore(pair / "audit.sqlite3")
    c.db.execute("DROP TRIGGER protect_audit_event_update")
    c.db.execute("UPDATE audit_events SET event_json=replace(event_json,'allow','deny') WHERE seq=2")
    c.db.commit()
    c.close()
    _detected(pair, "chain_integrity_failure")


def test_rt14_missing_or_corrupt_anchor_blocks_reconcile_without_creating(pair):
    (pair / "anchor.jsonl").unlink()
    with pytest.raises(rc.ReconcileBlocked):
        rc.reconcile(pair / "decisions.db", pair / "audit.sqlite3", anchor_path=pair / "anchor.jsonl", chain_id=CID)
    assert not (pair / "anchor.jsonl").exists()  # no auto-bootstrap
    _try_append(pair)
    assert not (pair / "anchor.jsonl").exists()


def test_rt07f_coordinated_rollback_is_NOT_detected_trust_limitation(pair):
    """Honest limitation: an actor who rewrites BOTH chain and sidecar anchor to an earlier matching
    state is undetectable locally. Pinned so nobody claims otherwise; needs an independent checkpoint."""
    lines = _anchor_lines(pair)
    kept = json.loads(lines[1])  # anchor record for sequence 2 (bootstrap@1, then 2,3,4)
    _delete_tail(pair, keep=kept["sequence"])
    _write_anchor(pair, lines[:2])
    assert _status(pair)["status"] == "anchored_verified"

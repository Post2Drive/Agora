from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from agora import audit_cli as ac
from agora import cli
from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import propose
from agora.decisions.store import DecisionRecordStore
from tests.test_decision_approval import draft_record

NOW = "2026-11-21T10:00:00Z"
DID = "decision-approval-001"


def _setup(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "anchor.jsonl", "c1")
    bootstrap_anchor(chain, anchors, performed_by="maint-1")
    writer = AnchoredAuditChain(chain, anchors)
    store = DecisionRecordStore(tmp_path / "decisions.db")
    store.append(draft_record())
    propose(store, DID, 1, actor="analyst", now=NOW, audit=writer)
    chain.db.commit()
    return chain, anchors, store


def _verify(tmp_path):
    return ac.verify_chain(tmp_path / "audit.sqlite3", tmp_path / "anchor.jsonl", "c1")


def _h(*paths):
    return [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_verify_intact_in_plain_words(tmp_path):
    _setup(tmp_path)
    r = _verify(tmp_path)
    assert r["valid"] is True and r["status"] == "anchored_verified"
    assert r["message"].startswith("INTACT")


def test_verify_detects_chain_tamper(tmp_path):
    chain, _a, _s = _setup(tmp_path)
    chain.db.execute("DROP TRIGGER protect_audit_event_update")
    chain.db.execute("UPDATE audit_events SET event_json=replace(event_json,'analyst','mallory')")
    chain.db.commit()
    r = _verify(tmp_path)
    assert r["valid"] is False and r["status"] == "chain_integrity_failure"
    assert r["message"].startswith("NOT INTACT")


def test_verify_detects_truncation_and_unanchored_tail(tmp_path):
    chain, anchors, _s = _setup(tmp_path)
    chain.append({"event_id": "extra-1", "event_type": "x", "resource_ids": ["a"]})  # bypasses anchor
    chain.db.commit()
    assert _verify(tmp_path)["status"] == "unanchored_tail"
    chain.db.execute("DROP TRIGGER protect_audit_event_delete")
    chain.db.execute("DELETE FROM audit_events WHERE seq=(SELECT MAX(seq) FROM audit_events)")
    chain.db.execute("DELETE FROM audit_events WHERE seq=(SELECT MAX(seq) FROM audit_events)")
    chain.db.commit()
    assert _verify(tmp_path)["status"] == "truncation_detected"


def test_verify_detects_anchor_tamper_and_missing_anchor(tmp_path):
    _setup(tmp_path)
    a = tmp_path / "anchor.jsonl"
    good = a.read_text()
    a.write_text(good.replace('"sequence":1', '"sequence":9'))
    assert _verify(tmp_path)["status"] == "anchor_invalid"
    a.unlink()
    r = _verify(tmp_path)
    assert r["status"] == "anchor_invalid" and r["valid"] is False


def test_verify_wrong_chain_id_is_not_intact(tmp_path):
    _setup(tmp_path)
    r = ac.verify_chain(tmp_path / "audit.sqlite3", tmp_path / "anchor.jsonl", "other")
    assert r["valid"] is False and r["status"] == "anchor_invalid"


def test_verify_is_read_only_and_never_creates_stores(tmp_path):
    _setup(tmp_path)
    paths = [tmp_path / "audit.sqlite3", tmp_path / "anchor.jsonl"]
    before = _h(*paths)
    _verify(tmp_path)
    assert _h(*paths) == before
    with pytest.raises(ac.AuditBlocked) as exc:
        ac.verify_chain(tmp_path / "nope.sqlite3", tmp_path / "anchor.jsonl", "c1")
    assert exc.value.code == "STORE_NOT_FOUND" and not (tmp_path / "nope.sqlite3").exists()


def test_verify_cli_exit_codes(tmp_path, capsys):
    chain, _a, _s = _setup(tmp_path)
    argv = ["audit", "verify", "--audit", str(tmp_path / "audit.sqlite3"),
            "--anchor", str(tmp_path / "anchor.jsonl"), "--chain-id", "c1"]
    assert cli.main(argv) == 0
    assert "INTACT" in capsys.readouterr().out
    chain.db.execute("DROP TRIGGER protect_audit_event_update")
    chain.db.execute("UPDATE audit_events SET event_json=replace(event_json,'analyst','x')")
    chain.db.commit()
    assert cli.main(argv) == 1
    assert "NOT INTACT" in capsys.readouterr().out
    argv[3] = str(tmp_path / "missing.sqlite3")
    assert cli.main(argv) == 2
    assert "AUDIT_BLOCKED: STORE_NOT_FOUND" in capsys.readouterr().err


def test_timeline_lists_transition_and_audit_entry(tmp_path):
    _setup(tmp_path)
    t = ac.timeline(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", DID)
    assert [x["transition"] for x in t["transitions"]] == ["proposed"]
    assert t["transitions"][0]["actor"] == "analyst"
    assert [e["event_type"] for e in t["audit_events"]] == ["decision_proposed"]
    assert set(t["transitions"][0]) == {"version", "transition", "actor", "method", "occurred_at", "fingerprint"}


def test_timeline_ignores_other_decisions(tmp_path):
    _setup(tmp_path)
    t = ac.timeline(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", "other-id")
    assert t["transitions"] == [] and t["audit_events"] == []


def test_timeline_refuses_broken_chain(tmp_path):
    chain, _a, _s = _setup(tmp_path)
    chain.db.execute("DROP TRIGGER protect_audit_event_update")
    chain.db.execute("UPDATE audit_events SET event_json=replace(event_json,'analyst','x')")
    chain.db.commit()
    with pytest.raises(ac.AuditBlocked) as exc:
        ac.timeline(tmp_path / "decisions.db", tmp_path / "audit.sqlite3", DID)
    assert exc.value.code == "CHAIN_INVALID"


def test_timeline_cli_output_and_read_only(tmp_path, capsys):
    _setup(tmp_path)
    paths = [tmp_path / "audit.sqlite3", tmp_path / "decisions.db"]
    before = _h(*paths)
    base = ["audit", "timeline", "--decisions", str(paths[1]), "--audit", str(paths[0])]
    assert cli.main(base + ["--decision-id", DID]) == 0
    out = capsys.readouterr().out
    kinds = [json.loads(l)["kind"] for l in out.splitlines() if l.startswith("{")]
    assert kinds == ["stored_transition", "audit_entry"]
    assert "policy" not in out and "details" not in out
    assert cli.main(base + ["--decision-id", "zzz"]) == 1
    assert "NOT_FOUND" in capsys.readouterr().out
    assert _h(*paths) == before
    assert cli.main(base[:5] + [str(tmp_path / "gone.sqlite3")] + ["--decision-id", DID]) == 2


def test_store_handles_are_read_only(tmp_path):
    _setup(tmp_path)
    db = ac._ro(tmp_path / "audit.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        db.execute("CREATE TABLE t(x)")
    db.close()

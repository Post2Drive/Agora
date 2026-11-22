from __future__ import annotations

import hashlib
import sqlite3

import pytest

from agora import cli
from agora import outcomes_held as oh
from agora.decisions.outcomes import (
    DecisionOutcomeStore, _record_outcome as record_outcome, _review_outcome as review_outcome,
)
from tests.test_decision_outcomes import approved_store, outcome_args, review_args, SECRET_NOTE


def _db(tmp_path):
    return tmp_path / "decisions.db"


def _held(tmp_path):
    return oh.held_outcomes(_db(tmp_path))["held"]


def _file_hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_recorded_outcome_is_awaiting_review(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved, notes=SECRET_NOTE))
    decisions.db.commit()
    held = _held(tmp_path)
    assert held == [{"decision_id": approved.decision_id, "decision_version": approved.version,
                     "outcome_id": out["outcome_id"], "state": "recorded", "reason": "awaiting_review"}]
    assert SECRET_NOTE not in str(held) and "42" not in str(held)


def test_reviewed_is_not_held_and_disputed_is(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved))
    review_outcome(store, approved.decision_id, approved.version, out["outcome_id"], **review_args())
    assert _held(tmp_path) == []
    review_outcome(store, approved.decision_id, approved.version, out["outcome_id"],
                   **review_args(new_state="disputed", now="2026-11-28T00:00:00Z"))
    held = _held(tmp_path)
    assert [h["reason"] for h in held] == ["disputed"]


def test_review_does_not_resolve_other_outcomes(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    a = record_outcome(store, **outcome_args(approved))
    b = record_outcome(store, **outcome_args(approved, source_ref={
        "source_registry_id": "source-2", "evidence_id": "evidence-2", "content_hash": "sha256:" + "cd" * 32}))
    review_outcome(store, approved.decision_id, approved.version, a["outcome_id"], **review_args())
    assert [h["outcome_id"] for h in _held(tmp_path)] == [b["outcome_id"]]


def test_invalid_history_fails_closed(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved))
    decisions.db.execute("DROP TRIGGER protect_decision_outcome_reviews_update")
    decisions.db.execute("INSERT INTO decision_outcome_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (approved.decision_id, approved.version, out["outcome_id"], 2, "recorded",
                          "reviewed", "x", "2026-11-27T00:00:00Z", "c", None, None))  # seq gap
    decisions.db.commit()
    assert [h["reason"] for h in _held(tmp_path)] == ["review_history_invalid"]


def test_review_without_outcome_is_held(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    decisions.db.execute("INSERT INTO decision_outcome_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (approved.decision_id, approved.version, "ghost", 1, "recorded",
                          "reviewed", "x", "2026-11-27T00:00:00Z", "c", None, None))
    decisions.db.commit()
    assert [h["reason"] for h in _held(tmp_path)] == ["review_without_outcome"]


def test_read_only_and_missing_store(tmp_path):
    decisions, store, approved = approved_store(tmp_path)
    record_outcome(store, **outcome_args(approved))
    decisions.db.commit()
    before = _file_hash(_db(tmp_path))
    _held(tmp_path)
    assert _file_hash(_db(tmp_path)) == before
    with pytest.raises(oh.HeldBlocked):
        oh.held_outcomes(tmp_path / "absent.db")


def test_store_without_outcome_tables_blocks(tmp_path):
    sqlite3.connect(tmp_path / "x.db").close()
    with pytest.raises(oh.HeldBlocked):
        oh.held_outcomes(tmp_path / "x.db")


def test_cli_exit_codes_and_messages(tmp_path, capsys):
    decisions, store, approved = approved_store(tmp_path)
    out = record_outcome(store, **outcome_args(approved))
    decisions.db.commit()
    assert cli.main(["outcomes", "held", "--decisions", str(_db(tmp_path))]) == 1
    assert "HELD:" in capsys.readouterr().out
    review_outcome(store, approved.decision_id, approved.version, out["outcome_id"], **review_args())
    assert cli.main(["outcomes", "held", "--decisions", str(_db(tmp_path))]) == 0
    assert "OK:" in capsys.readouterr().out
    assert cli.main(["outcomes", "held", "--decisions", str(tmp_path / "nope.db")]) == 2
    assert "HELD_BLOCKED" in capsys.readouterr().err


def test_no_engine_import():
    import subprocess, sys
    r = subprocess.run([sys.executable, "-c",
                        "import sys, agora.outcomes_held; print('agora.sim.engine' in sys.modules)"],
                       capture_output=True, text=True, timeout=120)
    assert r.stdout.strip() == "False"

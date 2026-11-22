"""Read-only list of observed outcomes held for review (#60, minimal).

An outcome is *held* when it is disputed, has never been reviewed, or its review
history is not a valid append-only sequence (fail closed). It never writes, never
propagates markers and never repairs. Output uses opaque IDs and stable codes only:
no observed values, units, notes or rationale text. Synthetic data only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from .decisions.outcomes import _TRANSITIONS, STATES


class HeldBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise HeldBlocked("STORE_NOT_FOUND")
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _history_state(reviews: list[tuple]) -> str | None:
    """Final state of a valid review history, or None when the history is invalid."""
    state = "recorded"
    for n, (seq, prior, new) in enumerate(reviews, 1):
        if seq != n or prior != state or new not in STATES or new not in _TRANSITIONS.get(state, set()):
            return None
        state = new
    return state


def held_outcomes(decisions_db: str | Path) -> dict[str, Any]:
    db = _ro(Path(decisions_db))
    try:
        try:
            outcomes = db.execute("SELECT decision_id, decision_version, outcome_id FROM decision_outcomes "
                                  "ORDER BY decision_id, decision_version, outcome_id").fetchall()
            reviews = db.execute("SELECT decision_id, decision_version, outcome_id, seq, prior_state, new_state "
                                 "FROM decision_outcome_reviews ORDER BY seq").fetchall()
        except sqlite3.DatabaseError:
            raise HeldBlocked("STORE_UNREADABLE") from None
    finally:
        db.close()
    by_key: dict[tuple, list[tuple]] = {}
    for did, ver, oid, seq, prior, new in reviews:
        by_key.setdefault((did, ver, oid), []).append((seq, prior, new))
    known = {(d, v, o) for d, v, o in outcomes}
    held: list[dict[str, Any]] = []
    for key in sorted(known):
        history = sorted(by_key.get(key, []))
        state = _history_state(history)
        if state == "reviewed":
            continue
        reason = {"recorded": "awaiting_review", "disputed": "disputed", None: "review_history_invalid"}[state]
        held.append({"decision_id": key[0], "decision_version": key[1], "outcome_id": key[2],
                     "state": state or "invalid", "reason": reason})
    for key in sorted(set(by_key) - known):  # review rows with no outcome row
        held.append({"decision_id": key[0], "decision_version": key[1], "outcome_id": key[2],
                     "state": "invalid", "reason": "review_without_outcome"})
    return {"outcomes": len(known), "held": held}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agora outcomes held",
                                 description="Read-only: list outcomes held for review.")
    ap.add_argument("--decisions", required=True, help="decision store SQLite file (holds the outcome tables)")
    args = ap.parse_args(argv)
    try:
        report = held_outcomes(args.decisions)
    except HeldBlocked as exc:
        print(f"HELD_BLOCKED: {exc.code}. Nothing was listed; nothing was changed.", file=sys.stderr)
        return 2
    for item in report["held"]:
        print(json.dumps(item, sort_keys=True))
    print(json.dumps({"outcomes": report["outcomes"], "held": len(report["held"])}, sort_keys=True))
    if not report["held"]:
        print("OK: no outcome is held for review.")
        return 0
    print("HELD: these outcomes must not be relied on until an independent reviewer records a decision. "
          "This command does not change anything.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

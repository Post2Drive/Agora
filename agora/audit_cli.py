"""Read-only audit commands: ``agora audit timeline`` and ``agora audit verify`` (M2 item 4).

Both open every store read-only (SQLite ``mode=ro``; the anchor file is only read), never
repair, never bootstrap and never write. Output uses opaque IDs, stable codes and fixed
plain-language sentences only: no payload, policy, note or free-text fields. Synthetic data only.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from .audit_anchor import AnchorError, AnchorStore, verify_anchored
from .audit_chain import verify_rows
from .pathsafe import is_unsafe_path


class AuditBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ro(path: Path) -> sqlite3.Connection:
    if is_unsafe_path(path):
        raise AuditBlocked("STORE_UNREADABLE")
    if not path.is_file():
        raise AuditBlocked("STORE_NOT_FOUND")
    try:
        return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        raise AuditBlocked("STORE_UNREADABLE") from None


class _ReadOnlyChain:
    """The two members verify_anchored needs (``db`` and ``verify``), over a read-only handle."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def verify(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq").fetchall()
        last, broken = verify_rows(rows)
        if broken is not None:
            return {"valid": False, "first_broken_sequence": broken}
        return {"valid": True, "entries": len(rows), "last_hash": last}


_WORDS = {
    "anchored_verified": "INTACT: the audit chain is unbroken and matches its anchor.",
    "chain_integrity_failure": "NOT INTACT: the audit chain has been altered or damaged "
                               "(an entry no longer matches its hash).",
    "anchor_invalid": "NOT INTACT: the anchor file is missing, unreadable or altered, "
                      "so the chain cannot be checked against it.",
    "truncation_detected": "NOT INTACT: the chain is shorter than its anchor; entries were removed.",
    "anchor_mismatch": "NOT INTACT: the chain no longer matches its anchor; an anchored entry was changed.",
    "unanchored_tail": "NOT INTACT: the chain has entries newer than the latest anchor; "
                       "they are not yet covered by the anchor.",
}
_TRUST_NOTE = ("Note: the anchor is a local sidecar file; it detects edits to the chain only while "
               "the anchor itself is kept safe and separate.")


def verify_chain(audit_db: str | Path, anchor_path: str | Path, chain_id: str) -> dict[str, Any]:
    try:
        anchors = AnchorStore(anchor_path, chain_id)
    except AnchorError:
        raise AuditBlocked("CHAIN_ID_REQUIRED") from None
    try:
        with closing(_ro(Path(audit_db))) as db:
            try:
                result = verify_anchored(_ReadOnlyChain(db), anchors)
            except sqlite3.Error:
                raise AuditBlocked("STORE_UNREADABLE") from None
    except sqlite3.Error:
        raise AuditBlocked("STORE_UNREADABLE") from None
    result["message"] = _WORDS.get(result["status"], "NOT INTACT: unknown verification status.")
    return result


def timeline(decisions_db: str | Path, audit_db: str | Path, decision_id: str) -> dict[str, Any]:
    """Stored lifecycle transitions of one decision, each with its matching audit entries."""
    try:
        with closing(_ro(Path(audit_db))) as audit, closing(_ro(Path(decisions_db))) as source:
            rows = audit.execute(
                "SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq").fetchall()
            _last, broken = verify_rows(rows)
            if broken is not None:
                raise AuditBlocked("CHAIN_INVALID")  # never show a timeline from a broken chain
            transitions = source.execute(
                "SELECT version,transition,actor,method,occurred_at,decision_fingerprint "
                "FROM decision_approval_events WHERE decision_id=? ORDER BY version,occurred_at,event_id",
                (decision_id,)).fetchall()
    except sqlite3.Error:
        raise AuditBlocked("STORE_UNREADABLE") from None
    audit_events: list[dict[str, Any]] = []
    for seq, _eid, _prev, raw, _hash in rows:
        event = json.loads(raw)
        ids = event.get("resource_ids")
        if isinstance(ids, list) and ids and ids[0] == decision_id:
            audit_events.append({"audit_sequence": seq, "event_type": event.get("event_type"),
                                 "subject_id": event.get("subject_id"),
                                 "recorded_at": event.get("recorded_at"),
                                 "resource_ids": [i for i in ids if isinstance(i, str)]})
    return {"decision_id": decision_id,
            "transitions": [{"version": v, "transition": t, "actor": a, "method": m,
                             "occurred_at": at, "fingerprint": f}
                            for v, t, a, m, at, f in transitions],
            "audit_events": audit_events}


def _blocked(command: str, exc: AuditBlocked) -> int:
    print(f"AUDIT_BLOCKED: {exc.code}. Nothing was {command}; nothing was changed.", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agora audit", description="Read-only audit commands.")
    sub = ap.add_subparsers(dest="audit_command", required=True)
    t = sub.add_parser("timeline", help="print the decision and audit timeline for one decision ID")
    t.add_argument("--decisions", required=True, help="decision store SQLite file")
    t.add_argument("--audit", required=True, help="audit chain SQLite file")
    t.add_argument("--decision-id", required=True)
    v = sub.add_parser("verify", help="check the audit chain against its anchor, in plain words")
    v.add_argument("--audit", required=True, help="audit chain SQLite file")
    v.add_argument("--anchor", required=True, help="anchor history file")
    v.add_argument("--chain-id", required=True)
    args = ap.parse_args(argv)
    if args.audit_command == "verify":
        try:
            result = verify_chain(args.audit, args.anchor, args.chain_id)
        except AuditBlocked as exc:
            return _blocked("verified", exc)
        print(result["message"])
        print(json.dumps({k: v for k, v in result.items() if k != "message"}, sort_keys=True))
        print(_TRUST_NOTE)
        return 0 if result["valid"] else 1
    try:
        report = timeline(args.decisions, args.audit, args.decision_id)
    except AuditBlocked as exc:
        return _blocked("listed", exc)
    if not report["transitions"] and not report["audit_events"]:
        print("NOT_FOUND: no stored transition or audit entry for this decision ID.")
        return 1
    for item in report["transitions"]:
        print(json.dumps({"kind": "stored_transition", **item}, sort_keys=True))
    for item in report["audit_events"]:
        print(json.dumps({"kind": "audit_entry", **item}, sort_keys=True))
    print("Timeline is read-only. Run `agora audit verify` to check the chain against its anchor, "
          "and `agora reconcile` to compare stored transitions with audit entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

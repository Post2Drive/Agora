"""Read-only decision-store / audit-chain reconciliation detector (#57, minimal).

Lists decision lifecycle transitions whose audit event is missing or conflicting,
and audit events that reference no stored transition. It never writes to either
store, never repairs, and refuses to classify anything when the audit chain does
not verify. Output uses opaque IDs and stable codes only. Synthetic data only.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, closing
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from .audit_chain import verify_rows

TRANSITIONS = ("proposed", "approved", "rejected", "expired", "superseded")
_EVENT_TYPES = {f"decision_{t}": t for t in TRANSITIONS}


class ReconcileBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ReconcileBlocked("STORE_NOT_FOUND")
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


_STATUS = {"proposed": "proposed", "approved": "approved", "rejected": "rejected",
           "expired": "rejected", "superseded": "superseded"}


def _source_problem(transition: str, actor: str, method: str, occurred_at: str,
                    payload: Any) -> str | None:
    """Cross-check a stored transition row against its immutable record payload."""
    try:
        record = json.loads(payload)
    except (TypeError, ValueError):
        return "RECORD_PAYLOAD_INVALID"
    if not isinstance(record, dict):
        return "RECORD_PAYLOAD_INVALID"
    if _STATUS.get(transition) != record.get("status"):
        return "TRANSITION_STATUS_MISMATCH"
    if transition == "expired":
        wanted_actor = "system:expiry"
    elif transition == "proposed":
        wanted_actor = record.get("proposer")
    elif transition == "approved":
        wanted_actor = record.get("approver")
    elif transition == "rejected":
        wanted_actor = record.get("reviewer")
    else:  # superseded: any decision participant
        wanted_actor = actor if actor in (record.get("proposer"), record.get("reviewer"),
                                          record.get("approver")) else None
    if wanted_actor is None or actor != wanted_actor:
        return "ACTOR_MISMATCH"
    if method != record.get("approval_method"):
        return "METHOD_MISMATCH"
    if occurred_at != record.get("updated_at"):
        return "TIMESTAMP_MISMATCH"
    return None


_ANCHOR_BLOCK = {
    "chain_integrity_failure": "CHAIN_INVALID", "anchor_invalid": "ANCHOR_INVALID",
    "truncation_detected": "ANCHOR_TRUNCATION", "anchor_mismatch": "ANCHOR_MISMATCH",
    "unanchored_tail": "ANCHOR_UNANCHORED_TAIL", "store_unreadable": "STORE_UNREADABLE",
}


def reconcile(decisions_db: str | Path, audit_db: str | Path, *, anchor_path: str | Path,
              chain_id: str) -> dict[str, Any]:
    """Return a deterministic report. Raises ReconcileBlocked when it cannot proceed.

    Nothing is classified unless the chain verifies AND matches its sidecar anchor
    (``anchored_verified``), checked read-only: no bootstrap, writes or repair.
    """
    from .audit_anchor import verify_anchored_readonly
    if Path(audit_db).is_file():  # a missing store falls through to STORE_NOT_FOUND below
        try:
            verdict = verify_anchored_readonly(audit_db, anchor_path, chain_id)
        except Exception as exc:  # fail closed on anything unexpected
            raise ReconcileBlocked("ANCHOR_INVALID") from exc
        if verdict.get("status") != "anchored_verified":
            raise ReconcileBlocked(_ANCHOR_BLOCK.get(str(verdict.get("status")), "ANCHOR_INVALID"))
    try:
        with ExitStack() as stack:
            audit = stack.enter_context(closing(_ro(Path(audit_db))))
            source = stack.enter_context(closing(_ro(Path(decisions_db))))
            rows = audit.execute(
                "SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq"
            ).fetchall()
            transitions = source.execute(
                "SELECT decision_id,version,transition,actor,decision_fingerprint,method,occurred_at "
                "FROM decision_approval_events ORDER BY decision_id,version,event_id"
            ).fetchall()
            records = {
                (d, v): (f, p) for d, v, f, p in source.execute(
                    "SELECT decision_id,version,fingerprint,payload_json FROM decision_records")
            }
    except sqlite3.Error as exc:
        raise ReconcileBlocked("STORE_UNREADABLE") from exc

    _last, broken = verify_rows(rows)
    if broken is not None:
        raise ReconcileBlocked("CHAIN_INVALID")  # halt: nothing is classified

    events: list[dict[str, Any]] = []
    for seq, _eid, _prev, raw, _hash in rows:
        event = json.loads(raw)
        if event.get("event_type") in _EVENT_TYPES:
            events.append({"seq": seq, **event})

    def key(event: dict[str, Any]) -> tuple[str, str] | None:
        ids = event.get("resource_ids")
        if isinstance(ids, list) and len(ids) >= 2 and all(isinstance(i, str) for i in ids[:2]):
            return ids[0], ids[1]
        return None

    findings: list[dict[str, Any]] = []
    matched_keys: set[tuple[str, str, str]] = set()
    counts = {"matched": 0, "missing": 0, "conflict": 0, "source_invalid": 0, "orphan": 0}
    versions_by_decision: dict[str, list[int]] = {}
    for (decision_id, version) in records:
        versions_by_decision.setdefault(decision_id, []).append(version)
    for decision_id, versions in sorted(versions_by_decision.items()):
        if sorted(versions) != list(range(1, len(versions) + 1)):
            counts["source_invalid"] += 1
            findings.append({"status": "source_invalid", "decision_id": decision_id,
                             "code": "VERSION_HISTORY_GAP"})

    for decision_id, version, transition, actor, fingerprint, method, occurred_at in transitions:
        base = {"decision_id": decision_id, "version": version, "transition": transition}
        stored = records.get((decision_id, version))
        if stored is None or stored[0] != fingerprint:
            counts["source_invalid"] += 1
            findings.append({**base, "status": "source_invalid", "code": "FINGERPRINT_MISMATCH"})
            continue
        problem = _source_problem(transition, actor, method, occurred_at, stored[1])
        if problem:
            counts["source_invalid"] += 1
            findings.append({**base, "status": "source_invalid", "code": problem})
            continue
        wanted = (decision_id, f"version-{version}")
        hits = [e for e in events
                if key(e) == wanted and _EVENT_TYPES[e["event_type"]] == transition]
        matched_keys.update((decision_id, f"version-{version}", t) for t in [transition])
        if not hits:
            counts["missing"] += 1
            findings.append({**base, "status": "missing", "code": "AUDIT_EVENT_MISSING"})
        elif len(hits) > 1:
            counts["conflict"] += 1
            findings.append({**base, "status": "conflict", "code": "DUPLICATE_AUDIT_EVENTS",
                             "audit_sequences": [h["seq"] for h in hits]})
        elif (hits[0].get("decision_fingerprint") != fingerprint or hits[0].get("subject_id") != actor
              or hits[0].get("operation") != ("decision_approval" if transition == "approved"
                                              else "decision_lifecycle")
              or hits[0].get("resource_ids") != [decision_id, f"version-{version}"]):
            counts["conflict"] += 1
            findings.append({**base, "status": "conflict", "code": "AUDIT_EVENT_MISMATCH",
                             "audit_sequences": [hits[0]["seq"]]})
        else:
            counts["matched"] += 1

    for event in events:
        ids = key(event)
        triple = (ids[0], ids[1], _EVENT_TYPES[event["event_type"]]) if ids else None
        if triple is None or triple not in matched_keys:
            counts["orphan"] += 1
            findings.append({"status": "orphan", "code": "AUDIT_EVENT_WITHOUT_TRANSITION",
                             "audit_sequence": event["seq"], "event_type": event["event_type"]})

    findings.sort(key=lambda f: json.dumps(f, sort_keys=True))
    gaps = sum(counts[k] for k in ("missing", "conflict", "source_invalid", "orphan"))
    return {"intact": gaps == 0, "audit_entries": len(rows), "transitions": len(transitions),
            "counts": counts, "findings": findings}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agora reconcile",
                                 description="Read-only: list decisions with missing or mismatched audit records.")
    ap.add_argument("--decisions", required=True, help="decision store SQLite file")
    ap.add_argument("--audit", required=True, help="audit chain SQLite file")
    ap.add_argument("--anchor", required=True, help="sidecar anchor history file for the audit chain")
    ap.add_argument("--chain-id", required=True, help="chain id the anchor was bootstrapped with")
    args = ap.parse_args(argv)
    try:
        report = reconcile(args.decisions, args.audit, anchor_path=args.anchor, chain_id=args.chain_id)
    except ReconcileBlocked as exc:
        print(f"RECONCILE_BLOCKED: {exc.code}. No decision was classified; nothing was changed.",
              file=sys.stderr)
        return 2
    for finding in report["findings"]:
        print(json.dumps(finding, sort_keys=True))
    print(json.dumps({k: report[k] for k in ("intact", "audit_entries", "transitions", "counts")},
                     sort_keys=True))
    if report["intact"]:
        print("OK: every stored decision transition has exactly one matching audit event.")
        return 0
    print("GAPS FOUND: review the findings above. This command does not repair anything.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

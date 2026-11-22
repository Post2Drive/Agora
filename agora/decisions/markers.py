"""Append-only outcome dependency review markers (docs/OUTCOME_REVIEW_MARKERS_SPEC.md).

A marker means: this exact object must not be relied on until an authorised
reviewer records a disposition. Markers are signals only: they never change an
outcome, decision, report or source, and propagation follows EXPLICIT stored
dependency edges only (no heuristics). Synthetic/local stores; no network.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from agora import protection as _protection
from agora.audit_anchor import require_anchored as _require_anchored
from agora.audit_chain import AuditAppender
from agora.principal import Principal

from .outcomes import (
    DecisionOutcomeStore, OutcomeError, OutcomePermissionError, _HASH_RE, _SOURCE_KEYS,
    _canonical, _principal_gate, _stamp, _utc,
)

PROVENANCE_VERSION = 1
TRIGGERS = frozenset({"outcome_disputed", "outcome_corrected", "source_hash_mismatch"})
DISPOSITIONS = frozenset({"valid", "needs_reissue", "remains_blocked", "superseded"})
ROOT_TYPES = frozenset({"outcome", "source"})
DEPENDENT_TYPES = frozenset({"decision", "report", "outcome"})
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:|-]{0,255}$")
_TRANSITIONS = {
    "open": {"acknowledged", "superseded"},
    "acknowledged": {"under_review", "superseded"},
    "under_review": {"resolved"},
}
_SEVERITY = {"outcome_disputed": "high", "outcome_corrected": "high", "source_hash_mismatch": "high"}


_REASON_RE = re.compile(r"[a-z][a-z0-9_]{2,63}")


class MarkerError(ValueError):
    """Raised when a marker operation violates the specification."""


def outcome_ref(decision_id: str, version: int, outcome_id: str) -> str:
    return f"outcome:{decision_id}:{version}:{outcome_id}"


def source_ref(content_hash: str) -> str:
    return f"source:{content_hash}"


def _setup(store: DecisionOutcomeStore) -> None:
    db = store.db
    db.execute("CREATE TABLE IF NOT EXISTS marker_edges (root_type TEXT NOT NULL, root_ref TEXT NOT NULL, "
               "dependent_type TEXT NOT NULL, dependent_ref TEXT NOT NULL, dependent_hash TEXT, "
               "registered_by TEXT NOT NULL, registered_at TEXT NOT NULL, "
               "PRIMARY KEY(root_type, root_ref, dependent_type, dependent_ref))")
    db.execute("CREATE TABLE IF NOT EXISTS outcome_markers (marker_id TEXT PRIMARY KEY, "
               "idempotency_key TEXT NOT NULL UNIQUE, decision_id TEXT NOT NULL, decision_version INTEGER NOT NULL, "
               "trigger_type TEXT NOT NULL, trigger_event_id TEXT NOT NULL, root_type TEXT NOT NULL, "
               "root_ref TEXT NOT NULL, affected_type TEXT NOT NULL, affected_ref TEXT NOT NULL, "
               "affected_hash TEXT, dependency_path_json TEXT NOT NULL, reason_code TEXT NOT NULL, "
               "severity TEXT NOT NULL, created_at TEXT NOT NULL, provenance_version INTEGER NOT NULL, "
               "source_evidence_json TEXT, outcome_recorder TEXT NOT NULL, fingerprint TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS outcome_marker_events (marker_id TEXT NOT NULL, seq INTEGER NOT NULL, "
               "prior_state TEXT NOT NULL, new_state TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, "
               "disposition TEXT, evidence_json TEXT, replacement_marker_id TEXT, "
               "PRIMARY KEY(marker_id, seq))")
    # Audit outbox: the intent to audit a marker opening is committed WITH the marker, so a crash or audit
    # failure between commit and append can be replayed (stable event id); delivery is recorded append-only.
    db.execute("CREATE TABLE IF NOT EXISTS marker_audit_outbox (event_id TEXT PRIMARY KEY, marker_id TEXT NOT NULL, "
               "payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS marker_audit_done (event_id TEXT PRIMARY KEY, done_at TEXT NOT NULL)")
    for table in ("marker_edges", "outcome_markers", "outcome_marker_events", "marker_audit_outbox",
                  "marker_audit_done"):
        for action in ("UPDATE", "DELETE"):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS protect_{table}_{action.lower()} BEFORE {action} ON {table} "
                       f"BEGIN SELECT RAISE(ABORT, '{table} are append-only'); END")
    db.commit()


def _audit(audit: AuditAppender | None, event_type: str, actor: str, decision_id: str, version: int,
           marker_id: str, fingerprint: str, reason: str) -> None:
    if audit is None:
        return
    event = {
        "event_id": f"{event_type}-{uuid.uuid4().hex}", "event_type": event_type, "subject_id": actor,
        "operation": "decision_outcome", "decision": "allow", "reason": reason,
        "resource_ids": [decision_id, f"version-{version}", marker_id], "marker_fingerprint": fingerprint,
    }
    try:
        audit.append(event)
    except Exception as exc:
        raise MarkerError("marker change was not committed because its audit event could not be appended") from exc


def _deliver(store: DecisionOutcomeStore, audit: AuditAppender, event_id: str) -> None:
    row = store.db.execute("SELECT payload_json FROM marker_audit_outbox WHERE event_id=?", (event_id,)).fetchone()
    if row is None or store.db.execute("SELECT 1 FROM marker_audit_done WHERE event_id=?", (event_id,)).fetchone():
        return
    try:
        audit.append(json.loads(row[0]))
    except Exception as exc:
        raise MarkerError("marker change was not committed because its audit event could not be appended") from exc
    store.db.execute("INSERT INTO marker_audit_done VALUES (?,?)", (event_id, _stamp(None)))
    store.db.commit()


def replay_pending_audits(store: DecisionOutcomeStore, audit: AuditAppender) -> int:
    """Append every committed-but-unaudited marker-open event (same event id and payload); returns the count.

    Delivery is at-least-once: if the process dies after the chain append but before the done record, the
    identical event (same id, same payload) is appended again; consumers dedupe on event_id.
    """
    _setup(store)
    pending = [r[0] for r in store.db.execute(
        "SELECT event_id FROM marker_audit_outbox WHERE event_id NOT IN (SELECT event_id FROM marker_audit_done) "
        "ORDER BY created_at, event_id")]
    for event_id in pending:
        _deliver(store, audit, event_id)
    return len(pending)


def _fingerprint(fields: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(dict(fields)).encode()).hexdigest()


def _gate(store, principal, role, audit, decision_id, version, outcome_id, now) -> Principal:
    if _protection.ANCHOR_REQUIRED:
        _require_anchored(audit)
    _principal_gate(principal, role, audit, store, decision_id, version, outcome_id, None, now)
    return principal  # type: ignore[return-value]


def register_dependency_as(
    store: DecisionOutcomeStore, *, principal: Principal | None, decision_id: str, decision_version: int,
    root_type: str, root_ref: str, dependent_type: str, dependent_ref: str, dependent_hash: str | None = None,
    audit: AuditAppender | None = None, now: datetime | str | None = None,
) -> dict[str, Any]:
    """Record one explicit provenance edge: ``dependent`` relied on ``root``."""
    _setup(store)
    if root_type not in ROOT_TYPES | DEPENDENT_TYPES or dependent_type not in DEPENDENT_TYPES:
        raise MarkerError("unknown edge type")
    for ref in (root_ref, dependent_ref):
        if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
            raise MarkerError("edge references must be bounded identifier tokens")
    if dependent_hash is not None and not _HASH_RE.fullmatch(str(dependent_hash)):
        raise MarkerError("dependent_hash must be an exact sha256 hash")
    if (root_type, root_ref) == (dependent_type, dependent_ref):
        raise MarkerError("an object cannot depend on itself")
    _gate(store, principal, "operator", audit, decision_id, decision_version, None, now)
    store.db.execute("INSERT OR IGNORE INTO marker_edges VALUES (?,?,?,?,?,?,?)",
                     (root_type, root_ref, dependent_type, dependent_ref, dependent_hash,
                      principal.subject_id, _stamp(now)))
    store.db.commit()
    return {"root": f"{root_type}:{root_ref}", "dependent": f"{dependent_type}:{dependent_ref}"}


def _traverse(store, root_type: str, root_ref: str) -> list[tuple[str, str, str | None, list[str]]]:
    """Breadth-first over explicit edges; returns (type, ref, hash, path) with a cycle guard."""
    found = []
    seen = {(root_type, root_ref)}
    queue = [(root_type, root_ref, [f"{root_type}:{root_ref}"])]
    while queue:
        rt, rr, path = queue.pop(0)
        rows = store.db.execute(
            "SELECT dependent_type, dependent_ref, dependent_hash FROM marker_edges "
            "WHERE root_type=? AND root_ref=? ORDER BY dependent_type, dependent_ref", (rt, rr)).fetchall()
        for dt, dr, dh in rows:
            if (dt, dr) in seen:
                continue
            seen.add((dt, dr))
            nxt = path + [f"{dt}:{dr}"]
            found.append((dt, dr, dh, nxt))
            queue.append((dt, dr, nxt))
    return found


def _create(store, *, actor: str, decision_id: str, version: int, trigger_type: str, trigger_event_id: str,
            root_type: str, root_ref: str, outcome_recorder: str, targets: list[tuple[str, str, str | None, list[str]]],
            source_evidence: Mapping[str, Any] | None, audit, now) -> list[dict[str, Any]]:
    created = []
    stamp = _stamp(now)
    for atype, aref, ahash, path in targets:
        key = hashlib.sha256(f"{trigger_type}|{trigger_event_id}|{atype}|{aref}".encode()).hexdigest()
        existing = store.db.execute("SELECT marker_id FROM outcome_markers WHERE idempotency_key=?", (key,)).fetchone()
        if existing:
            if audit is not None:
                _deliver(store, audit, f"decision_marker_opened-{existing[0]}")  # replay a missed audit
            created.append(marker_view(store, existing[0]))
            continue
        marker_id = f"marker-{key[:32]}"
        body = {"marker_id": marker_id, "trigger_type": trigger_type, "trigger_event_id": trigger_event_id,
                "root_type": root_type, "root_ref": root_ref, "affected_type": atype, "affected_ref": aref,
                "affected_hash": ahash, "dependency_path": path, "decision_id": decision_id,
                "decision_version": version}
        fp = _fingerprint(body)
        try:
            store.db.execute(
                "INSERT INTO outcome_markers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (marker_id, key, decision_id, version, trigger_type, trigger_event_id, root_type, root_ref,
                 atype, aref, ahash, _canonical(path), trigger_type, _SEVERITY[trigger_type], stamp,
                 PROVENANCE_VERSION, _canonical(dict(source_evidence)) if source_evidence else None,
                 outcome_recorder, fp))
            store.db.execute("INSERT INTO outcome_marker_events VALUES (?,?,?,?,?,?,?,?,?)",
                             (marker_id, 1, "none", "open", actor, stamp, None, None, None))
            if audit is not None:
                ev = {"event_id": f"decision_marker_opened-{marker_id}", "event_type": "decision_marker_opened",
                      "subject_id": actor, "operation": "decision_outcome", "decision": "allow",
                      "reason": trigger_type, "resource_ids": [decision_id, f"version-{version}", marker_id],
                      "marker_fingerprint": fp}
                store.db.execute("INSERT INTO marker_audit_outbox VALUES (?,?,?,?)",
                                 (ev["event_id"], marker_id, _canonical(ev), stamp))
            store.db.commit()
        except Exception:
            store.db.rollback()
            raise
        if audit is not None:
            _deliver(store, audit, f"decision_marker_opened-{marker_id}")
        created.append(marker_view(store, marker_id))
    return created


def _root_target(rt: str, rr: str) -> tuple[str, str, None, list[str]]:
    return (rt, rr, None, [f"{rt}:{rr}"])


def flag_disputed_outcome_as(
    store: DecisionOutcomeStore, decision_id: str, decision_version: int, outcome_id: str, *,
    principal: Principal | None, audit: AuditAppender | None = None, now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Open markers for a disputed outcome and every explicit dependent."""
    _setup(store)
    outcome = store.get(decision_id, decision_version, outcome_id)
    if store.state(decision_id, decision_version, outcome_id) != "disputed":
        raise MarkerError("outcome is not currently disputed")
    _gate(store, principal, "reviewer", audit, decision_id, decision_version, outcome_id, now)
    reviews = store.reviews(decision_id, decision_version, outcome_id)
    trigger = f"review:{decision_id}:{decision_version}:{outcome_id}:{reviews[-1]['seq']}"
    root = outcome_ref(decision_id, decision_version, outcome_id)
    targets = [_root_target("outcome", root)] + _traverse(store, "outcome", root)
    return _create(store, actor=principal.subject_id, decision_id=decision_id, version=decision_version,
                   trigger_type="outcome_disputed", trigger_event_id=trigger, root_type="outcome",
                   root_ref=root, outcome_recorder=outcome["recorder"], targets=targets,
                   source_evidence=outcome["source_ref"], audit=audit, now=now)


def flag_corrected_outcome_as(
    store: DecisionOutcomeStore, decision_id: str, decision_version: int, new_outcome_id: str, *,
    principal: Principal | None, audit: AuditAppender | None = None, now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Open markers for the outcome that a correction superseded, plus its dependents."""
    _setup(store)
    new = store.get(decision_id, decision_version, new_outcome_id)
    prior_id = new.get("supersedes_outcome_id")
    if not prior_id:
        raise MarkerError("outcome is not a correction")
    prior = store.get(decision_id, decision_version, prior_id)
    _gate(store, principal, "reviewer", audit, decision_id, decision_version, prior_id, now)
    root = outcome_ref(decision_id, decision_version, prior_id)
    targets = [_root_target("outcome", root)] + _traverse(store, "outcome", root)
    return _create(store, actor=principal.subject_id, decision_id=decision_id, version=decision_version,
                   trigger_type="outcome_corrected", trigger_event_id=f"correction:{new_outcome_id}",
                   root_type="outcome", root_ref=root, outcome_recorder=prior["recorder"], targets=targets,
                   source_evidence=prior["source_ref"], audit=audit, now=now)


def flag_source_hash_mismatch_as(
    store: DecisionOutcomeStore, decision_id: str, decision_version: int, outcome_id: str, *,
    current_content_hash: str, principal: Principal | None, audit: AuditAppender | None = None,
    now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Open markers when the source evidence no longer hashes to the recorded value.

    Marks the outcome itself (root level) and only objects with an explicit edge
    from the recorded source hash. No edge means a root-level marker only.
    """
    _setup(store)
    outcome = store.get(decision_id, decision_version, outcome_id)
    recorded = outcome["source_ref"]["content_hash"]
    if not isinstance(current_content_hash, str) or not _HASH_RE.fullmatch(current_content_hash):
        raise MarkerError("current_content_hash must be an exact sha256 hash")
    if current_content_hash == recorded:
        raise MarkerError("source hash matches the recorded reference; nothing to flag")
    _gate(store, principal, "reviewer", audit, decision_id, decision_version, outcome_id, now)
    out_root = outcome_ref(decision_id, decision_version, outcome_id)
    src_root = source_ref(recorded)
    targets = [_root_target("outcome", out_root)] + _traverse(store, "source", src_root)
    return _create(store, actor=principal.subject_id, decision_id=decision_id, version=decision_version,
                   trigger_type="source_hash_mismatch",
                   trigger_event_id=f"source-check:{recorded}:{current_content_hash}",
                   root_type="source", root_ref=src_root, outcome_recorder=outcome["recorder"],
                   targets=targets, source_evidence=outcome["source_ref"], audit=audit, now=now)


def marker_view(store: DecisionOutcomeStore, marker_id: str) -> dict[str, Any]:
    row = store.db.execute(
        "SELECT marker_id, decision_id, decision_version, trigger_type, root_type, root_ref, affected_type, "
        "affected_ref, dependency_path_json, reason_code, severity, created_at, fingerprint, outcome_recorder "
        "FROM outcome_markers WHERE marker_id=?", (marker_id,)).fetchone()
    if row is None:
        raise MarkerError("marker was not found")
    keys = ("marker_id", "decision_id", "decision_version", "trigger_type", "root_type", "root_ref",
            "affected_type", "affected_ref", "dependency_path", "reason_code", "severity", "created_at",
            "fingerprint", "outcome_recorder")
    view = dict(zip(keys, row))
    view["dependency_path"] = json.loads(view["dependency_path"])
    events = store.db.execute(
        "SELECT seq, new_state, disposition FROM outcome_marker_events WHERE marker_id=? ORDER BY seq",
        (marker_id,)).fetchall()
    view["state"], view["disposition"], view["event_seq"] = events[-1][1], events[-1][2], events[-1][0]
    return view


def blocking_markers(store: DecisionOutcomeStore, affected_type: str, affected_ref: str) -> list[dict[str, Any]]:
    """Markers that still forbid reliance on this exact object."""
    _setup(store)
    ids = [r[0] for r in store.db.execute(
        "SELECT marker_id FROM outcome_markers WHERE affected_type=? AND affected_ref=? ORDER BY created_at, marker_id",
        (affected_type, affected_ref))]
    out = []
    for mid in ids:
        v = marker_view(store, mid)
        if v["state"] in ("open", "acknowledged", "under_review") or (
                v["state"] == "resolved" and v["disposition"] != "valid"):
            out.append(v)
    return out


def advance_marker_as(
    store: DecisionOutcomeStore, marker_id: str, new_state: str, *, principal: Principal | None,
    expected_fingerprint: str, expected_event_seq: int, disposition: str | None = None,
    evidence_ref: Mapping[str, Any] | None = None, replacement_marker_id: str | None = None,
    supersession_reason: str | None = None,
    audit: AuditAppender | None = None, now: datetime | str | None = None,
) -> dict[str, Any]:
    """Move a marker through its lifecycle; resolution needs a disposition and exact evidence."""
    _setup(store)
    marker = marker_view(store, marker_id)
    _gate(store, principal, "reviewer", audit, marker["decision_id"], marker["decision_version"], None, now)
    actor = principal.subject_id
    if actor == marker["outcome_recorder"]:
        raise MarkerError("the outcome's recorder cannot act on its marker")
    if expected_fingerprint != marker["fingerprint"]:
        raise MarkerError("stale or wrong marker fingerprint")
    if expected_event_seq != marker["event_seq"]:
        raise MarkerError("stale marker event history; reload the marker")
    if new_state not in _TRANSITIONS.get(marker["state"], set()):
        raise MarkerError(f"invalid marker transition from {marker['state']} to {new_state}")
    evidence_json = None
    if new_state == "resolved":
        if disposition not in DISPOSITIONS:
            raise MarkerError("resolution requires a recognised disposition")
        if (not isinstance(evidence_ref, Mapping) or set(evidence_ref) != _SOURCE_KEYS
                or not _HASH_RE.fullmatch(str(evidence_ref["content_hash"]))):
            raise MarkerError("resolution requires an exact evidence reference")
        evidence_json = _canonical(dict(evidence_ref))
    elif disposition or evidence_ref:
        raise MarkerError("disposition and evidence apply only to resolution")
    if new_state == "superseded":
        if not replacement_marker_id or replacement_marker_id == marker_id:
            raise MarkerError("supersession requires a different replacement marker")
        repl = marker_view(store, replacement_marker_id)
        if any(repl[k] != marker[k] for k in ("decision_id", "decision_version", "affected_type", "affected_ref")):
            raise MarkerError("replacement marker must cover the same decision version and affected object")
        if not isinstance(supersession_reason, str) or not _REASON_RE.fullmatch(supersession_reason):
            raise MarkerError("supersession requires a bounded reason code")
        evidence_json = _canonical({"supersession_reason": supersession_reason})
    elif replacement_marker_id or supersession_reason:
        raise MarkerError("replacement and reason apply only to supersession")
    seq = marker["event_seq"] + 1
    try:
        store.db.execute("INSERT INTO outcome_marker_events VALUES (?,?,?,?,?,?,?,?,?)",
                         (marker_id, seq, marker["state"], new_state, actor, _stamp(now), disposition,
                          evidence_json, replacement_marker_id))
        # Audit BEFORE commit: a failed audit append rolls the transition back, so a hold can never be
        # lifted (resolved-valid / superseded) without its durable audit event.
        _audit(audit, f"decision_marker_{new_state}", actor, marker["decision_id"], marker["decision_version"],
               marker_id, marker["fingerprint"], disposition or marker["reason_code"])
        store.db.commit()
    except Exception:
        store.db.rollback()
        raise
    return marker_view(store, marker_id)


__all__ = [
    "MarkerError", "advance_marker_as", "blocking_markers", "flag_corrected_outcome_as",
    "flag_disputed_outcome_as", "flag_source_hash_mismatch_as", "marker_view", "outcome_ref",
    "register_dependency_as", "replay_pending_audits", "source_ref",
]

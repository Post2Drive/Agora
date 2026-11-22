"""Outcome dependency review markers (M1; docs/OUTCOME_REVIEW_MARKERS_SPEC.md).

A marker says "this exact object must not be relied on until an authorised
reviewer records a disposition". Markers are append-only; current state is
derived from the event history. Dependencies are followed ONLY along explicit,
stored edges (never names, projects or heuristics). Opening a marker never
edits, deletes, approves or publishes anything. Synthetic data only; no engine.
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
from agora.decisions.outcomes import DecisionOutcomeStore, OutcomeError
from agora.decisions.schema import DecisionRecordError
from agora.principal import Principal, decide_principal

TRIGGERS = frozenset({
    "outcome_disputed", "outcome_corrected", "source_hash_mismatch", "source_revoked",
    "source_erased", "retention_expired", "decision_dependency_changed", "outcome_reopened",
})
DISPOSITIONS = frozenset({"still_valid", "needs_reissue", "remains_blocked", "superseded"})
BLOCKING_DISPOSITIONS = frozenset({"needs_reissue", "remains_blocked"})
_TRANSITIONS = {"open": {"acknowledged", "superseded"},
                "acknowledged": {"under_review", "superseded"},
                "under_review": {"resolved"}}
_REF = re.compile(r"^(outcome|source|decision|report|run):[A-Za-z0-9][A-Za-z0-9_.:/-]{0,200}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_DEPTH = 25
PROVENANCE_VERSION = "edges-v1"


class MarkerError(ValueError):
    """Raised when a marker operation violates the specification."""


class MarkerPermissionError(PermissionError):
    def __init__(self, decision: Mapping[str, Any]):
        super().__init__(str(decision.get("reason", "policy_denied")))
        self.decision = dict(decision)


def outcome_ref(decision_id: str, version: int, outcome_id: str) -> str:
    return f"outcome:{decision_id}/{version}/{outcome_id}"


def source_ref(source_registry_id: str, evidence_id: str, content_hash: str) -> str:
    return f"source:{source_registry_id}/{evidence_id}/{content_hash}"


def _ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise MarkerError(f"{field} must be an exact typed reference (outcome:/source:/decision:/report:/run:)")
    return value


def _token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise MarkerError(f"{field} must be a bounded identifier token")
    return value


def _stamp(now: datetime | str | None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise MarkerError("timestamps must be timezone-aware")
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class MarkerStore:
    """Marker tables living beside the outcome tables (same SQLite file)."""

    def __init__(self, outcomes: DecisionOutcomeStore):
        self.outcomes = outcomes
        self.db = outcomes.db
        self.db.execute("CREATE TABLE IF NOT EXISTS outcome_dependency_edges ("
                        "root_ref TEXT NOT NULL, dependent_ref TEXT NOT NULL, created_at TEXT NOT NULL, "
                        "PRIMARY KEY(root_ref, dependent_ref))")
        self.db.execute("CREATE TABLE IF NOT EXISTS outcome_markers ("
                        "marker_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, "
                        "trigger_type TEXT NOT NULL, trigger_event_id TEXT NOT NULL, root_ref TEXT NOT NULL, "
                        "affected_ref TEXT NOT NULL, dependency_path TEXT NOT NULL, reason_code TEXT NOT NULL, "
                        "created_at TEXT NOT NULL, provenance_version TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                        "scope_decision_id TEXT NOT NULL, scope_decision_version INTEGER NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS outcome_marker_events ("
                        "marker_id TEXT NOT NULL, seq INTEGER NOT NULL, prior_state TEXT NOT NULL, "
                        "new_state TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, "
                        "disposition TEXT, evidence_ref TEXT, replacement_marker_id TEXT, "
                        "PRIMARY KEY(marker_id, seq))")
        for table in ("outcome_dependency_edges", "outcome_markers", "outcome_marker_events"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS protect_{table}_{action.lower()} "
                                f"BEFORE {action} ON {table} BEGIN "
                                f"SELECT RAISE(ABORT, '{table} are append-only'); END")
        self.db.commit()

    # --- reads -------------------------------------------------------------
    def get(self, marker_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT marker_id,idempotency_key,trigger_type,trigger_event_id,root_ref,affected_ref,"
            "dependency_path,reason_code,created_at,provenance_version,fingerprint,"
            "scope_decision_id,scope_decision_version FROM outcome_markers WHERE marker_id=?",
            (marker_id,)).fetchone()
        if row is None:
            raise MarkerError("marker was not found")
        keys = ("marker_id", "idempotency_key", "trigger_type", "trigger_event_id", "root_ref",
                "affected_ref", "dependency_path", "reason_code", "created_at", "provenance_version",
                "fingerprint", "scope_decision_id", "scope_decision_version")
        out = dict(zip(keys, row))
        out["dependency_path"] = json.loads(out["dependency_path"])
        return out

    def events(self, marker_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seq,prior_state,new_state,actor,at,disposition,evidence_ref,replacement_marker_id "
            "FROM outcome_marker_events WHERE marker_id=? ORDER BY seq", (marker_id,)).fetchall()
        keys = ("seq", "prior_state", "new_state", "actor", "at", "disposition", "evidence_ref",
                "replacement_marker_id")
        return [dict(zip(keys, r)) for r in rows]

    def state(self, marker_id: str) -> str:
        self.get(marker_id)
        ev = self.events(marker_id)
        return ev[-1]["new_state"] if ev else "open"

    def dependents(self, ref: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT dependent_ref FROM outcome_dependency_edges WHERE root_ref=? ORDER BY dependent_ref",
            (ref,))]

    def is_blocking(self, marker_id: str) -> bool:
        ev = self.events(marker_id)
        if not ev:
            return True
        last = ev[-1]
        if last["new_state"] == "resolved":
            return last["disposition"] in BLOCKING_DISPOSITIONS
        return last["new_state"] != "superseded"

    def held_refs(self) -> dict[str, list[str]]:
        """Exact refs that must not be relied on -> blocking marker ids (read-only)."""
        held: dict[str, list[str]] = {}
        for marker_id, affected in self.db.execute(
                "SELECT marker_id, affected_ref FROM outcome_markers ORDER BY created_at, marker_id"):
            if self.is_blocking(marker_id):
                held.setdefault(affected, []).append(marker_id)
        return held

    def is_held(self, ref: str) -> bool:
        return ref in self.held_refs()

    def close(self) -> None:
        self.db.commit()


# --- internals ----------------------------------------------------------------

def _audit(audit: Any, event_type: str, actor: str, marker_id: str | None, *, decision: str = "allow",
           reason: str | None = None, policy_version: str | None = None, extra_ids: list[str] | None = None) -> None:
    if audit is None:
        return
    ids = ([marker_id] if marker_id else []) + (extra_ids or [])
    event: dict[str, Any] = {"event_id": f"{event_type}-{uuid.uuid4().hex}", "event_type": event_type,
                             "subject_id": actor, "operation": "outcome_marker", "decision": decision,
                             "resource_ids": ids}
    if reason:
        event["reason"] = reason
    if policy_version:
        event["policy_version"] = policy_version
    try:
        audit.append(event)
    except Exception as exc:
        raise MarkerError("marker change was stored but its audit event could not be appended; "
                          "treat the marker as pending reconciliation") from exc


def _gate(principal: Principal | None, role: str, store: MarkerStore, decision_id: str, version: int,
          audit: Any, now: Any) -> tuple[Principal, str | None]:
    if _protection.ANCHOR_REQUIRED:
        _require_anchored(audit)
    try:
        record = store.outcomes.decisions.get(decision_id, version)
    except DecisionRecordError as exc:
        raise MarkerError("decision version was not found") from exc
    res = dict(record.project_scope)
    res["resource_ids"] = [decision_id]
    res["source_sensitivity"] = "internal"
    moment = datetime.fromisoformat(_stamp(now).replace("Z", "+00:00")) if now is not None \
        else datetime.now(timezone.utc)
    decision, granted = decide_principal(principal, "decision_outcome", res, now=moment, required_role=role)
    if granted is None:
        _audit(audit, "outcome_marker_denied", decision["subject_id"], None, decision="deny",
               reason=str(decision.get("reason", "policy_denied")), policy_version=decision.get("policy_version"))
        raise MarkerPermissionError(decision)
    assert principal is not None
    return principal, decision.get("policy_version")


def _fingerprint(row: Mapping[str, Any]) -> str:
    body = {k: row[k] for k in ("marker_id", "idempotency_key", "trigger_type", "trigger_event_id",
                                "root_ref", "affected_ref", "dependency_path", "reason_code")}
    return hashlib.sha256(_canon(body).encode()).hexdigest()


def _traverse(store: MarkerStore, root: str) -> list[tuple[str, list[str]]]:
    """Breadth-first over explicit edges only; returns (ref, path-from-root), root first."""
    seen = {root}
    out: list[tuple[str, list[str]]] = [(root, [root])]
    frontier = [(root, [root])]
    for _ in range(_MAX_DEPTH):
        nxt: list[tuple[str, list[str]]] = []
        for ref, path in frontier:
            for dep in store.dependents(ref):
                if dep in seen:
                    continue
                seen.add(dep)
                item = (dep, path + [dep])
                out.append(item)
                nxt.append(item)
        if not nxt:
            break
        frontier = nxt
    return out


def _open(store: MarkerStore, *, trigger_type: str, trigger_event_id: str, root: str,
          scope: tuple[str, int], actor: str, now: Any, audit: Any, policy_version: str | None) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for affected, path in _traverse(store, root):
        key = hashlib.sha256(f"{trigger_event_id}|{trigger_type}|{affected}".encode()).hexdigest()
        existing = store.db.execute("SELECT marker_id FROM outcome_markers WHERE idempotency_key=?",
                                    (key,)).fetchone()
        if existing:
            continue  # duplicate delivery: idempotent no-op
        row = {"marker_id": f"marker-{key[:24]}", "idempotency_key": key, "trigger_type": trigger_type,
               "trigger_event_id": trigger_event_id, "root_ref": root, "affected_ref": affected,
               "dependency_path": path, "reason_code": trigger_type}
        fp = _fingerprint(row)
        try:
            store.db.execute(
                "INSERT INTO outcome_markers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["marker_id"], key, trigger_type, trigger_event_id, root, affected, _canon(path),
                 trigger_type, _stamp(now), PROVENANCE_VERSION, fp, scope[0], scope[1]))
            store.db.commit()
        except Exception:
            store.db.rollback()
            raise
        _audit(audit, "outcome_marker_opened", actor, row["marker_id"], reason=trigger_type,
               policy_version=policy_version)
        created.append({**row, "fingerprint": fp})
    return created


# --- public, Principal-bound API ----------------------------------------------

def register_dependency_as(store: MarkerStore, root_ref: str, dependent_ref: str, *,
                           principal: Principal | None, decision_id: str, decision_version: int,
                           audit: Any = None, now: Any = None) -> dict[str, str]:
    """Record an explicit lineage edge (dependent relied on root). Idempotent."""
    root, dep = _ref(root_ref, "root_ref"), _ref(dependent_ref, "dependent_ref")
    if root == dep:
        raise MarkerError("an object cannot depend on itself")
    actor, pv = _gate(principal, "operator", store, decision_id, decision_version, audit, now)
    store.db.execute("INSERT OR IGNORE INTO outcome_dependency_edges VALUES (?,?,?)", (root, dep, _stamp(now)))
    store.db.commit()
    _audit(audit, "outcome_dependency_registered", actor.subject_id, None, policy_version=pv)
    return {"root_ref": root, "dependent_ref": dep}


def open_markers_as(store: MarkerStore, trigger_type: str, root_ref: str, trigger_event_id: str, *,
                    principal: Principal | None, decision_id: str, decision_version: int,
                    audit: Any = None, now: Any = None) -> list[dict[str, Any]]:
    """Open a marker on the root and on every explicitly dependent object (idempotent)."""
    if trigger_type not in TRIGGERS:
        raise MarkerError("trigger_type is not a recognised bounded trigger")
    root, evt = _ref(root_ref, "root_ref"), _token(trigger_event_id, "trigger_event_id")
    actor, pv = _gate(principal, "reviewer", store, decision_id, decision_version, audit, now)
    return _open(store, trigger_type=trigger_type, trigger_event_id=evt, root=root,
                 scope=(decision_id, decision_version), actor=actor.subject_id, now=now, audit=audit,
                 policy_version=pv)


def sweep_outcome_triggers_as(store: MarkerStore, decision_id: str, decision_version: int, *,
                              principal: Principal | None, audit: Any = None, now: Any = None) -> list[dict[str, Any]]:
    """Open markers for disputed outcomes and for corrected (superseded) outcomes of one decision version."""
    actor, pv = _gate(principal, "reviewer", store, decision_id, decision_version, audit, now)
    scope, created = (decision_id, decision_version), []
    outs = store.outcomes.outcomes(decision_id, decision_version)
    for out in outs:
        oid = out["outcome_id"]
        if store.outcomes.state(decision_id, decision_version, oid) == "disputed":
            n = len(store.outcomes.reviews(decision_id, decision_version, oid))
            created += _open(store, trigger_type="outcome_disputed", trigger_event_id=f"review-{oid}-{n}",
                             root=outcome_ref(decision_id, decision_version, oid), scope=scope,
                             actor=actor.subject_id, now=now, audit=audit, policy_version=pv)
        old = out.get("supersedes_outcome_id")
        if old:
            created += _open(store, trigger_type="outcome_corrected", trigger_event_id=f"correction-{oid}",
                             root=outcome_ref(decision_id, decision_version, old), scope=scope,
                             actor=actor.subject_id, now=now, audit=audit, policy_version=pv)
    return created


def check_source_hash_as(store: MarkerStore, source_registry_id: str, evidence_id: str, current_hash: str, *,
                         principal: Principal | None, decision_id: str, decision_version: int,
                         audit: Any = None, now: Any = None) -> list[dict[str, Any]]:
    """Compare a source's current hash with every outcome citing it; mismatches open markers.

    Only outcomes whose recorded source_ref names this exact registry/evidence id
    and a DIFFERENT hash are affected (plus their explicit dependents). No match,
    or an unchanged hash, opens nothing. Hash drift is a hold, never a repair.
    """
    if not isinstance(current_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", current_hash):
        raise MarkerError("current_hash must be an exact sha256:<hex> hash")
    _token(source_registry_id, "source_registry_id"), _token(evidence_id, "evidence_id")
    actor, pv = _gate(principal, "reviewer", store, decision_id, decision_version, audit, now)
    created: list[dict[str, Any]] = []
    rows = store.db.execute("SELECT decision_id, decision_version, outcome_id, payload_json FROM decision_outcomes "
                            "ORDER BY decision_id, decision_version, outcome_id").fetchall()
    for d, v, oid, payload in rows:
        ref = json.loads(payload).get("source_ref", {})
        if ref.get("source_registry_id") != source_registry_id or ref.get("evidence_id") != evidence_id:
            continue
        if ref.get("content_hash") == current_hash:
            continue
        old_src = source_ref(source_registry_id, evidence_id, ref["content_hash"])
        # the source edge lets reviewers see why; edge is explicit and recorded
        store.db.execute("INSERT OR IGNORE INTO outcome_dependency_edges VALUES (?,?,?)",
                         (old_src, outcome_ref(d, v, oid), _stamp(now)))
        store.db.commit()
        created += _open(store, trigger_type="source_hash_mismatch",
                         trigger_event_id=f"hash-{current_hash[7:23]}", root=old_src,
                         scope=(decision_id, decision_version), actor=actor.subject_id, now=now,
                         audit=audit, policy_version=pv)
    return created


def _transition(store: MarkerStore, marker_id: str, new_state: str, principal: Principal | None, audit: Any,
                now: Any, *, disposition: str | None = None, evidence_ref: str | None = None,
                marker_fingerprint: str | None = None, replacement: str | None = None) -> dict[str, Any]:
    marker = store.get(marker_id)
    scope_d, scope_v = marker["scope_decision_id"], marker["scope_decision_version"]
    actor, pv = _gate(principal, "reviewer", store, scope_d, scope_v, audit, now)
    prior = store.state(marker_id)
    if new_state not in _TRANSITIONS.get(prior, set()):
        raise MarkerError(f"invalid marker transition from {prior} to {new_state}")
    # separation of duties: nobody reviews a marker over an outcome they recorded
    for ref in marker["dependency_path"]:
        if ref.startswith("outcome:"):
            d, v, o = ref[len("outcome:"):].split("/", 2)
            try:
                if store.outcomes.get(d, int(v), o)["recorder"] == actor.subject_id:
                    raise MarkerError("a marker reviewer must differ from the recorder of an outcome on its path")
            except OutcomeError:
                continue
    if new_state == "resolved":
        if marker_fingerprint != marker["fingerprint"]:
            raise MarkerError("resolution must cite the exact marker fingerprint")
        if disposition not in DISPOSITIONS - {"superseded"}:
            raise MarkerError("disposition must be still_valid, needs_reissue or remains_blocked")
        _token(evidence_ref, "evidence_ref")
    if new_state == "superseded":
        if not replacement or replacement == marker_id:
            raise MarkerError("supersession requires a different replacement marker")
        store.get(replacement)
    seq = len(store.events(marker_id)) + 1
    try:
        store.db.execute("INSERT INTO outcome_marker_events VALUES (?,?,?,?,?,?,?,?,?)",
                         (marker_id, seq, prior, new_state, actor.subject_id, _stamp(now), disposition,
                          evidence_ref, replacement))
        store.db.commit()
    except Exception:
        store.db.rollback()
        raise
    _audit(audit, f"outcome_marker_{new_state}", actor.subject_id, marker_id, reason=disposition,
           policy_version=pv)
    return {"marker_id": marker_id, "prior_state": prior, "new_state": new_state, "seq": seq}


def acknowledge_as(store: MarkerStore, marker_id: str, *, principal: Principal | None,
                   audit: Any = None, now: Any = None) -> dict[str, Any]:
    return _transition(store, marker_id, "acknowledged", principal, audit, now)


def start_review_as(store: MarkerStore, marker_id: str, *, principal: Principal | None,
                    audit: Any = None, now: Any = None) -> dict[str, Any]:
    return _transition(store, marker_id, "under_review", principal, audit, now)


def resolve_as(store: MarkerStore, marker_id: str, *, disposition: str, evidence_ref: str,
               marker_fingerprint: str, principal: Principal | None, audit: Any = None,
               now: Any = None) -> dict[str, Any]:
    return _transition(store, marker_id, "resolved", principal, audit, now, disposition=disposition,
                       evidence_ref=evidence_ref, marker_fingerprint=marker_fingerprint)


def supersede_as(store: MarkerStore, marker_id: str, replacement_marker_id: str, *,
                 principal: Principal | None, audit: Any = None, now: Any = None) -> dict[str, Any]:
    return _transition(store, marker_id, "superseded", principal, audit, now, replacement=replacement_marker_id)


__all__ = [
    "MarkerStore", "MarkerError", "MarkerPermissionError", "outcome_ref", "source_ref",
    "register_dependency_as", "open_markers_as", "sweep_outcome_triggers_as", "check_source_hash_as",
    "acknowledge_as", "start_review_as", "resolve_as", "supersede_as", "TRIGGERS",
]

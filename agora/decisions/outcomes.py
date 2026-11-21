"""Append-only observed outcomes and reviews for approved decision records.

Outcomes are evidence about what actually happened. They never modify a
decision record, and simulated output can never be stored as an observed
outcome. See docs/DECISION_OUTCOMES_SPEC.md.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from agora.audit_chain import AuditChainStore
from agora.policy import decide
from agora.principal import Principal, decide_principal

from .schema import DecisionRecordError
from .store import DecisionRecordStore


class OutcomeError(ValueError):
    """Raised when an outcome or review violates the specification."""


class OutcomePermissionError(PermissionError):
    """Raised when the policy decision point denies an outcome operation."""

    def __init__(self, decision: Mapping[str, Any]):
        self.decision = dict(decision)
        super().__init__(f"decision outcome denied: {decision.get('reason', 'policy_denied')}")


VALIDATION_STATUSES = frozenset({"unverified", "source_verified", "independently_checked"})
STATES = frozenset({"recorded", "reviewed", "disputed"})
_TRANSITIONS = {
    "recorded": {"reviewed", "disputed"},
    "disputed": {"reviewed"},
    "reviewed": {"disputed"},
}
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SOURCE_KEYS = {"source_registry_id", "evidence_id", "content_hash"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise OutcomeError(f"{field} must be an RFC3339 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise OutcomeError(f"{field} must be an RFC3339 timestamp") from None
    if result.tzinfo is None:
        raise OutcomeError(f"{field} must include a timezone")
    return result.astimezone(timezone.utc)


def _stamp(value: datetime | str | None) -> str:
    moment = datetime.now(timezone.utc) if value is None else (
        value if isinstance(value, datetime) else _utc(value, "now"))
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise OutcomeError(f"{field} must be a bounded identifier token")
    if value.casefold() == "latest":
        raise OutcomeError(f"{field} must be an exact identifier, not 'latest'")
    return value


class DecisionOutcomeStore:
    """Outcome tables living beside the decision records they refer to."""

    def __init__(self, decisions: DecisionRecordStore):
        self.decisions = decisions
        self.db = decisions.db
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS decision_outcomes (decision_id TEXT NOT NULL, "
            "decision_version INTEGER NOT NULL, outcome_id TEXT NOT NULL, measure TEXT NOT NULL, "
            "payload_json TEXT NOT NULL, PRIMARY KEY(decision_id, decision_version, outcome_id))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS decision_outcome_reviews (decision_id TEXT NOT NULL, "
            "decision_version INTEGER NOT NULL, outcome_id TEXT NOT NULL, seq INTEGER NOT NULL, "
            "prior_state TEXT NOT NULL, new_state TEXT NOT NULL, reviewer TEXT NOT NULL, "
            "reviewed_at TEXT NOT NULL, rationale_code TEXT NOT NULL, rationale_text TEXT, "
            "evidence_json TEXT, PRIMARY KEY(decision_id, decision_version, outcome_id, seq))"
        )
        for table in ("decision_outcomes", "decision_outcome_reviews"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS protect_{table}_{action.lower()} "
                    f"BEFORE {action} ON {table} BEGIN "
                    f"SELECT RAISE(ABORT, '{table} are append-only'); END"
                )
        self.db.commit()

    def get(self, decision_id: str, version: int, outcome_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT payload_json FROM decision_outcomes WHERE decision_id=? AND decision_version=? AND outcome_id=?",
            (decision_id, version, outcome_id),
        ).fetchone()
        if row is None:
            raise OutcomeError("outcome was not found")
        return json.loads(row[0])

    def outcomes(self, decision_id: str, version: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT payload_json FROM decision_outcomes WHERE decision_id=? AND decision_version=? ORDER BY rowid",
            (decision_id, version),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def reviews(self, decision_id: str, version: int, outcome_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seq, prior_state, new_state, reviewer, reviewed_at, rationale_code "
            "FROM decision_outcome_reviews WHERE decision_id=? AND decision_version=? AND outcome_id=? ORDER BY seq",
            (decision_id, version, outcome_id),
        ).fetchall()
        return [dict(zip(("seq", "prior_state", "new_state", "reviewer", "reviewed_at", "rationale_code"), r))
                for r in rows]

    def state(self, decision_id: str, version: int, outcome_id: str) -> str:
        self.get(decision_id, version, outcome_id)
        reviews = self.reviews(decision_id, version, outcome_id)
        return reviews[-1]["new_state"] if reviews else "recorded"

    def close(self) -> None:
        self.db.commit()


def _audit(
    audit: AuditChainStore | None, event_type: str, actor: str, decision_id: str, version: int,
    outcome_id: str | None, *, decision: str = "allow", reason: str | None = None,
    policy_version: str | None = None,
) -> None:
    if audit is None:
        return
    ids = [decision_id, f"version-{version}"] + ([outcome_id] if outcome_id else [])
    event: dict[str, Any] = {
        "event_id": f"{event_type}-{uuid.uuid4().hex}", "event_type": event_type,
        "subject_id": actor, "operation": "decision_outcome", "decision": decision,
        "resource_ids": ids,
    }
    if reason:
        event["reason"] = reason
    if policy_version:
        event["policy_version"] = policy_version
    try:
        audit.append(event)
    except Exception as exc:
        raise OutcomeError(
            "outcome change was stored but its audit event could not be appended"
        ) from exc


def _authorize(
    audit, subject: Mapping[str, Any], role: str, required_role: str, actor: str,
    decision_id: str, version: int, outcome_id: str | None, project_scope: Mapping[str, Any],
    resource: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(subject, Mapping) or subject.get("subject_id") != actor:
        raise OutcomeError("policy subject must identify the acting principal")
    policy_resource = dict(resource or {})
    policy_resource.update(project_scope)
    policy_resource["resource_ids"] = [decision_id] + ([outcome_id] if outcome_id else [])
    policy_resource.setdefault("source_sensitivity", "internal")
    result = decide(subject, role, "decision_outcome", policy_resource)
    if result.get("decision") == "allow" and role != required_role:
        result = dict(result, decision="deny", reason="role_not_permitted_for_this_action")
    if result.get("decision") != "allow":
        _audit(audit, "decision_outcome_denied", actor, decision_id, version, outcome_id,
               decision="deny", reason=str(result.get("reason", "policy_denied")),
               policy_version=result.get("policy_version"))
        raise OutcomePermissionError(result)
    return result


def record_outcome(
    store: DecisionOutcomeStore,
    *,
    decision_id: str,
    decision_version: int,
    measure: str,
    observed_value: Any,
    unit: str,
    observed_at: str,
    measurement_window: Mapping[str, Any],
    source_ref: Mapping[str, Any],
    provenance_class: str,
    validation_status: str,
    recorder: str,
    role: str,
    subject: Mapping[str, Any],
    outcome_id: str | None = None,
    notes: str | None = None,
    supersedes_outcome_id: str | None = None,
    resource: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
    audit: AuditChainStore | None = None,
) -> dict[str, Any]:
    """Append one observed outcome for an exact approved decision version."""
    try:
        record = store.decisions.get(decision_id, decision_version)
    except DecisionRecordError as exc:
        raise OutcomeError("decision version was not found") from exc
    if record.status != "approved":
        raise OutcomeError("outcomes can only be recorded against an approved decision version")
    if measure not in record.outcome_measures:
        raise OutcomeError("measure is not one of the decision's outcome_measures")
    if provenance_class != "observed":
        raise OutcomeError("only observed evidence can be recorded; simulated output is not an outcome")
    if validation_status not in VALIDATION_STATUSES:
        raise OutcomeError("validation_status is not recognised")
    if isinstance(observed_value, bool) or isinstance(observed_value, str):
        pass
    elif isinstance(observed_value, (int, float)):
        if not math.isfinite(observed_value):
            raise OutcomeError("observed_value must be finite")
    else:
        raise OutcomeError("observed_value must be a string, finite number or boolean")
    if isinstance(observed_value, str) and not observed_value.strip():
        raise OutcomeError("observed_value must not be empty")
    if not isinstance(unit, str) or not unit.strip() or len(unit) > 100:
        raise OutcomeError("unit must be non-empty bounded text")
    if notes is not None and (not isinstance(notes, str) or len(notes) > 500):
        raise OutcomeError("notes must be text of at most 500 characters")
    at = _utc(observed_at, "observed_at")
    if not isinstance(measurement_window, Mapping) or set(measurement_window) != {"start", "end"}:
        raise OutcomeError("measurement_window requires exactly start and end")
    start, end = _utc(measurement_window["start"], "window.start"), _utc(measurement_window["end"], "window.end")
    if start > end or not start <= at <= end:
        raise OutcomeError("observed_at must fall inside the measurement window")
    if not isinstance(source_ref, Mapping) or set(source_ref) != _SOURCE_KEYS:
        raise OutcomeError("source_ref requires source_registry_id, evidence_id and content_hash")
    _token(source_ref["source_registry_id"], "source_ref.source_registry_id")
    _token(source_ref["evidence_id"], "source_ref.evidence_id")
    if not isinstance(source_ref["content_hash"], str) or not _HASH_RE.fullmatch(source_ref["content_hash"]):
        raise OutcomeError("source_ref.content_hash must be an exact sha256 hash")
    new_id = _token(outcome_id, "outcome_id") if outcome_id is not None else uuid.uuid4().hex
    if supersedes_outcome_id is not None:
        try:
            prior = store.get(decision_id, decision_version, supersedes_outcome_id)
        except OutcomeError as exc:
            raise OutcomeError("superseded outcome was not found for this decision version") from exc
        if prior["measure"] != measure or supersedes_outcome_id == new_id:
            raise OutcomeError("a correction must reference a different outcome of the same measure")

    policy = _authorize(audit, subject, role, "operator", recorder, decision_id, decision_version,
                        new_id, record.project_scope, resource)
    payload = {
        "decision_id": decision_id, "decision_version": decision_version, "outcome_id": new_id,
        "measure": measure, "observed_value": observed_value, "unit": unit.strip(),
        "observed_at": _stamp(at), "measurement_window": {"start": _stamp(start), "end": _stamp(end)},
        "source_ref": dict(source_ref), "provenance_class": "observed",
        "validation_status": validation_status, "recorder": recorder, "recorded_at": _stamp(now),
        "decision_fingerprint": record.fingerprint,
    }
    if notes:
        payload["notes"] = notes
    if supersedes_outcome_id:
        payload["supersedes_outcome_id"] = supersedes_outcome_id
    try:
        store.db.execute(
            "INSERT INTO decision_outcomes VALUES (?,?,?,?,?)",
            (decision_id, decision_version, new_id, measure, _canonical(payload)),
        )
        store.db.commit()
    except Exception as exc:
        store.db.rollback()
        if "UNIQUE" in str(exc) or "PRIMARY" in str(exc):
            raise OutcomeError("outcome_id already exists") from exc
        raise
    _audit(audit, "decision_outcome_correction_appended" if supersedes_outcome_id
           else "decision_outcome_recorded", recorder, decision_id, decision_version, new_id,
           policy_version=policy.get("policy_version"))
    return payload


def review_outcome(
    store: DecisionOutcomeStore,
    decision_id: str,
    decision_version: int,
    outcome_id: str,
    *,
    new_state: str,
    reviewer: str,
    role: str,
    subject: Mapping[str, Any],
    rationale_code: str,
    rationale_text: str | None = None,
    evidence_ref: Mapping[str, Any] | None = None,
    resource: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
    audit: AuditChainStore | None = None,
) -> dict[str, Any]:
    """Append a review event; the reviewer must differ from the recorder."""
    outcome = store.get(decision_id, decision_version, outcome_id)
    record = store.decisions.get(decision_id, decision_version)
    if new_state not in {"reviewed", "disputed"}:
        raise OutcomeError("new_state must be reviewed or disputed")
    if not isinstance(rationale_code, str) or not _TOKEN_RE.fullmatch(rationale_code):
        raise OutcomeError("rationale_code must be a bounded identifier token")
    if rationale_text is not None and (not isinstance(rationale_text, str) or len(rationale_text) > 500):
        raise OutcomeError("rationale_text must be text of at most 500 characters")
    if reviewer == outcome["recorder"]:
        raise OutcomeError("a reviewer must differ from the outcome's recorder")
    prior = store.state(decision_id, decision_version, outcome_id)
    if new_state not in _TRANSITIONS.get(prior, set()):
        raise OutcomeError(f"invalid outcome transition from {prior} to {new_state}")
    policy = _authorize(audit, subject, role, "reviewer", reviewer, decision_id, decision_version,
                        outcome_id, record.project_scope, resource)
    seq = len(store.reviews(decision_id, decision_version, outcome_id)) + 1
    stamp = _stamp(now)
    try:
        store.db.execute(
            "INSERT INTO decision_outcome_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (decision_id, decision_version, outcome_id, seq, prior, new_state, reviewer, stamp,
             rationale_code, rationale_text, _canonical(dict(evidence_ref)) if evidence_ref else None),
        )
        store.db.commit()
    except Exception:
        store.db.rollback()
        raise
    _audit(audit, f"decision_outcome_{new_state}", reviewer, decision_id, decision_version,
           outcome_id, policy_version=policy.get("policy_version"))
    return {"outcome_id": outcome_id, "prior_state": prior, "new_state": new_state,
            "reviewer": reviewer, "reviewed_at": stamp, "seq": seq}


def _principal_gate(
    principal: Principal | None, required_role: str, audit: AuditChainStore | None,
    store: DecisionOutcomeStore, decision_id: str, decision_version: int,
    outcome_id: str | None, resource: Mapping[str, Any] | None, now: Any,
) -> None:
    try:
        record = store.decisions.get(decision_id, decision_version)
    except DecisionRecordError as exc:
        raise OutcomeError("decision version was not found") from exc
    res = dict(resource or {})
    res.update(record.project_scope)
    res["resource_ids"] = [decision_id] + ([outcome_id] if outcome_id else [])
    res.setdefault("source_sensitivity", "internal")
    moment = _utc(now, "now") if now is not None else datetime.now(timezone.utc)
    decision, role = decide_principal(principal, "decision_outcome", res, now=moment,
                                      required_role=required_role)
    if role is None:
        _audit(audit, "decision_outcome_denied", decision["subject_id"], decision_id,
               decision_version, outcome_id, decision="deny",
               reason=str(decision.get("reason", "policy_denied")),
               policy_version=decision.get("policy_version"))
        raise OutcomePermissionError(decision)


def _project(store: DecisionOutcomeStore, decision_id: str, version: int) -> str:
    return store.decisions.get(decision_id, version).project_scope["project_id"]


def record_outcome_as(store: DecisionOutcomeStore, *, principal: Principal | None, **kwargs: Any) -> dict[str, Any]:
    """record_outcome with recorder/role/subject derived from a trusted principal."""
    for banned in ("recorder", "role", "subject"):
        if banned in kwargs:
            raise OutcomeError(f"{banned} is derived from the principal and must not be supplied")
    _principal_gate(principal, "operator", kwargs.get("audit"), store, kwargs["decision_id"],
                    kwargs["decision_version"], kwargs.get("outcome_id"), kwargs.get("resource"),
                    kwargs.get("now"))
    return record_outcome(store, recorder=principal.subject_id, role="operator",
                          subject={"subject_id": principal.subject_id, "project_id": _project(store, kwargs["decision_id"], kwargs["decision_version"])}, **kwargs)


def review_outcome_as(store: DecisionOutcomeStore, decision_id: str, decision_version: int,
                      outcome_id: str, *, principal: Principal | None, **kwargs: Any) -> dict[str, Any]:
    """review_outcome with reviewer/role/subject derived from a trusted principal."""
    for banned in ("reviewer", "role", "subject"):
        if banned in kwargs:
            raise OutcomeError(f"{banned} is derived from the principal and must not be supplied")
    _principal_gate(principal, "reviewer", kwargs.get("audit"), store, decision_id,
                    decision_version, outcome_id, kwargs.get("resource"), kwargs.get("now"))
    return review_outcome(store, decision_id, decision_version, outcome_id,
                          reviewer=principal.subject_id, role="reviewer",
                          subject={"subject_id": principal.subject_id, "project_id": _project(store, decision_id, decision_version)}, **kwargs)


__all__ = [
    "record_outcome_as", "review_outcome_as",
    "DecisionOutcomeStore", "OutcomeError", "OutcomePermissionError", "record_outcome",
    "review_outcome",
]

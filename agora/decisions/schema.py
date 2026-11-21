"""Fail-closed, immutable decision-record schema primitives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from datetime import date, datetime
import re
from typing import Any, Mapping


class DecisionRecordError(ValueError):
    """Raised when a decision record violates the Rung 5 contract."""


STATUSES = frozenset({"draft", "proposed", "approved", "rejected", "superseded"})
_REQUIRED = {
    "decision_id", "version", "project_scope", "status", "statement", "alternatives",
    "evidence_refs", "rationale", "assumptions", "uncertainty", "outcome_measures",
    "proposer", "reviewer", "created_at", "updated_at", "approval_method", "review_date",
}
_OPTIONAL = {"approver", "supersedes", "fingerprint"}
_REF_KINDS = {"import", "binding", "ontology_pack", "run", "scenario"}
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    body = {key: payload[key] for key in sorted(payload) if key != "fingerprint"}
    return "sha256:" + hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionRecordError(f"{field} must be non-empty text")
    return value.strip()


def _list_text(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise DecisionRecordError(f"{field} must be a list of non-empty text")
    return [item.strip() for item in value]


def _reject_latest(value: Any) -> None:
    if isinstance(value, str) and value.strip().lower() == "latest":
        raise DecisionRecordError("evidence references must use exact immutable IDs, not latest")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_latest(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_latest(nested)


def _validate_ref(ref: Mapping[str, Any]) -> None:
    kind = _text(ref.get("kind"), "evidence_refs.kind")
    if kind not in _REF_KINDS:
        raise DecisionRecordError("unsupported evidence reference kind")
    forbidden = {"head", "*"}
    for value in ref.values():
        if isinstance(value, str) and value.strip().lower() in forbidden:
            raise DecisionRecordError("evidence references must use exact immutable IDs")
    if kind == "import":
        _text(ref.get("import_id"), "evidence_refs.import_id")
    elif kind in {"binding", "ontology_pack"}:
        fingerprint = _text(ref.get("fingerprint"), "evidence_refs.fingerprint")
        if not _HASH_RE.fullmatch(fingerprint):
            raise DecisionRecordError("binding and ontology references require a sha256 fingerprint")
    elif kind == "run":
        _text(ref.get("run_id"), "evidence_refs.run_id")
        if ref.get("mode") != "exploratory":
            raise DecisionRecordError("run evidence must be labelled exploratory")
    elif kind == "scenario":
        scenario_hash = _text(ref.get("scenario_hash"), "evidence_refs.scenario_hash")
        if not _HASH_RE.fullmatch(scenario_hash):
            raise DecisionRecordError("scenario references require a sha256 scenario_hash")
        if ref.get("mode") != "exploratory":
            raise DecisionRecordError("scenario evidence must be labelled exploratory")


def _validate_timestamps(payload: Mapping[str, Any]) -> None:
    try:
        for field in ("created_at", "updated_at"):
            parsed = datetime.fromisoformat(_text(payload[field], field).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        date.fromisoformat(_text(payload["review_date"], "review_date"))
    except (TypeError, ValueError):
        raise DecisionRecordError("timestamps must be RFC3339 and review_date must be an ISO date") from None
@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    version: int
    project_scope: dict[str, Any]
    status: str
    statement: str
    alternatives: list[str]
    evidence_refs: list[dict[str, Any]]
    rationale: str
    assumptions: list[str]
    uncertainty: list[str]
    outcome_measures: list[str]
    proposer: str
    reviewer: str
    created_at: str
    updated_at: str
    approval_method: str
    review_date: str
    approver: str | None = None
    supersedes: str | None = None
    fingerprint: str = ""

    def as_dict(self) -> dict[str, Any]:
        value = {
            "decision_id": self.decision_id, "version": self.version, "project_scope": dict(self.project_scope),
            "status": self.status, "statement": self.statement, "alternatives": list(self.alternatives),
            "evidence_refs": [dict(item) for item in self.evidence_refs], "rationale": self.rationale,
            "assumptions": list(self.assumptions), "uncertainty": list(self.uncertainty),
            "outcome_measures": list(self.outcome_measures), "proposer": self.proposer, "reviewer": self.reviewer,
            "created_at": self.created_at, "updated_at": self.updated_at, "approval_method": self.approval_method,
            "review_date": self.review_date,
        }
        if self.approver is not None:
            value["approver"] = self.approver
        if self.supersedes is not None:
            value["supersedes"] = self.supersedes
        value["fingerprint"] = self.fingerprint
        return value


def load_decision_record(payload: Mapping[str, Any]) -> DecisionRecord:
    if not isinstance(payload, Mapping):
        raise DecisionRecordError("decision record must be an object")
    unknown = set(payload) - (_REQUIRED | _OPTIONAL)
    missing = _REQUIRED - set(payload)
    if unknown:
        raise DecisionRecordError(f"unknown decision record fields: {', '.join(sorted(unknown))}")
    if missing:
        raise DecisionRecordError(f"missing decision record fields: {', '.join(sorted(missing))}")
    decision_id = _text(payload["decision_id"], "decision_id")
    version = payload["version"]
    if type(version) is not int or version < 1:
        raise DecisionRecordError("version must be a positive integer")
    scope = payload["project_scope"]
    if not isinstance(scope, Mapping) or not scope:
        raise DecisionRecordError("project_scope must be a non-empty object")
    status = _text(payload["status"], "status")
    if status not in STATUSES:
        raise DecisionRecordError("unsupported decision status")
    refs = payload["evidence_refs"]
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, Mapping) or not ref for ref in refs):
        raise DecisionRecordError("evidence_refs must be a non-empty list of objects")
    for ref in refs:
        _validate_ref(ref)
    _reject_latest(refs)
    _validate_timestamps(payload)
    approver = payload.get("approver")
    if status == "approved":
        approver = _text(approver, "approver")
        if approver == _text(payload["proposer"], "proposer"):
            raise DecisionRecordError("approver must differ from proposer")
    body = {
        "decision_id": decision_id, "version": version, "project_scope": dict(scope), "status": status,
        "statement": _text(payload["statement"], "statement"), "alternatives": _list_text(payload["alternatives"], "alternatives"),
        "evidence_refs": [dict(ref) for ref in refs], "rationale": _text(payload["rationale"], "rationale"),
        "assumptions": _list_text(payload["assumptions"], "assumptions"), "uncertainty": _list_text(payload["uncertainty"], "uncertainty"),
        "outcome_measures": _list_text(payload["outcome_measures"], "outcome_measures"), "proposer": _text(payload["proposer"], "proposer"),
        "reviewer": _text(payload["reviewer"], "reviewer"), "created_at": _text(payload["created_at"], "created_at"),
        "updated_at": _text(payload["updated_at"], "updated_at"), "approval_method": _text(payload["approval_method"], "approval_method"),
        "review_date": _text(payload["review_date"], "review_date"),
    }
    for optional in ("approver", "supersedes"):
        if optional in payload and payload[optional] is not None:
            body[optional] = _text(payload[optional], optional)
    if status == "approved":
        body["approver"] = approver
    fingerprint = _fingerprint(body)
    if payload.get("fingerprint") is not None and payload["fingerprint"] != fingerprint:
        raise DecisionRecordError("decision record fingerprint does not match content")
    return DecisionRecord(**body, fingerprint=fingerprint)


__all__ = ["DecisionRecord", "DecisionRecordError", "STATUSES", "load_decision_record"]

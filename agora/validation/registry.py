"""Append-only, domain-scoped validation registry and review lifecycle.

Registry entries capture immutable evaluation evidence. Status changes and
review decisions are separate hash-chained events; no existing entry is edited.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import audit_log
from .json_io import strict_json_loads

STATES = {"not_assessed", "protocol_drafted", "data_reviewed", "evaluation_pending",
          "passed", "failed", "inconclusive", "expired"}
TRANSITIONS = {
    "not_assessed": {"protocol_drafted"},
    "protocol_drafted": {"data_reviewed"},
    "data_reviewed": {"evaluation_pending"},
    "evaluation_pending": {"passed", "failed", "inconclusive"},
    "passed": set(), "failed": set(), "inconclusive": set(), "expired": set(),
}
REQUIRED = ("domain", "use_case", "target", "population", "geography", "horizon",
            "data_provenance", "holdout_design", "baselines", "metrics", "thresholds",
            "results", "uncertainty", "model_version", "config_hash", "limitations",
            "approved_claims", "reviewer")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_FIELDS = ("domain", "use_case", "target", "population", "geography", "horizon")


def review_path(path: str | Path) -> Path:
    p = Path(path)
    return p.with_name("reviews.jsonl")


def _registry_lock(path: str | Path):
    """Return the shared cross-process lock for all registry operations."""
    p = Path(path)
    return audit_log._exclusive_lock(p.with_name(p.name + ".lock"))


def _read(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    raw = p.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Validation registry has an incomplete final JSONL record")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Validation registry is not valid UTF-8") from exc
    out = []
    for line_no, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            raise ValueError(f"Blank validation registry line {line_no}")
        try:
            row = strict_json_loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid registry JSON line {line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Validation registry line {line_no} must be an object")
        if not isinstance(row.get("registry_id"), str) or not row["registry_id"].strip():
            raise ValueError(f"Validation registry line {line_no} has no registry_id")
        if any(old["registry_id"] == row["registry_id"] for old in out):
            raise ValueError(f"Duplicate registry_id on line {line_no}: {row['registry_id']}")
        out.append(row)
    return out


def _read_reviews(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    state = audit_log.verify(p)
    if not state["valid"]:
        raise ValueError(f"Validation review history integrity failure at line {state.get('line')}: {state.get('reason')}")
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        row = strict_json_loads(line)
        if row.get("event_type") == "validation_status_transition":
            required = ("registry_id", "from_status", "to_status", "reviewer", "rationale", "evidence_refs", "registry_hash")
            if any(not row.get(key) for key in required):
                raise ValueError("Malformed validation review event: missing reviewer, rationale, evidence or transition fields")
            if not isinstance(row.get("evidence_refs"), list) or any(not isinstance(x, str) or not x.strip() for x in row["evidence_refs"]):
                raise ValueError("Malformed validation review event: invalid evidence_refs")
            if not isinstance(row.get("registry_hash"), str) or not _SHA256.fullmatch(row["registry_hash"]):
                raise ValueError("Malformed validation review event: invalid registry_hash")
            rows.append(row)
    return rows


def _status_for(registry_id: str, rows: Sequence[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    status = "not_assessed"
    latest = None
    for row in rows:
        if row.get("registry_id") != registry_id:
            continue
        if row.get("from_status") != status or row.get("to_status") not in TRANSITIONS.get(status, set()):
            raise ValueError(f"Invalid validation status history for {registry_id}")
        status = row["to_status"]
        latest = row
    return status, latest


def _validate_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise TypeError("Validation registry entry must be an object")
    missing = [k for k in REQUIRED if k not in entry or entry[k] in (None, "", [], {})]
    # Approved claims are assigned only by a passed review, not at registration.
    missing = [k for k in missing if k != "approved_claims"]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    row = dict(entry)
    if row.get("approved_claims") not in (None, []):
        raise ValueError("approved_claims can only be assigned by a passed review")
    if "registry_id" in row and (not isinstance(row["registry_id"], str) or not row["registry_id"].strip()):
        raise ValueError("registry_id must be a non-empty string")
    if row.get("status", "not_assessed") != "not_assessed":
        raise ValueError("New validation entries must start at not_assessed; use review transitions")
    row["status"] = "not_assessed"
    for key in _SCOPE_FIELDS:
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    if not isinstance(row.get("model_version"), str) or not row["model_version"].strip():
        raise ValueError("model_version must be a non-empty string")
    if not isinstance(row.get("config_hash"), str) or not _SHA256.fullmatch(row["config_hash"]):
        raise ValueError("config_hash must be a lowercase SHA-256 digest")
    for key in ("data_provenance", "holdout_design", "baselines", "metrics", "thresholds", "results", "uncertainty"):
        if not isinstance(row.get(key), dict) or not row[key]:
            raise ValueError(f"{key} must be a non-empty object")
    hashes = row["data_provenance"].get("source_hashes")
    if not isinstance(hashes, dict) or not hashes or any(
            not isinstance(source_id, str) or not source_id.strip()
            or not isinstance(digest, str) or not _SHA256.fullmatch(digest)
            for source_id, digest in hashes.items()):
        raise ValueError("data_provenance.source_hashes must map source IDs to lowercase SHA-256 digests")
    holdout = row["holdout_design"]
    if not isinstance(holdout.get("protocol_fingerprint"), str) or not _SHA256.fullmatch(holdout["protocol_fingerprint"]):
        raise ValueError("holdout_design.protocol_fingerprint must be a lowercase SHA-256 digest")
    for count_name in ("n_train", "n_test"):
        if isinstance(holdout.get(count_name), bool) or not isinstance(holdout.get(count_name), int) or holdout[count_name] < 1:
            raise ValueError(f"holdout_design.{count_name} must be a positive integer")
    if not isinstance(row.get("limitations"), (str, list)) or not row["limitations"]:
        raise ValueError("limitations must be a non-empty string or list")
    if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
        raise ValueError("reviewer must identify the evaluation owner/reviewer")
    return row


def _entry_hash(entry: Mapping[str, Any]) -> str:
    encoded = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def add_entry(path: str | Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Register immutable evidence, always beginning at not_assessed."""
    p = Path(path)
    row = _validate_entry(entry)
    now = datetime.now(timezone.utc).isoformat()
    row.setdefault("registry_id", "val-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    row.setdefault("created_at", now)
    row["registered_at"] = now
    row["approved_claims"] = []
    p.parent.mkdir(parents=True, exist_ok=True)
    # Normalise to the exact JSON types that will be persisted before hashing.
    row = json.loads(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str))
    with _registry_lock(p):
        rows = _read(p)
        if any(x["registry_id"] == row["registry_id"] for x in rows):
            raise ValueError("Duplicate registry_id")
        encoded = json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write while appending validation registry record")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
    return row


def transition_entry(path: str | Path, registry_id: str, to_status: str, *,
                     reviewer: str, rationale: str, evidence_refs: Sequence[str],
                     approved_claims: Sequence[str] | None = None,
                     expires_at: str | None = None,
                     reviews_file: str | Path | None = None) -> dict[str, Any]:
    """Append a review decision; prior evidence and review events are never edited."""
    p = Path(path)
    rp = Path(reviews_file) if reviews_file else review_path(p)
    if to_status not in STATES or to_status == "expired":
        raise ValueError("Invalid target status; expired is computed from the approval expiry")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("A named reviewer is required")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("Review rationale is required")
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs or any(not isinstance(x, str) or not x.strip() for x in evidence_refs):
        raise ValueError("At least one non-empty evidence reference is required")
    claims = list(approved_claims or [])
    if any(not isinstance(x, str) or not x.strip() for x in claims) or len(set(claims)) != len(claims):
        raise ValueError("approved_claims must contain unique non-empty strings")
    if to_status == "passed":
        if not claims:
            raise ValueError("A passed review must explicitly list approved_claims")
        if not expires_at:
            raise ValueError("A passed review must set expires_at")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("expires_at must be an ISO-8601 timestamp with timezone") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be a future timezone-aware timestamp")
    elif claims or expires_at:
        raise ValueError("approved_claims and expires_at are only valid for a passed review")

    # Serialise state-check + append so two reviewers cannot both transition from
    # the same previous state. audit_log.append has its own lock for chain integrity.
    rp.parent.mkdir(parents=True, exist_ok=True)
    with _registry_lock(p):
        entries = {r["registry_id"]: r for r in _read(p)}
        if registry_id not in entries:
            raise KeyError(f"Unknown registry_id: {registry_id}")
        history = _read_reviews(rp)
        current, _ = _status_for(registry_id, history)
        if to_status not in TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid status transition: {current} -> {to_status}")
        base = entries[registry_id]
        base_hash = _entry_hash(base)
        if any(event.get("registry_hash") != base_hash for event in history
               if event.get("registry_id") == registry_id):
            raise ValueError("Registered evidence changed after its review history began")
        if to_status == "passed":
            missing = [key for key in ("data_provenance", "holdout_design", "baselines", "metrics",
                                        "thresholds", "results", "uncertainty", "limitations", "model_version", "config_hash")
                       if not base.get(key)]
            if missing:
                raise ValueError("Cannot pass incomplete evidence: " + ", ".join(missing))
            assessment = (base.get("results") or {}).get("threshold_assessment")
            if not isinstance(assessment, dict) or assessment.get("overall") != "pass":
                raise ValueError("Cannot pass: registered evaluation threshold_assessment.overall must be 'pass'")
            if not (base.get("holdout_design") or {}).get("protocol_fingerprint"):
                raise ValueError("Cannot pass: holdout_design must include protocol_fingerprint")
            if not (base.get("data_provenance") or {}).get("source_hashes"):
                raise ValueError("Cannot pass: data_provenance must include source_hashes")
        event = {
            "event_type": "validation_status_transition", "registry_id": registry_id,
            "from_status": current, "to_status": to_status, "reviewer": reviewer.strip(),
            "rationale": rationale.strip(), "evidence_refs": list(evidence_refs),
            "registry_hash": base_hash,
        }
        if to_status == "passed":
            event.update({"approved_claims": claims, "expires_at": expires_at})
        return audit_log.append(rp, event)


def list_entries(path: str | Path, *, reviews_file: str | Path | None = None) -> list[dict[str, Any]]:
    p = Path(path)
    with _registry_lock(p):
        rows = _read(p)
        history = _read_reviews(reviews_file or review_path(p))
        out = []
        for row in rows:
            digest = _entry_hash(row)
            if any(event.get("registry_hash") != digest for event in history
                   if event.get("registry_id") == row["registry_id"]):
                raise ValueError(f"Registered validation evidence changed after review: {row['registry_id']}")
            status, latest = _status_for(row["registry_id"], history)
            current = dict(row)
            current["status"] = status
            current["latest_review"] = latest
            if status == "passed" and latest:
                exp = datetime.fromisoformat(latest["expires_at"].replace("Z", "+00:00"))
                if exp <= datetime.now(timezone.utc):
                    current["status"] = "expired"
            out.append(current)
        return out


def require_approval(path: str | Path, registry_id: str, *, domain: str, use_case: str,
                     target: str, population: str, geography: str, horizon: str,
                     model_version: str, config_hash: str,
                     requested_claims: Sequence[str], reviews_file: str | Path | None = None) -> dict[str, Any]:
    """Require a current passed review matching every scope field and each claim."""
    if not isinstance(requested_claims, (list, tuple)) or not requested_claims:
        raise PermissionError("At least one requested claim is required")
    p = Path(path)
    with _registry_lock(p):
        rows = {r["registry_id"]: r for r in _read(p)}
        if registry_id not in rows:
            raise PermissionError("Validation registry entry not found")
        r = rows[registry_id]
        history = _read_reviews(reviews_file or review_path(p))
        base_hash = _entry_hash(r)
        if any(event.get("registry_hash") != base_hash for event in history
               if event.get("registry_id") == registry_id):
            raise PermissionError("Registered validation evidence changed after review")
        status, latest = _status_for(registry_id, history)
        if status != "passed" or latest is None:
            raise PermissionError(f"Registry status is {status!r}, not passed")
        exp = latest.get("expires_at")
        try:
            expiry = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, AttributeError):
            raise PermissionError("Invalid or timezone-naive approval expiry")
        if expiry <= datetime.now(timezone.utc):
            raise PermissionError("Validation approval has expired")
        wanted = {"domain": domain, "use_case": use_case, "target": target,
                  "population": population, "geography": geography, "horizon": horizon,
                  "model_version": model_version, "config_hash": config_hash}
        mismatch = [key for key, value in wanted.items() if r.get(key) != value]
        if mismatch:
            raise PermissionError("Approval scope mismatch: " + ", ".join(mismatch))
        if not isinstance(latest.get("reviewer"), str) or not latest["reviewer"].strip() or not latest.get("rationale"):
            raise PermissionError("Passed review is missing reviewer identity or rationale")
        if not isinstance(latest.get("evidence_refs"), list) or not latest["evidence_refs"]:
            raise PermissionError("Passed review is missing reviewer evidence references")
        approved = latest.get("approved_claims")
        if not isinstance(approved, list) or not approved or any(not isinstance(x, str) or not x.strip() for x in approved):
            raise PermissionError("No valid approved claims recorded in the passed review")
        if any(not isinstance(x, str) or not x.strip() for x in requested_claims):
            raise PermissionError("Requested claims must be non-empty strings")
        unapproved = sorted(set(requested_claims) - set(approved))
        if unapproved:
            raise PermissionError("Unapproved claim(s): " + ", ".join(unapproved))
        return {**r, "status": "passed", "approved_claims": approved,
                "reviewer": latest["reviewer"], "reviewed_at": latest["recorded_at"],
                "expires_at": latest["expires_at"], "review_evidence_refs": latest["evidence_refs"],
                "review_hash": latest["entry_hash"]}

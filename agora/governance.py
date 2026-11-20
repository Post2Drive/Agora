# Shared governance helpers for provenance and audit events.
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid


_OPERATION_STATES = {"pending", "committed", "failed"}


def _operation_rows(project):
    path = Path(project) / "governance" / "operations.jsonl"
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid operation journal JSON on line {line_no}") from exc
        if (not isinstance(row, dict) or not row.get("operation_id")
                or row.get("status") not in _OPERATION_STATES):
            raise ValueError(f"Invalid operation journal record on line {line_no}")
        prior = next((item for item in reversed(rows)
                      if item["operation_id"] == row["operation_id"]), None)
        if prior is None:
            if row["status"] != "pending":
                raise ValueError(f"Operation must begin pending on line {line_no}")
        else:
            if prior["status"] != "pending" or row["status"] not in {"committed", "failed"}:
                raise ValueError(f"Invalid operation state transition on line {line_no}")
            for field in ("operation_type", "created_at", "source_ids", "details"):
                if row.get(field) != prior.get(field):
                    raise ValueError(f"Operation identity changed on line {line_no}")
        rows.append(row)
    return rows


def list_operations(project):
    """Return the append-only operation journal in recorded order."""
    return _operation_rows(project)


def operation_states(project):
    """Return the latest known state for each operation ID."""
    latest = {}
    for row in _operation_rows(project):
        latest[row["operation_id"]] = row
    return latest


def pending_operations(project):
    """Return operations needing manual reconciliation; never retries them automatically."""
    return [row for row in operation_states(project).values() if row["status"] == "pending"]


def _append_operation(project, row):
    path = Path(project) / "governance" / "operations.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def begin_operation(project, operation_type, *, source_ids=(), details=None):
    """Record intent before a provenance-bearing write; pending records require manual recovery."""
    operation_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    row = {"operation_id": operation_id, "operation_type": str(operation_type),
           "status": "pending", "created_at": now, "updated_at": now,
           "source_ids": list(source_ids), "details": details or {}}
    _append_operation(project, row)
    return row


def finish_operation(project, operation_id, status, *, error=None, details=None):
    """Append a terminal state for a pending operation; terminal states cannot be rewritten."""
    if status not in {"committed", "failed"}:
        raise ValueError("Final operation status must be committed or failed")
    current = operation_states(project).get(str(operation_id))
    if current is None:
        raise KeyError(f"Unknown operation_id: {operation_id}")
    if current["status"] != "pending":
        raise ValueError(f"Operation is already {current['status']}")
    row = dict(current)
    row.update({"status": status, "updated_at": datetime.now(timezone.utc).isoformat()})
    if error is not None:
        row["error"] = str(error)
    if details:
        row["completion_details"] = details
    _append_operation(project, row)
    return row

def record_source(project, *, source_id, content, data_role, source_url="", publisher="", author="",
                  acquired_at=None, published_at=None, licence="", geography="", population="",
                  parser_version="", extraction_status="not_assessed", quality_flags=None, reviewer=""):
    """Register source metadata and a content hash; source bytes remain in their owning data store."""
    from .sources.registry import register_source
    project = Path(project)
    return register_source(project / "governance" / "sources.jsonl", source_id=source_id,
        content=content, source_url=source_url, publisher=publisher, author=author,
        acquired_at=acquired_at, published_at=published_at, licence=licence, geography=geography,
        population=population, data_role=data_role, parser_version=parser_version,
        extraction_status=extraction_status, quality_flags=quality_flags, reviewer=reviewer)

def audit_event(project, event_type, **details):
    from .validation.audit_log import append
    return append(Path(project) / "governance" / "audit.jsonl", {
        "event_type": event_type, "recorded_at": datetime.now(timezone.utc).isoformat(), **details})

def source_roles(project):
    from .sources.registry import list_sources
    path = Path(project) / "governance" / "sources.jsonl"
    return {row["source_id"]: row["data_role"] for row in list_sources(path)}

def require_registered_source(project, source_path, *, allowed_roles=("calibration",)):
    project, source_path = Path(project), Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Required source file not found: {source_path}")
    from .sources.registry import list_sources
    registry = project / "governance" / "sources.jsonl"
    if not registry.is_file():
        raise PermissionError(f"{source_path.name} has no provenance registration. Re-upload it through Agora's data upload flow.")
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    matches = [row for row in list_sources(registry) if row.get("sha256") == digest]
    if not matches:
        raise PermissionError(f"{source_path.name} does not match a registered source hash. Re-upload it through Agora's data upload flow.")
    roles = {row.get("data_role") for row in matches}
    if "sealed_holdout" in roles:
        raise PermissionError("Sealed holdout data cannot be used for calibration or ordinary backtesting.")
    invalid = roles - set(allowed_roles)
    if invalid:
        raise PermissionError(f"{source_path.name} has conflicting or non-permitted registered roles: {', '.join(sorted(map(str, invalid)))}.")
    return sorted({str(row["source_id"]) for row in matches})

def reject_sealed_holdout_for_calibration(project, source_id):
    role = source_roles(project).get(str(source_id))
    if role == "sealed_holdout":
        raise PermissionError("Sealed holdout data cannot be used for calibration")
    return role

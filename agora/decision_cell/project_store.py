"""Stored, versioned, audited project record: the gate's trusted project input.

DECISION_CELL_SPEC sections 2A and 9.3: the designated project owner is named in the project record and is
the approver; nobody else is a delegate until the owner records that exact person for that project.

Rules in this version:

* The first version can be written only by a high-assurance approver who belongs to the project, and only
  naming themself as owner. The first successful write wins.
* Later versions can be written only by the recorded owner (same permission). Delegates and the second
  approver cannot change the record. The owner cannot be changed; ownership transfer is not built.
* Versions are append-only. A write must name the version it replaces, so a stale edit is refused.
* Each version row is inserted in the same SQLite transaction as its anchored audit event, which carries the
  hash of the whole row. Every read compares all rows with all such events and refuses on any difference, so
  a removed, added or edited row (including a roll back to an older delegate list) is detected.

Limits: the anchor is a local sidecar (see agora.audit_anchor); someone who can rewrite both the database and
the anchor file, or run code in this process, is outside this protection. First-writer ownership means project
membership and the approver role must be granted with care by the identity layer. Read cost grows with the
audit chain, which is re-verified on every read. ``audit`` and ``tenant_id`` come from the service's own
configuration, never from a request.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agora.audit_anchor import AnchoredAuditChain, require_anchored, verify_anchored
from agora.audit_chain import AuditReplayError
from agora.decision_cell.options import DecisionCellError, GateResult, OptionRequest, ProjectRecord, request_option
from agora.policy import POLICY_VERSION
from agora.principal import Principal, decide_principal

EVENT_PREFIX = "dc-project-record-"
EVENT_TYPE = "decision_cell_project_record"
TABLE = "decision_cell_project_records"

_SCHEMA = {
    TABLE: (
        "CREATE TABLE decision_cell_project_records (tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, "
        "version INTEGER NOT NULL, body_json TEXT NOT NULL, audit_event_id TEXT NOT NULL UNIQUE, "
        "PRIMARY KEY (tenant_id, project_id, version))"
    ),
    "protect_dc_project_record_update": (
        "CREATE TRIGGER protect_dc_project_record_update BEFORE UPDATE ON decision_cell_project_records "
        "BEGIN SELECT RAISE(ABORT, 'project records are append-only'); END"
    ),
    "protect_dc_project_record_delete": (
        "CREATE TRIGGER protect_dc_project_record_delete BEFORE DELETE ON decision_cell_project_records "
        "BEGIN SELECT RAISE(ABORT, 'project records are append-only'); END"
    ),
}
_BODY_KEYS = frozenset({
    "tenant_id", "project_id", "version", "owner_subject_id", "delegate_subject_ids",
    "second_approver_subject_id", "requires_second_approval", "written_by_subject_id",
})
# Written only when a backup is named, so records stored before the field existed keep their exact form.
_BACKUP_KEY = "backup_contact_subject_id"


class ProjectRecordError(DecisionCellError):
    """A refused write or an untrustworthy store. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class StoredProjectRecord:
    record: ProjectRecord
    version: int
    record_hash: str


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _event_id(tenant_id: str, project_id: str, version: int) -> str:
    return EVENT_PREFIX + _hash(_canonical([tenant_id, project_id, version]))


def _identifier(value: Any) -> bool:
    """Exact identity strings only: no padding that could make two records look alike."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return value.isprintable()


def _writer(audit: Any) -> AnchoredAuditChain:
    try:
        return require_anchored(audit)
    except PermissionError as exc:
        raise ProjectRecordError("AUDIT_REQUIRED", "an anchored audit writer is required") from exc


def _objects(db: sqlite3.Connection) -> dict[str, str]:
    rows = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE (lower(tbl_name)=? OR lower(name)=?) AND sql IS NOT NULL",
        (TABLE, TABLE),
    ).fetchall()
    return {name: sql for name, sql in rows}


def _record_events(db: sqlite3.Connection) -> dict[str, Any]:
    rows = db.execute(
        "SELECT event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=?",
        (len(EVENT_PREFIX), EVENT_PREFIX),
    ).fetchall()
    return {event_id: json.loads(raw) for event_id, raw in rows}


def _checked_rows(db: sqlite3.Connection, events: Mapping[str, Any]) -> list[tuple[str, str, int, str, str]]:
    """Every stored row, only if the table is exactly as created and matches the chain events one for one."""
    objects = _objects(db)
    if not objects:
        if events:
            raise ProjectRecordError("STORE_INCONSISTENT", "audited record versions have no table")
        return []
    if objects != _SCHEMA:
        raise ProjectRecordError("STORE_SCHEMA", "table or triggers are not as this version creates them")
    rows = db.execute(
        f"SELECT tenant_id, project_id, version, body_json, audit_event_id FROM {TABLE}").fetchall()
    if len(rows) != len(events) or {r[4] for r in rows} != set(events):
        raise ProjectRecordError("STORE_INCONSISTENT", "record rows do not match the audit chain")
    for tenant_id, project_id, version, body_json, event_id in rows:
        if (type(version) is not int or not isinstance(body_json, str) or not body_json.isascii()
                or event_id != _event_id(tenant_id, project_id, version)
                or events[event_id].get("record_hash") != _hash(body_json)):
            raise ProjectRecordError("STORE_INCONSISTENT", "a record row differs from its audited hash")
    return rows


def _latest(rows: list[tuple[str, str, int, str, str]], tenant_id: str,
            project_id: str) -> StoredProjectRecord | None:
    mine = sorted((r for r in rows if r[0] == tenant_id and r[1] == project_id), key=lambda r: r[2])
    if not mine:
        return None
    if [r[2] for r in mine] != list(range(1, len(mine) + 1)):
        raise ProjectRecordError("STORE_INCONSISTENT", "record versions are not contiguous")
    _, _, version, body_json, _ = mine[-1]
    body = json.loads(body_json)
    if (not isinstance(body, dict) or set(body) - {_BACKUP_KEY} != _BODY_KEYS
            or (_BACKUP_KEY in body and not _identifier(body[_BACKUP_KEY]))
            or body["tenant_id"] != tenant_id
            or body["project_id"] != project_id or body["version"] != version):
        raise ProjectRecordError("STORE_INCONSISTENT", "record body does not match its row")
    record = ProjectRecord(
        project_id=project_id, tenant_id=tenant_id, owner_subject_id=body["owner_subject_id"],
        delegate_subject_ids=frozenset(body["delegate_subject_ids"]),
        second_approver_subject_id=body["second_approver_subject_id"],
        requires_second_approval=body["requires_second_approval"],
        backup_contact_subject_id=body.get(_BACKUP_KEY),
    )
    return StoredProjectRecord(record, version, _hash(body_json))


def load_project_record(*, tenant_id: str, project_id: str,
                        audit: AnchoredAuditChain) -> StoredProjectRecord | None:
    """The latest version, or None if none was ever written. Raises if the store cannot be trusted.

    A trusted service-side read: it performs no caller permission check.
    """
    writer = _writer(audit)
    try:
        with writer.anchors.lock():
            state = verify_anchored(writer.chain, writer.anchors)
            if not state["valid"]:
                raise ProjectRecordError("AUDIT_UNANCHORED", state["status"])
            db = writer.chain.db
            return _latest(_checked_rows(db, _record_events(db)), tenant_id, project_id)
    except ProjectRecordError:
        raise
    except Exception as exc:
        raise ProjectRecordError("STORE_ERROR", "the project record could not be read") from exc


def write_project_record(
    principal: Principal | None, record: ProjectRecord, *, expected_version: int,
    audit: AnchoredAuditChain, now: datetime | None = None,
) -> StoredProjectRecord:
    """Write the next version. ``expected_version`` is 0 to create, else the version being replaced.

    Refused attempts are audited. Raises ``ProjectRecordError``; nothing was changed unless the code is
    ``AUDIT_ANCHOR_WRITE_FAILED`` (the version is committed but unanchored, so every later read refuses
    until an operator reconciles the anchor).
    """
    writer = _writer(audit)
    if not isinstance(record, ProjectRecord):
        raise ProjectRecordError("RECORD_INVALID", "a ProjectRecord is required")
    if not _identifier(record.project_id) or not _identifier(record.tenant_id):
        raise ProjectRecordError("RECORD_INVALID", "project and tenant ids must be exact non-empty strings")
    subject = principal.subject_id if isinstance(principal, Principal) else "unknown"
    scope = [f"tenant:{record.tenant_id}", f"project:{record.project_id}"]

    def refuse(code: str, detail: str = "") -> ProjectRecordError:
        try:
            writer.append({
                "event_id": f"dc-project-denied-{uuid.uuid4().hex}",
                "event_type": "decision_cell_project_record_denied", "subject_id": subject,
                "operation": "decision_cell_project_record_write", "decision": "deny",
                "policy_version": POLICY_VERSION, "reason": code, "resource_ids": scope,
            })
        except Exception as exc:
            raise ProjectRecordError("AUDIT_FAILED", f"refused ({code}) and the refusal could not be recorded") from exc
        return ProjectRecordError(code, detail)

    decision, role = decide_principal(
        principal, "decision_approval",
        {"project_id": record.project_id, "tenant_id": record.tenant_id, "source_sensitivity": "internal"},
        now=now, required_role="approver")
    if role is None:
        raise refuse("NOT_PERMITTED", decision["reason"])

    delegates = record.delegate_subject_ids
    second = record.second_approver_subject_id
    if not _identifier(record.owner_subject_id):
        raise refuse("RECORD_INVALID", "owner")
    if not isinstance(delegates, frozenset) or not all(_identifier(d) for d in delegates):
        raise refuse("RECORD_INVALID", "delegates must be a frozenset of exact ids")
    if record.owner_subject_id in delegates:
        raise refuse("RECORD_INVALID", "the owner is not a delegate")
    if second is not None and (not _identifier(second) or second == record.owner_subject_id):
        raise refuse("RECORD_INVALID", "the second approver must be another exact id")
    backup = record.backup_contact_subject_id
    if backup is not None and (not _identifier(backup) or backup == record.owner_subject_id):
        raise refuse("RECORD_INVALID", "the backup contact must be another exact id")
    if type(record.requires_second_approval) is not bool:
        raise refuse("RECORD_INVALID", "requires_second_approval must be true or false")
    if record.requires_second_approval and second is None:
        raise refuse("RECORD_INVALID", "a required second approval needs a named second approver")
    if type(expected_version) is not int or expected_version < 0:
        raise refuse("VERSION_CONFLICT", "expected_version")

    current = load_project_record(tenant_id=record.tenant_id, project_id=record.project_id, audit=writer)
    if (current.version if current else 0) != expected_version:
        raise refuse("VERSION_CONFLICT", "the record changed or does not exist at that version")
    # Authority comes from the stored version, never from the record being written.
    owner = current.record.owner_subject_id if current else record.owner_subject_id
    if subject != owner:
        raise refuse("NOT_OWNER")
    if record.owner_subject_id != owner:
        raise refuse("OWNER_IMMUTABLE")

    version = expected_version + 1
    body = {
        "tenant_id": record.tenant_id, "project_id": record.project_id, "version": version,
        "owner_subject_id": record.owner_subject_id, "delegate_subject_ids": sorted(delegates),
        "second_approver_subject_id": second,
        "requires_second_approval": record.requires_second_approval, "written_by_subject_id": subject,
    }
    if backup is not None:
        body[_BACKUP_KEY] = backup
    body_json = _canonical(body)
    record_hash = _hash(body_json)
    event_id = _event_id(record.tenant_id, record.project_id, version)

    def within_transaction(db: sqlite3.Connection) -> None:
        events = _record_events(db)
        events.pop(event_id)  # this write's own event, inserted just before this callback
        _checked_rows(db, events)
        if not _objects(db):
            for statement in _SCHEMA.values():
                db.execute(statement)
        db.execute(
            f"INSERT INTO {TABLE}(tenant_id,project_id,version,body_json,audit_event_id) VALUES (?,?,?,?,?)",
            (record.tenant_id, record.project_id, version, body_json, event_id))

    event = {
        "event_id": event_id, "event_type": EVENT_TYPE, "subject_id": subject,
        "operation": "decision_cell_project_record_write", "decision": "allow",
        "policy_version": POLICY_VERSION, "count": version, "record_hash": record_hash,
        "resource_ids": scope,
    }
    try:
        writer.append(event, in_transaction=within_transaction)
    except ProjectRecordError:
        raise
    except AuditReplayError as exc:
        # Another writer committed this version after our check.
        raise ProjectRecordError("VERSION_CONFLICT", "this version was written concurrently") from exc
    except Exception as exc:
        from agora.audit_anchor import AnchorWriteError
        if isinstance(exc, AnchorWriteError):
            raise ProjectRecordError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; do not rely on it") from exc
        raise ProjectRecordError("STORE_ERROR", "the version could not be committed") from exc
    return StoredProjectRecord(
        ProjectRecord(record.project_id, record.tenant_id, record.owner_subject_id, delegates, second,
                      record.requires_second_approval, backup), version, record_hash)


def request_project_option(
    principal: Principal | None, request: OptionRequest, *, tenant_id: str, project_id: str,
    audit: AnchoredAuditChain, **context: Any,
) -> GateResult:
    """``request_option`` with the project record taken from the store instead of from the caller.

    With no stored record every option is blocked and the attempt is audited. An untrustworthy store raises.
    As with the gate itself, the result is not an authorization token: call again immediately before acting.
    """
    if "record" in context or "record_hash" in context:
        raise ProjectRecordError("RECORD_INVALID", "the project record cannot be supplied by the caller")
    if {"evidence_hash", "item_statements", "audit_flags", "in_transaction"} & set(context):
        # Only request_labelled_option, which reads the labels itself, binds evidence to an attempt.
        raise ProjectRecordError("RECORD_INVALID", "evidence cannot be supplied by the caller")
    stored = load_project_record(tenant_id=tenant_id, project_id=project_id, audit=audit)
    record = stored.record if stored else ProjectRecord(project_id, tenant_id, "")
    return request_option(principal, request, record=record, audit=audit,
                          record_hash=stored.record_hash if stored else None, **context)


__all__ = ["ProjectRecordError", "StoredProjectRecord", "load_project_record", "request_project_option",
           "write_project_record"]

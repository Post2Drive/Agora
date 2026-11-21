"""Project-local append-only decision-record storage."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Mapping

from .schema import DecisionRecord, DecisionRecordError, load_decision_record


class DecisionRecordStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS decision_records (decision_id TEXT NOT NULL, "
            "version INTEGER NOT NULL, fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "PRIMARY KEY(decision_id, version))"
        )
        self.db.execute(
            "CREATE TRIGGER IF NOT EXISTS protect_decision_record_update "
            "BEFORE UPDATE ON decision_records BEGIN "
            "SELECT RAISE(ABORT, 'decision records are append-only'); END"
        )
        self.db.execute(
            "CREATE TRIGGER IF NOT EXISTS protect_decision_record_delete "
            "BEFORE DELETE ON decision_records BEGIN "
            "SELECT RAISE(ABORT, 'decision records are append-only'); END"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS decision_approval_events ("
            "event_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL, version INTEGER NOT NULL, "
            "transition TEXT NOT NULL, actor TEXT NOT NULL, method TEXT NOT NULL, "
            "occurred_at TEXT NOT NULL, decision_fingerprint TEXT NOT NULL, "
            "policy_decision_json TEXT, details_json TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TRIGGER IF NOT EXISTS protect_decision_approval_event_update "
            "BEFORE UPDATE ON decision_approval_events BEGIN "
            "SELECT RAISE(ABORT, 'decision approval events are append-only'); END"
        )
        self.db.execute(
            "CREATE TRIGGER IF NOT EXISTS protect_decision_approval_event_delete "
            "BEFORE DELETE ON decision_approval_events BEGIN "
            "SELECT RAISE(ABORT, 'decision approval events are append-only'); END"
        )
        self.db.commit()

    def append(self, record: DecisionRecord | dict) -> DecisionRecord:
        """Append a non-approved record version.

        Approved versions must use append_transition(), which verifies the
        prior proposed version and persists its policy decision and audit event.
        """
        record = record if isinstance(record, DecisionRecord) else load_decision_record(record)
        if record.status == "approved":
            raise DecisionRecordError(
                "approved records must be appended through a valid approval transition"
            )
        payload = record.as_dict()
        existing = self.db.execute(
            "SELECT payload_json FROM decision_records WHERE decision_id=? AND version=?",
            (record.decision_id, record.version),
        ).fetchone()
        if existing is not None:
            if json.loads(existing[0]) != payload:
                raise DecisionRecordError("decision version already exists with different content")
            return record
        self.db.execute(
            "INSERT INTO decision_records VALUES (?,?,?,?)",
            (record.decision_id, record.version, record.fingerprint,
             json.dumps(payload, sort_keys=True, separators=(",", ":"))),
        )
        self.db.commit()
        return record

    def append_transition(
        self,
        record: DecisionRecord | dict,
        event: Mapping[str, Any],
        *,
        policy_decision: Mapping[str, Any] | None = None,
    ) -> DecisionRecord:
        """Atomically append a lifecycle version and its immutable audit event."""
        record = record if isinstance(record, DecisionRecord) else load_decision_record(record)
        if not isinstance(event, Mapping):
            raise DecisionRecordError("transition audit event must be an object")
        required = {"transition", "actor", "method", "occurred_at", "decision_fingerprint"}
        if not required.issubset(event):
            raise DecisionRecordError("transition audit event is incomplete")
        transition, actor, method, occurred_at = (
            event["transition"], event["actor"], event["method"], event["occurred_at"]
        )
        if not all(isinstance(value, str) and value.strip()
                   for value in (transition, actor, method, occurred_at)):
            raise DecisionRecordError("transition audit event fields must be non-empty text")
        if event["decision_fingerprint"] != record.fingerprint or occurred_at != record.updated_at:
            raise DecisionRecordError("transition audit event does not match the record version")
        if transition == "approved" and record.status != "approved":
            raise DecisionRecordError("approved event requires an approved record")
        if record.status == "approved" and transition != "approved":
            raise DecisionRecordError("approved record requires an approved transition event")
        if record.status == "approved":
            if not isinstance(policy_decision, Mapping) or policy_decision.get("decision") != "allow":
                raise DecisionRecordError("approved transition requires an allow policy decision")
            if policy_decision.get("subject_id") != actor or record.approver != actor:
                raise DecisionRecordError("approval actor does not match the policy decision")
            if actor in {record.proposer, record.reviewer}:
                raise DecisionRecordError("approver must differ from proposer and reviewer")
        elif policy_decision is not None:
            raise DecisionRecordError("policy decision is only valid for approval transitions")

        payload = record.as_dict()
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        policy_json = (json.dumps(dict(policy_decision), sort_keys=True, separators=(",", ":"))
                       if policy_decision is not None else None)
        details = {key: value for key, value in event.items() if key not in required}
        details_json = json.dumps(details, sort_keys=True, separators=(",", ":"))

        try:
            self.db.execute("BEGIN IMMEDIATE")
            previous_row = self.db.execute(
                "SELECT payload_json FROM decision_records WHERE decision_id=? AND version=?",
                (record.decision_id, record.version - 1),
            ).fetchone()
            if previous_row is None:
                raise DecisionRecordError("transition requires the immediately preceding record version")
            previous = load_decision_record(json.loads(previous_row[0]))
            if record.version != previous.version + 1 or record.supersedes != previous.fingerprint:
                raise DecisionRecordError("transition version or previous fingerprint is stale")
            allowed = {
                "draft": {"proposed"},
                "proposed": {"approved", "rejected", "superseded"},
                "approved": {"superseded"},
                "rejected": {"superseded"},
            }
            if record.status not in allowed.get(previous.status, set()):
                raise DecisionRecordError("invalid decision lifecycle transition")
            mutable = {"version", "status", "updated_at", "approval_method",
                       "approver", "supersedes", "fingerprint"}
            old_body = {key: value for key, value in previous.as_dict().items() if key not in mutable}
            new_body = {key: value for key, value in record.as_dict().items() if key not in mutable}
            if old_body != new_body:
                raise DecisionRecordError("transition cannot change decision content, scope, or evidence")
            if record.status == "approved":
                if previous.status != "proposed":
                    raise DecisionRecordError("only a proposed record can be approved")
                if record.approver != actor:
                    raise DecisionRecordError("approved record must name the transition actor")
            self.db.execute(
                "INSERT INTO decision_records VALUES (?,?,?,?)",
                (record.decision_id, record.version, record.fingerprint, payload_json),
            )
            self.db.execute(
                "INSERT INTO decision_approval_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), record.decision_id, record.version, transition, actor,
                 method, occurred_at, record.fingerprint, policy_json, details_json),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return record

    def approval_events(self, decision_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT version, transition, actor, method, occurred_at, decision_fingerprint, "
            "policy_decision_json, details_json FROM decision_approval_events "
            "WHERE decision_id=? ORDER BY version",
            (decision_id,),
        ).fetchall()
        return [
            {"version": row[0], "transition": row[1], "actor": row[2], "method": row[3],
             "occurred_at": row[4], "decision_fingerprint": row[5],
             "policy_decision": json.loads(row[6]) if row[6] else None,
             "details": json.loads(row[7])}
            for row in rows
        ]

    def get(self, decision_id: str, version: int) -> DecisionRecord:
        row = self.db.execute(
            "SELECT payload_json FROM decision_records WHERE decision_id=? AND version=?",
            (decision_id, version),
        ).fetchone()
        if row is None:
            raise DecisionRecordError("decision record version was not found")
        return load_decision_record(json.loads(row[0]))

    def versions(self, decision_id: str) -> list[DecisionRecord]:
        rows = self.db.execute(
            "SELECT payload_json FROM decision_records WHERE decision_id=? ORDER BY version",
            (decision_id,),
        ).fetchall()
        return [load_decision_record(json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self.db.close()


__all__ = ["DecisionRecordStore"]

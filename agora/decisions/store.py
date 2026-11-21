"""Project-local append-only decision-record storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import DecisionRecord, DecisionRecordError, load_decision_record


class DecisionRecordStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("CREATE TABLE IF NOT EXISTS decision_records (decision_id TEXT NOT NULL, version INTEGER NOT NULL, fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(decision_id, version))")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_decision_record_update BEFORE UPDATE ON decision_records BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_decision_record_delete BEFORE DELETE ON decision_records BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END")
        self.db.commit()

    def append(self, record: DecisionRecord | dict) -> DecisionRecord:
        record = record if isinstance(record, DecisionRecord) else load_decision_record(record)
        payload = record.as_dict()
        existing = self.db.execute("SELECT payload_json FROM decision_records WHERE decision_id=? AND version=?", (record.decision_id, record.version)).fetchone()
        if existing is not None:
            if json.loads(existing[0]) != payload:
                raise DecisionRecordError("decision version already exists with different content")
            return record
        self.db.execute("INSERT INTO decision_records VALUES (?,?,?,?)", (record.decision_id, record.version, record.fingerprint, json.dumps(payload, sort_keys=True, separators=(",", ":"))))
        self.db.commit()
        return record

    def get(self, decision_id: str, version: int) -> DecisionRecord:
        row = self.db.execute("SELECT payload_json FROM decision_records WHERE decision_id=? AND version=?", (decision_id, version)).fetchone()
        if row is None:
            raise DecisionRecordError("decision record version was not found")
        return load_decision_record(json.loads(row[0]))

    def versions(self, decision_id: str) -> list[DecisionRecord]:
        rows = self.db.execute("SELECT payload_json FROM decision_records WHERE decision_id=? ORDER BY version", (decision_id,)).fetchall()
        return [load_decision_record(json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self.db.close()


__all__ = ["DecisionRecordStore"]

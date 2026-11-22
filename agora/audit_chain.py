"""Standalone append-only, redacted hash-chain audit storage."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Protocol


GENESIS = "0" * 64
_SAFE_KEYS = {
    "event_id", "event_type", "subject_id", "operation", "decision", "policy_version",
    "resource_ids", "reason", "recorded_at", "count", "sequence", "duration_ms",
}
_SAFE_SUFFIXES = ("_hash", "_fingerprint")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _redact(value: Any, key: str | None = None) -> Any:
    if key is not None:
        normalized = key.casefold()
        if normalized not in _SAFE_KEYS and not normalized.endswith(_SAFE_SUFFIXES):
            return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def redact_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return an audit-safe copy with personal/sensitive fields removed."""
    if not isinstance(event, Mapping) or not event:
        raise ValueError("audit event must be a non-empty mapping")
    return _redact(dict(event))


class AuditAppender(Protocol):
    """Structural type for anything that can durably append an audit event.

    Satisfied by AuditChainStore and by AnchoredAuditChain (anchor-checked writer).
    """

    def append(self, event: Mapping[str, Any]) -> Any: ...


def verify_rows(rows: Any) -> tuple[str, int | None]:
    """Verify (seq,event_id,previous_hash,event_json,event_hash) rows in order.

    Returns (last_hash, None) when intact, or ("", first_broken_sequence).
    """
    previous = GENESIS
    for seq, _event_id, prior, raw, stored in rows:
        if prior != previous:
            return "", seq
        try:
            event = json.loads(raw)
            actual = hashlib.sha256(_canonical({"previous_hash": prior, "event": event}).encode()).hexdigest()
        except (ValueError, TypeError, json.JSONDecodeError):
            return "", seq
        if actual != stored:
            return "", seq
        previous = stored
    return previous, None


class AuditChainStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path), timeout=5.0)
        self.db.execute("CREATE TABLE IF NOT EXISTS audit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, previous_hash TEXT NOT NULL, event_json TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE, recorded_at TEXT NOT NULL)")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_audit_event_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit chain is append-only'); END")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_audit_event_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit chain is append-only'); END")
        self.db.commit()

    def _state(self) -> tuple[str, int | None]:
        rows = self.db.execute("SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq").fetchall()
        return verify_rows(rows)

    def append(self, event: Mapping[str, Any]) -> dict[str, Any]:
        safe = redact_event(event)
        event_id = safe.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("audit event requires a non-empty event_id")
        if any(key in safe for key in ("previous_hash", "event_hash")):
            raise ValueError("hash fields are reserved")
        if "recorded_at" not in safe:
            safe["recorded_at"] = datetime.now(timezone.utc).isoformat()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous, broken = self._state()
            if broken is not None:
                raise ValueError(f"audit chain is broken at sequence {broken}")
            if self.db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (event_id,)).fetchone():
                raise ValueError("audit event replay detected")
            event_hash = hashlib.sha256(_canonical({"previous_hash": previous, "event": safe}).encode()).hexdigest()
            self.db.execute("INSERT INTO audit_events(event_id,previous_hash,event_json,event_hash,recorded_at) VALUES (?,?,?,?,?)", (event_id, previous, _canonical(safe), event_hash, safe["recorded_at"]))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"event_id": event_id, "previous_hash": previous, "event": safe, "event_hash": event_hash}

    def find_event(self, event_id: str) -> dict[str, Any] | None:
        """Read-only lookup of a committed event by id (stored, redacted form); None when absent."""
        row = self.db.execute("SELECT event_json FROM audit_events WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def verify(self) -> dict[str, Any]:
        previous, broken = self._state()
        if broken:
            return {"valid": False, "first_broken_sequence": broken}
        return {"valid": True, "entries": self.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], "last_hash": previous}

    def close(self) -> None:
        self.db.close()


__all__ = ["AuditAppender", "AuditChainStore", "GENESIS", "redact_event", "verify_rows"]

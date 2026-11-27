"""Standalone append-only, redacted hash-chain audit storage."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Protocol


from agora.pathsafe import require_safe_path

GENESIS = "0" * 64
# How long a writer waits for another writer's lock before append() raises "database is locked". SQLite does
# not queue waiters, and each append re-verifies the whole chain while holding the lock, so on a slow disk a
# few busy writers can keep one waiting well past a short timeout. The wait stays bounded.
BUSY_TIMEOUT_SECONDS = 30.0
_SAFE_KEYS = {
    "event_id", "event_type", "subject_id", "operation", "decision", "policy_version",
    "resource_ids", "reason", "recorded_at", "count", "sequence", "duration_ms",
    # A fixed classification word on an action proposal record, never free text.
    "proposal_sensitivity",
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


class AuditReplayError(ValueError):
    """An event with this event_id is already committed to the chain."""


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
        self.path = require_safe_path(path)  # UnsafePathError before SQLite can follow a link
        self.db = sqlite3.connect(str(self.path), timeout=BUSY_TIMEOUT_SECONDS)
        self.db.execute("CREATE TABLE IF NOT EXISTS audit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, previous_hash TEXT NOT NULL, event_json TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE, recorded_at TEXT NOT NULL)")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_audit_event_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit chain is append-only'); END")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS protect_audit_event_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit chain is append-only'); END")
        self.db.commit()

    def _state(self) -> tuple[str, int | None]:
        rows = self.db.execute("SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq").fetchall()
        return verify_rows(rows)

    def append(
        self, event: Mapping[str, Any], *,
        in_transaction: Callable[[sqlite3.Connection], None] | None = None,
    ) -> dict[str, Any]:
        """Append one event.

        ``in_transaction``, when given, runs on this store's connection after the event row is inserted and
        before the commit, so its writes commit or roll back together with the event. It must not commit,
        roll back or start a transaction itself. Anything it raises rolls back both.
        """
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
                raise AuditReplayError("audit event replay detected")
            event_hash = hashlib.sha256(_canonical({"previous_hash": previous, "event": safe}).encode()).hexdigest()
            self.db.execute("INSERT INTO audit_events(event_id,previous_hash,event_json,event_hash,recorded_at) VALUES (?,?,?,?,?)", (event_id, previous, _canonical(safe), event_hash, safe["recorded_at"]))
            if in_transaction is not None:
                in_transaction(self.db)
            self.db.commit()
        except BaseException:
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


__all__ = ["AuditAppender", "AuditChainStore", "AuditReplayError", "GENESIS", "redact_event", "verify_rows"]

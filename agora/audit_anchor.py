"""Local sidecar anchor for the audit hash chain (spec: docs/AUDIT_ANCHOR_SPEC.md).

The anchor history is a separate append-only JSONL file. It detects truncation
and rollback of the chain when the anchor survives. It is NOT protection against
an attacker who can rewrite both files: trust_level reports "local_sidecar".
No network, no external write-back.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agora.audit_chain import GENESIS, AuditChainStore, _canonical
from agora.validation.audit_log import _exclusive_lock

FORMAT_VERSION = 1
TRUST_LEVEL = "local_sidecar"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class AnchorError(ValueError):
    """Anchor history is missing, malformed, or a write was refused."""


class AnchorWriteError(AnchorError):
    """The chain event was appended but its anchor could not be written."""


class AnchorRequiredError(PermissionError):
    """A protected append was refused because the chain is not cleanly anchored."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record_hash(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(dict(body)).encode()).hexdigest()


class AnchorStore:
    """Append-only anchor history at an explicit path (never inside the chain DB)."""

    def __init__(self, path: str | Path, chain_id: str):
        if not isinstance(chain_id, str) or not chain_id.strip():
            raise AnchorError("chain_id is required")
        self.path = Path(path)
        self.chain_id = chain_id

    def read(self) -> list[dict[str, Any]]:
        """Return validated history; raise AnchorError when absent or invalid."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise AnchorError("anchor history is missing") from None
        except OSError as exc:
            raise AnchorError("anchor history is unreadable") from exc
        records: list[dict[str, Any]] = []
        previous = GENESIS
        last_seq = -1
        lines = raw.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            raise AnchorError("anchor history is empty")
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise AnchorError("anchor history is malformed") from None
            if not isinstance(record, dict):
                raise AnchorError("anchor history is malformed")
            body = {k: v for k, v in record.items() if k != "record_hash"}
            seq, head = record.get("sequence"), record.get("head_hash")
            if (type(seq) is not int or seq < 0 or not isinstance(head, str) or not _HASH.match(head)
                    or record.get("format_version") != FORMAT_VERSION
                    or not isinstance(record.get("timestamp"), str)):
                raise AnchorError("anchor record has invalid fields")
            try:
                datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                raise AnchorError("anchor record timestamp is invalid") from None
            if record.get("chain_id") != self.chain_id:
                raise AnchorError("anchor record is for a different chain")
            if record.get("previous_record_hash") != previous or record.get("record_hash") != _record_hash(body):
                raise AnchorError("anchor history linkage is broken")
            if seq <= last_seq:
                raise AnchorError("anchor sequence must increase")
            last_seq, previous = seq, record["record_hash"]
            records.append(record)
        return records

    def latest(self) -> dict[str, Any]:
        return self.read()[-1]

    def _append(self, sequence: int, head_hash: str, extra: Mapping[str, Any] | None = None,
                *, require_history: bool = True) -> dict[str, Any]:
        if require_history:
            history = self.read()
            if sequence <= history[-1]["sequence"]:
                raise AnchorError("anchor sequence must increase")
            previous = history[-1]["record_hash"]
        else:
            if self.path.exists():
                raise AnchorError("anchor history already exists; refusing to bootstrap")
            previous = GENESIS
        body: dict[str, Any] = {
            "sequence": sequence, "head_hash": head_hash, "timestamp": _now(),
            "chain_id": self.chain_id, "format_version": FORMAT_VERSION,
            "previous_record_hash": previous, **dict(extra or {}),
        }
        record = {**body, "record_hash": _record_hash(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)  # owner-only on POSIX
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def lock(self):
        """Cross-process exclusive lock on a sidecar lock file next to the anchor history."""
        return _exclusive_lock(self.path.with_name(self.path.name + ".lock"))

    def advance(self, sequence: int, head_hash: str) -> dict[str, Any]:
        return self._append(sequence, head_hash)


def _head(chain: AuditChainStore) -> tuple[int, str]:
    verdict = chain.verify()
    if not verdict["valid"]:
        raise AnchorError("audit chain failed integrity verification")
    row = chain.db.execute("SELECT seq, event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    return (row[0], row[1]) if row else (0, GENESIS)


def bootstrap_anchor(chain: AuditChainStore, anchors: AnchorStore, *, performed_by: str) -> dict[str, Any]:
    """Explicit maintenance step: verify the whole chain, then record its head."""
    if not isinstance(performed_by, str) or not performed_by.strip():
        raise AnchorError("bootstrap requires performed_by")
    sequence, head = _head(chain)  # raises on an invalid chain, before anything is written
    return anchors._append(sequence, head, {"kind": "bootstrap", "performed_by": performed_by},
                           require_history=False)


def verify_anchored(chain: AuditChainStore, anchors: AnchorStore) -> dict[str, Any]:
    """Read-only comparison of chain and anchor; never repairs either store."""
    def result(status: str, ok: bool = False, **extra: Any) -> dict[str, Any]:
        return {"valid": ok, "status": status, "trust_level": TRUST_LEVEL, **extra}

    if not chain.verify()["valid"]:
        return result("chain_integrity_failure")
    try:
        anchor = anchors.latest()
    except AnchorError as exc:
        return result("anchor_invalid", reason=str(exc))
    head_seq, head_hash = _head(chain)
    if head_seq < anchor["sequence"]:
        return result("truncation_detected", anchor_sequence=anchor["sequence"], chain_sequence=head_seq)
    if anchor["sequence"] == 0:
        at_anchor = GENESIS
    else:
        row = chain.db.execute("SELECT event_hash FROM audit_events WHERE seq=?", (anchor["sequence"],)).fetchone()
        at_anchor = row[0] if row else None
    if at_anchor != anchor["head_hash"]:
        return result("anchor_mismatch", anchor_sequence=anchor["sequence"])
    if head_seq > anchor["sequence"]:
        return result("unanchored_tail", anchor_sequence=anchor["sequence"], chain_sequence=head_seq)
    return result("anchored_verified", True, sequence=head_seq, head_hash=head_hash)


class _ReadOnlyChain:
    """Minimal read-only chain view over a mode=ro SQLite connection."""

    def __init__(self, db: Any):
        self.db = db

    def verify(self) -> dict[str, Any]:
        from .audit_chain import verify_rows
        rows = self.db.execute(
            "SELECT seq,event_id,previous_hash,event_json,event_hash FROM audit_events ORDER BY seq").fetchall()
        previous, broken = verify_rows(rows)
        if broken:
            return {"valid": False, "first_broken_sequence": broken}
        return {"valid": True, "entries": len(rows), "last_hash": previous}


def verify_anchored_readonly(audit_db: str | Path, anchor_path: str | Path, chain_id: str) -> dict[str, Any]:
    """verify_anchored() over a read-only connection: no bootstrap, no writes, no repair.

    Open/read failures return status ``store_unreadable`` (never raises for those).
    """
    import sqlite3
    path = Path(audit_db)
    if not path.is_file():
        return {"valid": False, "status": "store_unreadable", "trust_level": TRUST_LEVEL}
    try:
        db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return {"valid": False, "status": "store_unreadable", "trust_level": TRUST_LEVEL}
    try:
        try:
            anchors = AnchorStore(anchor_path, chain_id)
        except AnchorError as exc:
            return {"valid": False, "status": "anchor_invalid", "trust_level": TRUST_LEVEL, "reason": str(exc)}
        try:
            return verify_anchored(_ReadOnlyChain(db), anchors)  # type: ignore[arg-type]
        except sqlite3.Error:
            return {"valid": False, "status": "store_unreadable", "trust_level": TRUST_LEVEL}
    finally:
        db.close()


class AnchoredAuditChain:
    """Append wrapper: chain append, then a durable anchor, then success."""

    def __init__(self, chain: AuditChainStore, anchors: AnchorStore):
        self.chain, self.anchors = chain, anchors

    def append(self, event: Mapping[str, Any]) -> dict[str, Any]:
        with self.anchors.lock():  # serialise verify -> append -> anchor across processes
            state = verify_anchored(self.chain, self.anchors)
            if not state["valid"]:
                raise AnchorRequiredError(f"audit chain is not cleanly anchored: {state['status']}")
            appended = self.chain.append(event)
            sequence, head = _head(self.chain)
            try:
                self.anchors.advance(sequence, head)
            except Exception as exc:
                raise AnchorWriteError("event was appended but its anchor could not be written") from exc
            return appended

    def close(self) -> None:
        self.chain.close()

    def verify(self) -> dict[str, Any]:
        return verify_anchored(self.chain, self.anchors)


def require_anchored(audit: Any) -> "AnchoredAuditChain":
    """Fail closed unless ``audit`` is an anchored writer (protected-mode gate)."""
    if not isinstance(audit, AnchoredAuditChain):
        raise AnchorRequiredError("protected operation requires an anchored audit writer")
    return audit


@contextmanager
def open_anchored_audit(chain_path: str | Path, anchor_path: str | Path, chain_id: str):
    """Open an anchored writer from explicit paths; always closes the chain.

    Never bootstraps: a missing or invalid anchor, or a chain that is not cleanly
    anchored at open time, raises AnchorRequiredError (fail closed).
    """
    chain_path, anchor_path = Path(chain_path), Path(anchor_path)
    if chain_path.resolve() == anchor_path.resolve():
        raise AnchorError("anchor must be a separate file from the audit chain")
    anchors = AnchorStore(anchor_path, chain_id)
    chain = AuditChainStore(chain_path)
    try:
        writer = AnchoredAuditChain(chain, anchors)
        state = writer.verify()
        if not state["valid"]:
            raise AnchorRequiredError(f"audit chain is not cleanly anchored: {state['status']}")
        yield writer
    finally:
        chain.close()


__all__ = ["AnchorError", "AnchorRequiredError", "AnchorStore", "AnchorWriteError", "AnchoredAuditChain",
           "bootstrap_anchor", "open_anchored_audit", "require_anchored", "verify_anchored"]

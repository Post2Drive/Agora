"""Cross-process serialised, hash-chained JSONL audit log.

The chain is tamper-evident relative to its retained contents, not immutable:
operators must protect and independently anchor backups for stronger guarantees.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from agora.pathsafe import require_safe_path

GENESIS = "0" * 64
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_RESERVED_EVENT_FIELDS = {"previous_hash", "entry_hash"}


def _canonical(value: Any) -> bytes:
    """Stable strict JSON representation; reject NaN and non-JSON values."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise TypeError("Audit event must be a JSON object")
    if any(key in event for key in _RESERVED_EVENT_FIELDS):
        raise ValueError("Audit event cannot set reserved hash fields")
    event_type = event.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("Audit event requires a non-empty event_type")
    row = dict(event)
    row.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
    if not _valid_timestamp(row["recorded_at"]):
        raise ValueError("Audit event recorded_at must be an ISO-8601 timestamp")
    # Validate the complete event before acquiring the lock or touching the log.
    _canonical(row)
    return row


@contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Lock a stable sidecar file across processes on Windows and POSIX."""
    require_safe_path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            # Lock one byte at offset 0 without ever writing to the file: Windows
            # byte-range locks are mandatory, so a racing "initialise" write by a
            # second process hit the locked byte and raised PermissionError.
            # Locking past EOF is permitted. LK_LOCK gives up after ~10 s, so retry.
            handle.seek(0)
            deadline = time.monotonic() + 60.0
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _verify_unlocked(path: Path) -> dict[str, Any]:
    previous = GENESIS
    count = 0
    if not path.exists():
        return {"valid": True, "entries": 0, "last_hash": GENESIS}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"valid": False, "line": 0, "reason": f"cannot read audit log: {exc}"}
    if not raw:
        return {"valid": True, "entries": 0, "last_hash": GENESIS}
    if not raw.endswith(b"\n"):
        return {"valid": False, "line": raw.count(b"\n") + 1,
                "reason": "incomplete final JSONL record (missing newline)"}
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"valid": False, "line": raw[:exc.start].count(b"\n") + 1,
                "reason": "audit log is not valid UTF-8"}

    for line_no, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            return {"valid": False, "line": line_no, "reason": "blank JSONL record"}
        try:
            row = json.loads(
                line, object_pairs_hook=_unique_object,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON constant {value}")),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return {"valid": False, "line": line_no, "reason": f"invalid JSON: {exc}"}
        if not isinstance(row, dict):
            return {"valid": False, "line": line_no,
                    "reason": "audit record must be a JSON object"}
        if not isinstance(row.get("event_type"), str) or not row["event_type"].strip():
            return {"valid": False, "line": line_no, "reason": "missing or invalid event_type"}
        if not _valid_timestamp(row.get("recorded_at")):
            return {"valid": False, "line": line_no, "reason": "missing or invalid recorded_at"}
        stored_hash = row.get("entry_hash")
        previous_hash = row.get("previous_hash")
        if not isinstance(previous_hash, str) or not _HASH_RE.fullmatch(previous_hash):
            return {"valid": False, "line": line_no, "reason": "missing or invalid previous_hash"}
        if not isinstance(stored_hash, str) or not _HASH_RE.fullmatch(stored_hash):
            return {"valid": False, "line": line_no, "reason": "missing or invalid entry_hash"}
        if previous_hash != previous:
            return {"valid": False, "line": line_no, "reason": "previous hash mismatch"}
        unsigned = dict(row)
        unsigned.pop("entry_hash")
        try:
            actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
        except (TypeError, ValueError) as exc:
            return {"valid": False, "line": line_no, "reason": f"invalid record values: {exc}"}
        if stored_hash != actual:
            return {"valid": False, "line": line_no, "reason": "entry hash mismatch"}
        previous = stored_hash
        count += 1
    return {"valid": True, "entries": count, "last_hash": previous}


def verify(path: str | Path) -> dict[str, Any]:
    """Verify the complete chain under the same lock used by appenders."""
    audit_path = require_safe_path(path)
    with _exclusive_lock(audit_path.with_name(audit_path.name + ".lock")):
        return _verify_unlocked(audit_path)


def append(path: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Verify and append one event as a single cross-process critical section."""
    audit_path = require_safe_path(path)
    row = _validate_event(event)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = audit_path.with_name(audit_path.name + ".lock")
    with _exclusive_lock(lock_path):
        state = _verify_unlocked(audit_path)
        if not state["valid"]:
            raise ValueError(
                f"Audit log integrity check failed at line {state.get('line')}: "
                f"{state.get('reason')}"
            )
        row["previous_hash"] = state["last_hash"]
        row["entry_hash"] = hashlib.sha256(_canonical(row)).hexdigest()
        encoded = _canonical(row) + b"\n"
        # O_APPEND prevents offset races; the sidecar lock serialises verification
        # and append as one operation. fsync asks the OS to flush file data/metadata.
        descriptor = os.open(audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write while appending audit record")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return row

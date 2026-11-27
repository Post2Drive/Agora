# Source provenance registry. Stores metadata and hashes, not source contents.
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..jsonl_journal import append_line, reader_lock, writer_lock

ROLES = {"context", "scenario_input", "calibration", "validation", "sealed_holdout"}
STABLE_FIELDS = (
    "sha256", "source_url", "publisher", "author", "published_at", "licence",
    "geography", "population", "data_role", "parser_version",
    "extraction_status", "quality_flags", "reviewer",
)

def _read_rows(path):
    path = Path(path)
    rows = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid source registry JSON on line {line_no}") from exc
        digest = row.get("sha256") if isinstance(row, dict) else None
        valid_digest = (isinstance(digest, str) and len(digest) == 64
                        and all(char in "0123456789abcdef" for char in digest.lower()))
        if (not isinstance(row, dict) or not isinstance(row.get("source_id"), str)
                or not row["source_id"].strip() or row.get("data_role") not in ROLES
                or not valid_digest or not isinstance(row.get("quality_flags", []), list)):
            raise ValueError(f"Invalid source registry record on line {line_no}")
        source_id = str(row["source_id"])
        if any(existing.get("source_id") == source_id for existing in rows):
            raise ValueError(f"Duplicate source_id in source registry on line {line_no}: {source_id}")
        rows.append(row)
    return rows

def list_sources(path):
    """Return validated source metadata in append order."""
    with reader_lock(path):
        return _read_rows(path)

def get_source(path, source_id):
    """Return one source record, or None when it is not registered."""
    wanted = str(source_id)
    return next((row for row in list_sources(path) if row["source_id"] == wanted), None)

def register_source(path, *, source_id, content, source_url="", publisher="", author="",
                    acquired_at=None, published_at=None, licence="", geography="", population="",
                    data_role="context", parser_version="", extraction_status="not_assessed",
                    quality_flags=None, reviewer=""):
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id is required")
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if data_role not in ROLES:
        raise ValueError("Invalid data_role")
    if quality_flags is not None and not isinstance(quality_flags, list):
        raise TypeError("quality_flags must be a list")
    digest = hashlib.sha256(content).hexdigest()
    row = {
        "source_id": str(source_id), "sha256": digest, "source_url": source_url,
        "publisher": publisher, "author": author,
        "acquired_at": acquired_at or datetime.now(timezone.utc).isoformat(),
        "published_at": published_at, "licence": licence, "geography": geography,
        "population": population, "data_role": data_role, "parser_version": parser_version,
        "extraction_status": extraction_status, "quality_flags": quality_flags or [],
        "reviewer": reviewer,
    }
    p = Path(path)
    with writer_lock(p):
        rows = _read_rows(p)
        existing = next((item for item in rows if item.get("source_id") == str(source_id)), None)
        if existing is not None:
            if all(existing.get(key) == row.get(key) for key in STABLE_FIELDS):
                return existing
            raise ValueError(f"Conflicting source_id already registered: {source_id}")
        append_line(p, json.dumps(row, sort_keys=True))
    return row

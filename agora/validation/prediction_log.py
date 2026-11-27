"""Append-only log of predictions made before an outcome is known.

A prediction is recorded with the time it was made, the model version and a hash of its
inputs. Once an outcome is recorded, the prediction is scored against it. Entries are
never rewritten, so a prediction cannot be changed after the fact through this class. Each
write holds one lock across its check and its append, and a log holding two predictions or two
outcomes for one event is refused. The file is not hash-chained: this does not detect a hand edit.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..jsonl_journal import append_line, reader_lock, writer_lock


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class PredictionLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> list[dict]:
        """Parse the log. The caller holds a reader or writer lock."""
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        seen = set()
        for row in rows:
            key = (row["kind"], row["event_id"])
            if key in seen:
                raise ValueError(f"prediction log has two {key[0]} records for event {key[1]}")
            seen.add(key)
        return rows

    def _append(self, entry: dict) -> None:
        """Append one record. The caller holds the writer lock."""
        append_line(self.path, json.dumps(entry, sort_keys=True, default=str))

    def predict(self, event_id: str, model_version: str, inputs: dict, prediction: Any,
                made_at: datetime | None = None) -> dict:
        made_at = made_at or datetime.now(timezone.utc)
        entry = {"kind": "prediction", "event_id": event_id, "model_version": model_version,
                 "made_at": made_at.isoformat(), "inputs_hash": _hash(inputs),
                 "prediction": prediction}
        with writer_lock(self.path):
            if any(e["kind"] == "prediction" and e["event_id"] == event_id for e in self._read()):
                raise ValueError(f"event {event_id} already has a prediction; predictions are not rewritten")
            self._append(entry)
        return entry

    def outcome(self, event_id: str, outcome: Any, observed_at: datetime | None = None) -> dict:
        with writer_lock(self.path):
            rows = self._read()
            preds = [e for e in rows if e["kind"] == "prediction" and e["event_id"] == event_id]
            if not preds:
                raise ValueError(f"no prediction recorded for {event_id}")
            if any(e["kind"] == "outcome" and e["event_id"] == event_id for e in rows):
                raise ValueError(f"outcome for {event_id} already recorded")
            observed_at = observed_at or datetime.now(timezone.utc)
            if observed_at < datetime.fromisoformat(preds[0]["made_at"]):
                raise ValueError("outcome cannot be dated before the prediction")
            entry = {"kind": "outcome", "event_id": event_id, "observed_at": observed_at.isoformat(),
                     "outcome": outcome}
            self._append(entry)
        return entry

    def scored(self) -> list[dict]:
        """Predictions that have an outcome, paired for scoring."""
        with reader_lock(self.path):
            rows = self._read()
        outcomes = {e["event_id"]: e["outcome"] for e in rows if e["kind"] == "outcome"}
        return [{"event_id": e["event_id"], "model_version": e["model_version"],
                 "prediction": e["prediction"], "outcome": outcomes[e["event_id"]]}
                for e in rows if e["kind"] == "prediction" and e["event_id"] in outcomes]

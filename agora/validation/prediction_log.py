"""Append-only log of predictions made before an outcome is known.

A prediction is recorded with the time it was made, the model version and a hash of its
inputs. Once an outcome is recorded, the prediction is scored against it. Entries are
never rewritten, so a prediction cannot be changed after the fact.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


class PredictionLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")

    def predict(self, event_id: str, model_version: str, inputs: dict, prediction: Any,
                made_at: datetime | None = None) -> dict:
        if any(e["kind"] == "prediction" and e["event_id"] == event_id for e in self._read()):
            raise ValueError(f"event {event_id} already has a prediction; predictions are not rewritten")
        made_at = made_at or datetime.now(timezone.utc)
        entry = {"kind": "prediction", "event_id": event_id, "model_version": model_version,
                 "made_at": made_at.isoformat(), "inputs_hash": _hash(inputs),
                 "prediction": prediction}
        self._append(entry)
        return entry

    def outcome(self, event_id: str, outcome: Any, observed_at: datetime | None = None) -> dict:
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
        rows = self._read()
        outcomes = {e["event_id"]: e["outcome"] for e in rows if e["kind"] == "outcome"}
        return [{"event_id": e["event_id"], "model_version": e["model_version"],
                 "prediction": e["prediction"], "outcome": outcomes[e["event_id"]]}
                for e in rows if e["kind"] == "prediction" and e["event_id"] in outcomes]

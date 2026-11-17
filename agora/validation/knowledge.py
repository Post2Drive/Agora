"""Knowledge store: what was learned from past events, and how it transfers.

Each record keeps a past event's domain, date, features, outcome and any parameters fitted
from it. A new event retrieves the most similar past events within the same domain, and
the store returns their fitted parameters, weighted by similarity. Similarity here is a
simple scaled distance over numeric features; it is a starting point, not a learned metric.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Event:
    event_id: str
    domain: str
    when: str
    features: dict
    outcome: float
    params: dict = field(default_factory=dict)


class KnowledgeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _all(self) -> list[Event]:
        if not self.path.exists():
            return []
        return [Event(**json.loads(l)) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def add(self, event: Event) -> None:
        if any(e.event_id == event.event_id for e in self._all()):
            raise ValueError(f"{event.event_id} is already stored")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), sort_keys=True) + "\n")

    def similar(self, domain: str, features: dict, k: int = 3, before: str | None = None) -> list[tuple[Event, float]]:
        """The k most similar past events in the same domain, with similarity in (0, 1].
        Only events dated before `before` are used, so a test event cannot see its own future."""
        cands = [e for e in self._all() if e.domain == domain and (before is None or e.when < before)]
        keys = sorted(set(features) & {k2 for e in cands for k2 in e.features})
        scored = []
        for e in cands:
            shared = [key for key in keys if key in e.features]
            if not shared:
                continue
            d = math.sqrt(sum((float(features[key]) - float(e.features[key])) ** 2 for key in shared) / len(shared))
            scored.append((e, 1.0 / (1.0 + d)))
        scored.sort(key=lambda t: -t[1])
        return scored[:k]

    def transferred_params(self, domain: str, features: dict, before: str | None = None, k: int = 3) -> dict:
        """Similarity-weighted average of the fitted parameters of the nearest past events."""
        near = self.similar(domain, features, k=k, before=before)
        total, out = 0.0, {}
        for e, w in near:
            total += w
            for key, val in e.params.items():
                if isinstance(val, (int, float)):
                    out[key] = out.get(key, 0.0) + w * float(val)
        return {key: round(v / total, 6) for key, v in out.items()} if total else {}

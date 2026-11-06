"""Mock backend: no model needed. Produces plausible, deterministic structured output
so the whole pipeline can be tested (and demoed) on any machine in seconds.

Real models ignore `meta`; the mock reads it to know what kind of answer is expected.
"""
from __future__ import annotations

import hashlib
import json
import random

from .base import LLMBackend

_POS = ["Honestly this looks good", "Tried it, no complaints", "Worth a go",
        "I'm in, sounds useful", "Good to see something like this here"]
_NEG = ["Not convinced", "What's the catch?", "Seems like a sales trick",
        "I'd rather wait and see", "Too many of these offers lately"]
_NEU = ["Anyone tried this?", "Need more details first", "Hmm, interesting",
        "Will check the website", "What do others think?"]


class MockBackend(LLMBackend):
    name = "mock"

    def _rng(self, messages, seed) -> random.Random:
        h = hashlib.sha256((json.dumps(messages, sort_keys=True) + str(seed)).encode()).hexdigest()
        return random.Random(int(h[:16], 16))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta) -> str:
        rng = self._rng(messages, seed)
        task = meta.get("task", "text")
        if task == "decide":
            return json.dumps(self._decide(meta, rng))
        if task == "poll":
            yes = float(meta.get("stance", 0.0)) + rng.gauss(0, 0.3) > meta.get("bar", 0.0)
            return json.dumps({"vote": "yes" if yes else "no", "reason": "mock vote"})
        if task == "json":
            return json.dumps(meta.get("default", {}))
        return meta.get("default_text") or "Mock response."

    def _decide(self, m: dict, rng: random.Random) -> dict:
        stance = float(m.get("stance", 0.0))
        feed = m.get("feed", [])
        topic = m.get("topic", "this")
        if feed:
            avg = sum(f.get("stance", 0.0) for f in feed) / len(feed)
            stance += 0.25 * (avg - stance)
        stance = max(-1.0, min(1.0, stance + rng.gauss(0, 0.08)))

        acts: list[dict] = []
        allowed = set(m.get("actions", []))
        for f in feed[:6]:
            agree = 1 - abs(f.get("stance", 0.0) - stance) / 2
            if "like" in allowed and rng.random() < 0.35 * agree:
                acts.append({"type": "like", "target": f["id"]})
            elif "reply" in allowed and rng.random() < 0.12 and abs(f.get("stance", 0) - stance) > 0.6:
                acts.append({"type": "reply", "target": f["id"], "text": self._say(stance, topic, rng)})
            if len(acts) >= 2:
                break
        where = m.get("where", [])
        if "post" in allowed and where and rng.random() < 0.3:
            acts.append({"type": "post", "where": rng.choice(where),
                         "text": self._say(stance, topic, rng)})
        for c in m.get("conversions", []):
            if stance > c.get("mock_threshold", 0.3) and rng.random() < 0.4:
                acts.append({"type": "convert", "name": c["name"]})
        return {"thoughts": "mock reasoning", "stance": round(stance, 3), "actions": acts[:3]}

    @staticmethod
    def _say(stance: float, topic: str, rng: random.Random) -> str:
        pool = _POS if stance > 0.25 else _NEG if stance < -0.25 else _NEU
        return f"{rng.choice(pool)} - {topic}."

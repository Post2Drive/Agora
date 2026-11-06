"""Fact retrieval: gives each LLM voice the few graph facts most relevant to what is on
its screen right now (BM25 over relation facts and entity descriptions). Pure Python,
no embeddings needed, so it is fast on any machine."""
from __future__ import annotations

import math
import re
from collections import Counter

_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("""a an the and or of to in on at for by with from is are was were be been it its this
that these those as not no but if then than so such can will may per each every one any all into
about after before your you we our they their he she his her i me my""".split())


def tokens(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if t not in _STOP and len(t) > 1]


class FactIndex:
    def __init__(self, facts: list[str], k1: float = 1.4, b: float = 0.75):
        self.facts = list(dict.fromkeys(f.strip() for f in facts if f and f.strip()))
        self.docs = [Counter(tokens(f)) for f in self.facts]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def __len__(self):
        return len(self.facts)

    def search(self, query: str, k: int = 3, exclude: set[str] | None = None) -> list[str]:
        q = set(tokens(query))
        if not q or not self.facts:
            return []
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in sorted(q):
                f = d.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for _, i in scored:
            if exclude and self.facts[i] in exclude:
                continue
            out.append(self.facts[i])
            if len(out) >= k:
                break
        return out

    @classmethod
    def from_graph(cls, gs) -> "FactIndex":
        facts = [f for (f,) in gs.rows("SELECT fact FROM edges WHERE fact != '' ORDER BY id")]
        facts += [f"{n}: {d}" for n, d in gs.rows(
            "SELECT name, description FROM nodes WHERE description != '' ORDER BY id")]
        return cls(facts)

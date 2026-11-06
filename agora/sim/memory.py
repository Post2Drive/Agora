"""World memory: a running, searchable record of what happened in the simulated world.

Every public post, decision, news item and wave of real-world actions becomes an
'episode'. When an LLM voice acts, it recalls the couple of earlier episodes most
related to what is on its screen, the way people remember something a friend
mentioned last week. Private messages never enter world memory.
"""
from __future__ import annotations

import json
from collections import Counter

from ..graph.retrieve import FactIndex
from ..platforms import REGISTRY

MAX_EPISODES = 4000


def _when(start, round_hours: float, r: int) -> str:
    from datetime import timedelta
    t = start + timedelta(hours=r * round_hours)
    part = "morning" if 5 <= t.hour < 12 else "afternoon" if t.hour < 17 else "evening" if t.hour < 22 else "night"
    return f"{t:%a} {part}"


class WorldMemory:
    def __init__(self, sc):
        self.sc = sc
        self.episodes: list[tuple[int, int | None, str]] = []    # (round, post id or None, text)
        self._index: FactIndex | None = None
        self._index_ids: list[int | None] = []
        self._dirty = True

    # ---------------------------------------------------------------- building
    def _post_episode(self, world, p) -> str | None:
        if p.kind not in ("post", "reply", "quote") or not p.text or p.space.startswith("@dm:"):
            return None
        a = world.agents[p.author]
        who = f"{a.name} ({'official' if a.kind == 'account' else a.segment.replace('_', ' ')})"
        where = REGISTRY[p.platform].label + (f" group '{p.space}'" if p.space else "")
        verb = {"post": "posted", "reply": "replied", "quote": "quoted someone"}[p.kind]
        return f"{_when(self.sc.start, self.sc.round_hours, p.round)}: {who} {verb} on {where}: \"{p.text[:200]}\""

    def add_round(self, world, r: int, posts, conversions, events) -> None:
        for p in posts:
            ep = self._post_episode(world, p)
            if ep:
                self.episodes.append((r, p.id, ep))
        when = _when(self.sc.start, self.sc.round_hours, r)
        for kind, d in events:
            if kind == "news":
                self.episodes.append((r, None, f"{when}: news: {d['text']}"))
            elif kind == "poll":
                self.episodes.append((r, None, f"{when}: decision '{d['name'].replace('_', ' ')}' was "
                                              f"{'approved' if d['passed'] else 'rejected'} ({d['yes']}-{d['no']})"))
        counts = Counter(n for _, n in conversions)
        for name, n in counts.items():
            c = next((c for c in self.sc.conversions if c.name == name), None)
            label = c.label if c else name.replace("_", " ")
            self.episodes.append((r, None, f"{when}: {n} {'person' if n == 1 else 'people'} chose to {label}"))
        if len(self.episodes) > MAX_EPISODES:
            del self.episodes[: len(self.episodes) - MAX_EPISODES]
        self._dirty = True

    @classmethod
    def load(cls, sc, world, store) -> "WorldMemory":
        m = cls(sc)
        by_round_posts: dict[int, list] = {}
        for p in world.posts:
            by_round_posts.setdefault(p.round, []).append(p)
        events: dict[int, list] = {}
        for r, kind, detail in store.rows("SELECT round, kind, detail FROM event_log ORDER BY rowid"):
            events.setdefault(r, []).append((kind, json.loads(detail)))
        convs: dict[int, list] = {}
        for r, a, n in store.rows("SELECT round, agent, name FROM conversions ORDER BY rowid"):
            convs.setdefault(r, []).append((a, n))
        for r in sorted(set(by_round_posts) | set(events) | set(convs)):
            m.add_round(world, r, by_round_posts.get(r, []), convs.get(r, []), events.get(r, []))
        return m

    # ---------------------------------------------------------------- recall
    def recall(self, query: str, before_round: int, exclude: set[int], k: int = 2) -> list[str]:
        if self._dirty:
            self._index = FactIndex([f"{i}\x00{t}" for i, (_, _, t) in enumerate(self.episodes)])
            self._dirty = False
        if not self._index or not len(self._index):
            return []
        out = []
        for hit in self._index.search(query, k=k * 6):
            i = int(hit.split("\x00", 1)[0])
            r, pid, text = self.episodes[i]
            if r >= before_round or (pid is not None and pid in exclude):
                continue
            out.append(text)
            if len(out) >= k:
                break
        return out

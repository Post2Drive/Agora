"""Simulated platforms. Each one decides what an agent sees (its feed) and which
actions make sense there.

  x         - public feed: follows + trending + recommendations; post, reply, like, repost, follow
  reddit    - communities with threads ranked by votes; post thread, comment, upvote, downvote
  whatsapp  - private groups, chronological, unread since last visit; message, reply, forward, react

The feed index is rebuilt once per round, so per-agent feeds stay cheap even with
tens of thousands of crowd agents.
"""
from __future__ import annotations

import math

import numpy as np

from ..world import Agent, Post, World

ACTIONS = {
    "x": ("post", "reply", "like", "repost", "follow"),
    "reddit": ("post", "reply", "upvote", "downvote"),
    "whatsapp": ("post", "reply", "like", "forward"),
}
X_WINDOW_H = 48.0
REDDIT_WINDOW_H = 120.0
X_HALF_LIFE_H = 10.0


class FeedIndex:
    """Per-round snapshot used to build feeds."""

    def __init__(self, world: World, t: float, top_n: int = 60):
        self.world = world
        self.t = t
        posts = world.posts
        # X: recent posts, scored once
        recent = [pid for pid in reversed(world.x_posts) if t - posts[pid].t <= X_WINDOW_H]
        self.x_score: dict[int, float] = {}
        for pid in recent:
            p = posts[pid]
            src = posts[p.root]
            author = world.agents[p.author]
            age = max(0.0, t - p.t)
            self.x_score[pid] = ((1 + math.log1p(max(0, src.engagement)))
                                 * math.exp(-age * math.log(2) / X_HALF_LIFE_H)
                                 * math.sqrt(max(0.05, author.influence)))
        self.x_trending = sorted(self.x_score, key=self.x_score.get, reverse=True)[:top_n]
        # Reddit: hot threads per community, with their best comments
        self.reddit_hot: dict[str, list[int]] = {}
        for (plat, space), pids in world.space_posts.items():
            if plat != "reddit":
                continue
            threads, comments = [], {}
            for pid in pids:
                p = posts[pid]
                if t - p.t > REDDIT_WINDOW_H:
                    continue
                if p.parent is None:
                    threads.append(pid)
                else:
                    comments.setdefault(p.root, []).append(pid)
            hot = sorted(threads, key=lambda q: self._hot(posts[q]), reverse=True)[:top_n]
            items = []
            for th in hot:
                items.append(th)
                best = sorted(comments.get(th, []), key=lambda c: posts[c].ups - posts[c].downs,
                              reverse=True)[:2]
                items.extend(best)
            self.reddit_hot[space] = items

    @staticmethod
    def _hot(p: Post) -> float:
        score = p.ups - p.downs + p.replies
        order = math.log10(max(abs(score), 1))
        sign = 1 if score > 0 else -1 if score < 0 else 0
        return sign * order + p.t / 12.0

    # ---------------------------------------------------------------- feeds
    def feed(self, a: Agent, k: int, rng: np.random.Generator) -> list[int]:
        w = self.world
        chosen: list[int] = []
        per = max(2, k // max(1, len(a.platforms)))
        for plat in a.platforms:
            if plat == "x":
                chosen += self._x_feed(a, per, rng)
            elif plat == "reddit":
                chosen += self._reddit_feed(a, per)
            elif plat == "whatsapp":
                chosen += self._wa_feed(a, per)
        seen, out = set(), []
        for pid in chosen:
            p = w.posts[pid]
            src = p.root if p.kind in ("repost", "forward") else pid
            if src in seen or p.author == a.id or w.posts[src].author == a.id:
                continue
            seen.add(src)          # one copy of a message, however many times it was shared
            out.append(pid)
        return out[:k]

    def _x_feed(self, a: Agent, k: int, rng) -> list[int]:
        w = self.world
        follows = w.following.get(a.id, ())
        cand: dict[int, float] = {}
        for f in follows:
            for pid in reversed(w.author_posts.get(f, [])[-5:]):
                s = self.x_score.get(pid)
                if s is not None:
                    cand[pid] = s * 3.0
        for pid in self.x_trending:
            cand.setdefault(pid, self.x_score[pid] * (0.6 + 0.8 * rng.random()))
        ranked = sorted(cand, key=cand.get, reverse=True)
        out, sources = [], set()
        for pid in ranked:
            p = w.posts[pid]
            src = p.root if p.kind == "repost" else pid
            if src in sources or self._done(a, pid) or self._done(a, src):
                continue
            sources.add(src)
            out.append(pid)
            if len(out) >= k:
                break
        return out

    def _reddit_feed(self, a: Agent, k: int) -> list[int]:
        out = []
        for space in self.world.member_of.get(a.id, {}).get("reddit", []):
            out += [p for p in self.reddit_hot.get(space, []) if not self._done(a, p)][:k]
        return out[:k]

    def _wa_feed(self, a: Agent, k: int) -> list[int]:
        w = self.world
        out = []
        for space in w.member_of.get(a.id, {}).get("whatsapp", []):
            pids = w.space_posts.get(("whatsapp", space), [])
            new = []
            for pid in reversed(pids):
                if w.posts[pid].t <= a.last_seen:
                    break
                new.append(pid)
            out += new[:k]
        out.sort(key=lambda p: w.posts[p].t, reverse=True)
        return out[:k]

    def _done(self, a: Agent, pid: int) -> bool:
        e = self.world.engaged
        return (a.id, pid, "like") in e or (a.id, pid, "upvote") in e or (a.id, pid, "downvote") in e


def where_options(world: World, a: Agent) -> list[str]:
    """Places an agent can post: 'x', 'reddit:<community>', 'whatsapp:<group>'."""
    out = []
    for plat in a.platforms:
        if plat == "x":
            out.append("x")
        else:
            out += [f"{plat}:{s}" for s in world.member_of.get(a.id, {}).get(plat, [])]
    return out

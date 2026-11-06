"""Feeds: what each agent sees on each platform this round.

  feed platforms  - posts from people you follow (boosted) + trending, decaying with age
  forum platforms - hot threads in your communities, each with its best comments
  chat platforms  - unread messages in your groups, newest first

The index is rebuilt once per round from a snapshot, so per-agent feeds stay cheap even
with tens of thousands of crowd agents. Platform behaviour comes from `agora.platforms`.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from ...platforms import REGISTRY
from ..timing import feed_cfg
from ..world import Agent, Post, World


def actions_for(platform: str) -> tuple[str, ...]:
    return REGISTRY[platform].actions


class FeedIndex:
    """Per-round snapshot used to build feeds."""

    def __init__(self, world: World, t: float, top_n: int = 60, feeds: dict | None = None):
        self.world = world
        self.t = t
        posts = world.posts
        self.cfg = {plat: feed_cfg(feeds, plat) for plat in REGISTRY if REGISTRY[plat].kind == "feed"}
        self.score: dict[str, dict[int, float]] = {}       # global part: recency + popularity
        self.trending: dict[str, list[int]] = {}
        self.viral: dict[str, set[int]] = {}
        for plat, pids in world.feed_posts.items():
            spec, c = REGISTRY[plat], self.cfg[plat]
            recent = []
            for pid in reversed(pids):
                p = posts[pid]
                age = t - p.t
                if age > spec.window_h:
                    break
                recent.append((pid, age, max(0, posts[p.root].engagement)))
            top = max([e for _, _, e in recent] + [1])
            sc: dict[int, float] = {}
            viral = set()
            for pid, age, eng in recent:
                rec = math.exp(-max(0.0, age) * math.log(2) / spec.half_life_h)
                pop = math.log1p(eng) / math.log1p(top)
                author = world.agents[posts[pid].author]
                sc[pid] = (c["recency"] * rec + c["popularity"] * pop + 0.05) * math.sqrt(max(0.05, author.influence))
                if eng >= c["viral_threshold"]:
                    viral.add(pid)
                    sc[pid] *= 1.5
            self.score[plat] = sc
            self.viral[plat] = viral
            self.trending[plat] = sorted(sc, key=sc.get, reverse=True)[:top_n]
        # forums: hot threads per community, each followed by its best comments
        self.hot: dict[tuple[str, str], list[int]] = {}
        for (plat, space), pids in world.space_posts.items():
            if REGISTRY[plat].kind != "forum":
                continue
            window = REGISTRY[plat].window_h
            threads, comments = [], {}
            for pid in pids:
                p = posts[pid]
                if t - p.t > window:
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
            self.hot[(plat, space)] = items

    @staticmethod
    def _hot(p: Post) -> float:
        score = p.ups - p.downs + p.replies
        order = math.log10(max(abs(score), 1))
        sign = 1 if score > 0 else -1 if score < 0 else 0
        return sign * order + p.t / 12.0

    # ---------------------------------------------------------------- feeds
    def trends(self, platform: str, k: int = 5) -> list[str]:
        """Hashtags and words most used on a feed platform recently (shown as 'trending')."""
        cache = getattr(self, "_trends", None)
        if cache is None:
            cache = self._trends = {}
        if platform not in cache:
            c: Counter[str] = Counter()
            for pid in self.score.get(platform, {}):
                txt = self.world.posts[pid].text.lower()
                c.update(set(re.findall(r"#[a-z0-9_]{3,30}", txt)))
                c.update(w for w in set(re.findall(r"[a-z]{5,}", txt)) if w not in _COMMON)
            cache[platform] = [t for t, n in c.most_common(k) if n >= 2]
        return cache[platform]

    def feed(self, a: Agent, k: int, rng: np.random.Generator) -> list[int]:
        w = self.world
        # things addressed to you come first: replies, @mentions, private messages
        chosen: list[int] = w.inbox(a.id, a.last_seen, limit=max(2, k // 2))
        per = max(2, -(-k // max(1, len(a.platforms))))
        for plat in a.platforms:
            kind = REGISTRY[plat].kind
            if kind == "feed":
                chosen += self._feed(plat, a, per, rng)
            elif kind == "forum":
                chosen += self._forum(plat, a, per)
            else:
                chosen += self._chat(plat, a, per)
        seen, out = set(), []
        muted = w.muted.get(a.id, ())
        for pid in chosen:
            p = w.posts[pid]
            src = p.root if p.kind in ("repost", "forward") else pid
            if (src in seen or p.author == a.id or w.posts[src].author == a.id
                    or p.author in muted or w.posts[src].author in muted):
                continue
            seen.add(src)          # one copy of a message, however many times it was shared
            out.append(pid)
        return out[:k]

    def _feed(self, plat: str, a: Agent, k: int, rng) -> list[int]:
        w = self.world
        score = self.score.get(plat, {})
        if not score:
            return []
        c = self.cfg[plat]
        follows = w.following[plat].get(a.id, ())
        posts = w.posts

        def personal(pid: int, followed: bool) -> float:
            # relevance: people you follow, and (echo chamber) views close to yours
            st = posts[posts[pid].root].stance
            agree = 1 - abs(st - a.stance) / 2
            rel = 0.6 * followed + 0.4 * agree
            echo = 1 + c["echo_chamber"] * (2 * agree - 1)
            return (score[pid] + c["relevance"] * rel) * max(0.05, echo)

        cand: dict[int, float] = {}
        for f in follows:
            for pid in reversed(w.author_posts.get(f, [])[-6:]):
                if pid in score:
                    cand[pid] = personal(pid, True)
        for pid in self.trending.get(plat, []):
            if pid not in cand:
                cand[pid] = personal(pid, posts[pid].author in follows) * (0.7 + 0.6 * rng.random())
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

    def _forum(self, plat: str, a: Agent, k: int) -> list[int]:
        out = []
        for space in self.world.member_of.get(a.id, {}).get(plat, []):
            out += [p for p in self.hot.get((plat, space), []) if not self._done(a, p)][:k]
        return out[:k]

    def _chat(self, plat: str, a: Agent, k: int) -> list[int]:
        w = self.world
        out = []
        for space in w.member_of.get(a.id, {}).get(plat, []):
            new = []
            for pid in reversed(w.space_posts.get((plat, space), [])):
                if w.posts[pid].t <= a.last_seen:
                    break
                new.append(pid)
            out += new[:k]
        out.sort(key=lambda p: w.posts[p].t, reverse=True)
        return out[:k]

    def _done(self, a: Agent, pid: int) -> bool:
        e = self.world.engaged
        return (a.id, pid, "like") in e or (a.id, pid, "upvote") in e or (a.id, pid, "downvote") in e


_COMMON = set("""about after again being could every first going great really should their there these
think thing things those today where which while would people still never always maybe""".split())


def where_options(world: World, a: Agent) -> list[str]:
    """Places an agent can post: '<feed platform>' or '<platform>:<group or community>'."""
    out = []
    for plat in a.platforms:
        if REGISTRY[plat].kind == "feed":
            out.append(plat)
        else:
            out += [f"{plat}:{s}" for s in world.member_of.get(a.id, {}).get(plat, [])]
    return out

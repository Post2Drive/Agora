"""Opinion dynamics and engagement for crowd agents.

Opinions are numbers from -1 (strongly against) to +1 (strongly for).

Update rule (Friedkin-Johnsen with bounded confidence):
    social  = influence-weighted mean of the posts seen whose stance is within
              `openness` of the agent's own (too-different views are ignored)
    x_new   = s * x0 + (1 - s) * ((1 - mu) * x + mu * social)
where x0 is the agent's starting opinion and s its stubbornness. These parameters are
what Phase 4 calibrates against real data.
"""
from __future__ import annotations

import math

import numpy as np

from ..platforms import REGISTRY
from .world import Agent, Post, World

MU = 0.35                 # how far one round of exposure moves an open-minded agent
P_LIKE = 0.18
P_DOWNVOTE = 0.06
P_SHARE = 0.04
P_FOLLOW = 0.08


def sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def exposure_weight(world: World, p: Post) -> float:
    author = world.agents[p.author]
    src = world.posts[p.root]
    return math.sqrt(max(0.05, author.influence)) * (1 + 0.3 * math.log1p(max(0, src.engagement)))


def update_stance(world: World, a: Agent, feed: list[Post], rng: np.random.Generator,
                  mu: float = MU) -> float:
    num = den = 0.0
    for p in feed:
        if abs(p.stance - a.stance) <= a.openness:
            wgt = exposure_weight(world, p)
            num += wgt * p.stance
            den += wgt
    x = a.stance
    if den > 0:
        social = num / den
        x = a.stubbornness * a.initial_stance + (1 - a.stubbornness) * ((1 - mu) * x + mu * social)
    x += rng.normal(0, 0.015)
    return float(np.clip(x, -1, 1))


def update_prefs(world: World, a: Agent, feed: list[Post], rng: np.random.Generator,
                 mu: float = MU) -> dict:
    """Choice mode: the same rule, applied to each option a post is about."""
    prefs = dict(a.prefs)
    p0 = a.attrs.get("prefs0") or prefs
    by_opt: dict[str, list[tuple[float, float]]] = {}
    for p in feed:
        src = world.posts[p.root] if p.kind in ("repost", "forward") else p
        if src.option in prefs and abs(src.stance - prefs[src.option]) <= a.openness:
            by_opt.setdefault(src.option, []).append((exposure_weight(world, p), src.stance))
    for o in sorted(prefs):
        x = prefs[o]
        if o in by_opt:
            den = sum(w for w, _ in by_opt[o])
            social = sum(w * v for w, v in by_opt[o]) / den
            x = a.stubbornness * p0.get(o, x) + (1 - a.stubbornness) * ((1 - mu) * x + mu * social)
        prefs[o] = float(np.clip(x + rng.normal(0, 0.01), -1, 1))
    return prefs


def crowd_engagement(world: World, a: Agent, feed: list[Post], rng: np.random.Generator
                     ) -> list[dict]:
    """Likes, votes, shares and follows a crowd agent makes. Crowd agents never write
    text; the LLM voices do the talking and the crowd amplifies or ignores it."""
    acts = []
    for p in feed:
        if p.kind in ("repost", "forward"):
            target = world.posts[p.root]
        else:
            target = p
        agree = 1 - abs(target.stance - a.view_of(target.option)) / 2
        strength = 0.5 + abs(target.stance)
        kind = REGISTRY[p.platform].kind
        if kind == "forum":
            if rng.random() < P_LIKE * agree ** 3 * strength:
                acts.append({"type": "upvote", "target": p.id})
            elif rng.random() < P_DOWNVOTE * (1 - agree) ** 2 * strength:
                acts.append({"type": "downvote", "target": p.id})
            continue
        if rng.random() < P_LIKE * agree ** 3 * strength:
            acts.append({"type": "like", "target": p.id})
            if (kind == "feed" and target.author not in world.following[p.platform][a.id]
                    and rng.random() < P_FOLLOW):
                acts.append({"type": "follow", "target": f"p{target.id}", "platform": p.platform})
        if abs(target.stance) > 0.4 and rng.random() < P_SHARE * agree ** 4 * abs(target.stance):
            acts.append({"type": "repost" if kind == "feed" else "forward", "target": p.id})
    return acts

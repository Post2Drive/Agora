"""Who may contact whom, and whom a crowd person chooses to talk to.

Pure functions over the society store and the world. They draw from a generator the caller
derives from (seed, round, agent), so the same run always makes the same choices.
"""
from __future__ import annotations

import math

DEFAULT_WEIGHTS = {"trust": 1.0, "familiarity": 1.0, "similarity": 1.0, "influence": 0.5}
TEMPERATURE = 0.35


def acquainted(world, soc, a, b) -> bool:
    """Already connected: a relationship edge either way, a shared group chat or a shared app space."""
    if soc.relationship(a.id, b.id) or soc.relationship(b.id, a.id) or soc.share_group(a.id, b.id):
        return True
    mine = {s for spaces in world.member_of.get(a.id, {}).values() for s in spaces}
    theirs = {s for spaces in world.member_of.get(b.id, {}).values() for s in spaces}
    return bool(mine & theirs)


def may_contact(mode: str, world, soc, a, b) -> bool:
    """The permission matrix. `open`: anyone. `relationship`: only people already connected.
    `group_only`: only people who share a group chat."""
    if a.id == b.id:
        return False
    if mode == "open":
        return True
    if mode == "group_only":
        return soc.share_group(a.id, b.id)
    if mode == "relationship":
        return acquainted(world, soc, a, b)
    raise ValueError(f"unknown contact mode {mode!r}")


def components(soc, a, b, top_influence: float) -> dict[str, float]:
    """The parts of the score for a talking to b, each in [0, 1]."""
    rel = soc.relationship(a.id, b.id) or {"trust": 0.5, "familiarity": 0.0}
    similarity = 0.5 * (a.segment == b.segment) + 0.5 * (1 - min(1.0, abs(a.stance - b.stance) / 2))
    influence = min(1.0, b.influence / top_influence) if top_influence > 0 else 0.0
    return {"trust": float(rel["trust"]), "familiarity": float(rel["familiarity"]),
            "similarity": float(similarity), "influence": float(influence)}


def score(parts: dict[str, float], weights: dict[str, float]) -> float:
    w = {**DEFAULT_WEIGHTS, **weights}
    return sum(w[k] * parts[k] for k in DEFAULT_WEIGHTS)


def choose(world, soc, a, mode: str, pool: int, weights: dict[str, float], rng,
           top_influence: float, taken: set[int]) -> tuple | None:
    """Pick one permitted person for `a` to talk to, or None. Returns (agent, score parts, score).

    Candidates are taken in id order, `pool` of them are sampled without replacement, and one is
    drawn with probability proportional to exp(score / TEMPERATURE)."""
    cands = [b for b in world.agents if b.id not in taken and may_contact(mode, world, soc, a, b)]
    if not cands:
        return None
    if len(cands) > pool:
        idx = sorted(int(i) for i in rng.choice(len(cands), size=pool, replace=False))
        cands = [cands[i] for i in idx]
    rows = []
    for b in cands:
        parts = components(soc, a, b, top_influence)
        rows.append((b, parts, score(parts, weights)))
    best = max(r[2] for r in rows)
    probs = [math.exp((r[2] - best) / TEMPERATURE) for r in rows]
    total = sum(probs)
    draw = float(rng.random()) * total
    acc = 0.0
    for r, p in zip(rows, probs):
        acc += p
        if draw <= acc:
            return r
    return rows[-1]

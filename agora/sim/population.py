"""Build the initial population, follow network and group memberships from a scenario."""
from __future__ import annotations

import re

import numpy as np

from ..platforms import REGISTRY
from ..scenario import Scenario
from .world import Agent, World

TRAITS = [
    "skeptical, has been burned by offers before",
    "curious early adopter who likes trying new things",
    "price-conscious and careful with money",
    "busy and practical, values convenience",
    "sociable, goes along with what friends say",
    "loyal to familiar brands and habits",
    "detail-oriented, reads the fine print",
    "outspoken, likes to share opinions",
    "private, rarely posts but reads everything",
    "health-conscious and research-minded",
]

DEFAULT_NAMES = [
    "Aarav", "Priya", "Rahul", "Sneha", "Vikram", "Ananya", "Arjun", "Divya", "Karthik",
    "Lakshmi", "Ravi", "Meera", "Suresh", "Kavya", "Naveen", "Swathi", "Harsha", "Pooja",
    "Srinivas", "Deepika", "Manoj", "Bhavana", "Kiran", "Sravani", "Ajay", "Madhavi",
    "Vamsi", "Keerthi", "Rohit", "Anjali", "Sai", "Haritha", "Venkat", "Nithya", "Prakash",
    "Sowjanya", "Teja", "Varsha", "Chaitanya", "Gayathri", "James", "Sarah", "David", "Emma",
]


def _alloc(total: int, weights: list[float]) -> list[int]:
    """Split `total` by weights using largest remainders (always sums to total)."""
    w = np.array(weights, float)
    w = w / w.sum() if w.sum() > 0 else np.full(len(w), 1 / len(w))
    raw = w * total
    out = np.floor(raw).astype(int)
    for i in np.argsort(-(raw - out))[: total - out.sum()]:
        out[i] += 1
    return out.tolist()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:20] or "user"


def build(sc: Scenario) -> tuple[World, list[tuple[int, int]], list[tuple[int, str, str]]]:
    rng = np.random.default_rng([sc.seed, 0xA60A])
    w = World()
    seg_idx = {s.name: i for i, s in enumerate(sc.segments)}

    def new_agent(**kw) -> Agent:
        kw.setdefault("stance", kw["initial_stance"])
        a = Agent(id=len(w.agents), **kw)
        w.add_agent(a)
        return a

    # 1. named accounts first so they get low, stable ids
    for acc in sc.accounts:
        new_agent(handle=acc.id, kind="account", name=acc.name, segment=acc.segment,
                  persona=acc.persona, platforms=list(acc.platforms),
                  initial_stance=float(acc.stance), stubbornness=acc.stubbornness,
                  activity=acc.activity, influence=acc.influence, openness=0.3,
                  attrs={"llm": acc.llm, "spaces": acc.spaces})

    # 2. LLM voices and crowd agents per segment
    llm_counts = _alloc(sc.llm_agents, [s.llm_share if s.llm_share is not None else s.share
                                        for s in sc.segments])
    crowd_counts = _alloc(sc.crowd_agents, [s.share for s in sc.segments])
    used_handles: set[str] = set(w.by_handle)
    for seg, n_llm, n_crowd in zip(sc.segments, llm_counts, crowd_counts):
        names = seg.names or DEFAULT_NAMES
        voices = [v for v in sc.voices if v.get("segment") == seg.name]
        for i in range(n_llm + n_crowd):
            kind = "llm" if i < n_llm else "crowd"
            voice = voices[i] if kind == "llm" and i < len(voices) else None
            name = str(voice["name"]) if voice and voice.get("name") else str(rng.choice(names))
            base = _slug(name)
            handle = f"{base}{rng.integers(10, 9999)}"
            while handle in used_handles:
                handle = f"{base}{rng.integers(10, 99999)}"
            used_handles.add(handle)
            s0 = float(np.clip(rng.normal(seg.stance_mean, seg.stance_sd), -1, 1))
            stub = float(np.clip(rng.normal(seg.stubbornness, 0.1), 0.02, 0.98))
            act = float(np.clip(rng.normal(seg.activity, 0.12), 0.02, 1.0))
            infl = float(seg.influence * rng.lognormal(0, 0.6))
            attrs = {}
            persona = seg.persona
            if kind == "llm":
                age = int(rng.integers(seg.age[0], seg.age[1] + 1))
                occ = str(rng.choice(seg.occupations)) if seg.occupations else ""
                trait = str(rng.choice(TRAITS))
                if voice:
                    age = int(voice.get("age") or age)
                    occ = str(voice.get("occupation") or occ)
                    attrs = {"age": age, "occupation": occ, "voice": True}
                    bits = [f"{name}, {age}"] + ([occ] if occ else [])
                    persona = f"{', '.join(bits)}. {voice['persona']} ({seg.persona})"
                else:
                    attrs = {"age": age, "occupation": occ, "trait": trait}
                    bits = [f"{name}, {age}"] + ([occ] if occ else [])
                    persona = f"{', '.join(bits)}. {seg.persona} Personality: {trait}."
                infl *= 1.5      # voices that write are a bit more visible
            new_agent(handle=handle, kind=kind, name=name, segment=seg.name, persona=persona,
                      platforms=list(seg.platforms), initial_stance=s0, stubbornness=stub,
                      activity=act, influence=infl, openness=seg.openness, attrs=attrs)

    # 3. group / community memberships
    memberships: list[tuple[int, str, str]] = []
    taken: dict[str, set[int]] = {}           # exclusive tag -> agents already placed
    for sp in sc.spaces:
        blocked = taken.setdefault(sp.exclusive, set()) if sp.exclusive else set()
        pool = [a for a in w.agents if a.kind != "account" and sp.platform in a.platforms
                and a.id not in blocked
                and sp.segments.get(a.segment, 0 if sp.segments else 1) > 0]
        if not pool:
            continue
        wts = np.array([sp.segments.get(a.segment, 1.0) if sp.segments else 1.0 for a in pool])
        size = min(sp.size, len(pool))
        pick = rng.choice(len(pool), size=size, replace=False, p=wts / wts.sum())
        for i in sorted(pick):
            w.add_member(pool[i].id, sp.platform, sp.name)
            memberships.append((pool[i].id, sp.platform, sp.name))
            if sp.exclusive:
                blocked.add(pool[i].id)
    for a in w.agents:
        if a.kind != "account":
            continue
        wanted = a.attrs.get("spaces") or []
        for sp in sc.spaces:
            if sp.platform in a.platforms and ("*" in wanted or sp.name in wanted):
                w.add_member(a.id, sp.platform, sp.name)
                memberships.append((a.id, sp.platform, sp.name))

    # 4. follow networks, one per feed platform: homophily + preferential attachment
    follows: list[tuple[str, int, int]] = []
    for plat in [k for k in REGISTRY if REGISTRY[k].kind == "feed"]:
        on = [a for a in w.agents if plat in a.platforms]
        if len(on) < 2:
            continue
        ids = np.array([a.id for a in on])
        infl = np.array([a.influence for a in on])
        segs = np.array([seg_idx.get(a.segment, -1) for a in on])
        by_seg = {s: np.where(segs == s)[0] for s in set(segs.tolist())}
        p_all = infl / infl.sum()
        for k, a in enumerate(on):
            n = max(1, int(rng.poisson(sc.avg_follows)))
            same = by_seg[segs[k]]
            n_same = int(round(n * sc.homophily))
            choices = []
            if len(same) > 1 and n_same:
                ps = infl[same] / infl[same].sum()
                choices += rng.choice(same, size=min(n_same, len(same)), replace=False, p=ps).tolist()
            choices += rng.choice(len(on), size=min(max(0, n - n_same), len(on)), replace=False,
                                  p=p_all).tolist()
            for j in choices:
                dst = int(ids[j])
                if w.add_follow(plat, a.id, dst):
                    follows.append((plat, a.id, dst))
    return w, follows, memberships

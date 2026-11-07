"""Keep drafted populations realistic.

Small models drafting from a brand's own documents tend to make everyone keen: every group
positive, every persona "thrilled". Real audiences are mixed. Most people are indifferent,
a minority are keen, and a vocal minority are sceptical or hostile. This module pulls a
drafted population back to that shape before anything is simulated. The numbers are
default assumptions, not data; calibrate against real observations when you have them.
"""
from __future__ import annotations

import re

import numpy as np

# Default shape of a public reacting to a promoted product, offer or campaign:
# population-average starting view, and the spread inside each group.
PRIOR_MEAN = 0.05
MIN_SD = 0.45
SCEPTIC_SHARE = 0.18          # share given to sceptics when the draft has none
SCEPTIC_MEAN = -0.45
NEGATIVE_FLOOR = -0.2         # at least one group starts at or below this

SCEPTICS = {
    "name": "sceptics",
    "persona": ("Sceptical people who distrust free offers and brand health claims, suspect "
                "a catch (data collection, upselling, side effects), would rather ask their "
                "own doctor, and are quick to question, complain about spam or mock it in groups."),
    "stubbornness": 0.65, "activity": 0.45,
    "occupations": ["accountant", "government employee", "shop owner", "retired officer", "doctor"],
}

_GUSH = re.compile(r"[^.!?]*\b(thrilled|delighted|excited|can't wait|cannot wait|love[sd]? to|"
                   r"eager|eagerly|jump at|overjoyed|would be happy to)\b[^.!?]*[.!?]", re.I)


def balance_segments(segs: list[dict]) -> tuple[list[dict], list[str]]:
    """Shift and widen drafted group opinions so the population is mixed. Returns notes."""
    notes: list[str] = []
    if not segs:
        return segs, notes
    shares = np.array([s["share"] for s in segs], float)
    shares = shares / shares.sum()
    means = np.array([s["stance"]["mean"] for s in segs], float)
    avg = float((shares * means).sum())
    if avg > PRIOR_MEAN + 0.1:
        # keep each group's position relative to the others, move the whole crowd to the prior
        shift = avg - PRIOR_MEAN
        means = np.clip(means - shift, -0.9, 0.9)
        notes.append(f"Starting opinions were all positive (average {avg:+.2f}); moved to a "
                     f"realistic mix (average {PRIOR_MEAN:+.2f}).")
    for s, m in zip(segs, means):
        s["stance"] = {"mean": round(float(m), 2), "sd": max(MIN_SD, float(s["stance"].get("sd", 0.3)))}
    if min(means) > NEGATIVE_FLOOR:
        plats = sorted({p for s in segs for p in s["platforms"]},
                       key=lambda p: -sum(p in s["platforms"] for s in segs))[:3]
        ages = [min(s["age"][0] for s in segs), max(s["age"][1] for s in segs)]
        for s in segs:
            s["share"] = round(s["share"] * (1 - SCEPTIC_SHARE), 4)
        segs.append({**SCEPTICS, "leaning": {}, "share": SCEPTIC_SHARE, "platforms": plats or ["whatsapp"],
                     "age": ages, "stance": {"mean": SCEPTIC_MEAN, "sd": MIN_SD}})
        notes.append(f"No group was sceptical; added 'sceptics' ({SCEPTIC_SHARE:.0%} of people).")
    return segs, notes


def voice_stances(segs: list[dict], counts: list[int], seed: int) -> list[list[float]]:
    """A starting view for each AI voice, drawn from its group, so persona and number agree."""
    rng = np.random.default_rng(seed + 77)
    return [[round(float(np.clip(rng.normal(s["stance"]["mean"], s["stance"]["sd"]), -1, 1)), 2)
             for _ in range(n)] for s, n in zip(segs, counts)]


def tame_persona(text: str, stance: float) -> str:
    """Drop gushing sentences from a persona whose view is not actually keen."""
    if stance >= 0.6:
        return text
    kept = _GUSH.sub("", text).strip()
    return kept if len(kept) >= 12 else text


def rebalance_scenario(d: dict, seed: int = 0) -> list[str]:
    """Apply the realism pass to an existing scenario dict in place (segments and voices)."""
    segs = []
    for s in d.get("segments", []):
        st = s.get("stance", 0.0)
        s["stance"] = st if isinstance(st, dict) else {"mean": float(st), "sd": 0.3}
        s.setdefault("platforms", ["whatsapp"])
        s.setdefault("age", [22, 65])
        segs.append(s)
    segs, notes = balance_segments(segs)
    d["segments"] = segs
    by_seg: dict[str, list[dict]] = {}
    for v in d.get("voices") or []:
        by_seg.setdefault(v.get("segment"), []).append(v)
    known = [s for s in segs if s["name"] in by_seg]
    for s, sts in zip(known, voice_stances(known, [len(by_seg[s["name"]]) for s in known], seed)):
        for v, st in zip(by_seg[s["name"]], sts):
            v["stance"] = st
            v["persona"] = tame_persona(str(v.get("persona", "")), st)
    return notes

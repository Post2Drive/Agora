"""Ranges, probabilities and sensitivity.

Monte Carlo: many fast runs, each with a different random seed AND slightly different
assumptions (every uncertain number is drawn around its value). The spread of outcomes
gives a likely range (10th-90th percentile), the chance of hitting each target, and for
choices the chance each option wins.

Sensitivity: change one assumption at a time (low / high) and see how much the main
outcome moves - the 'tornado' of what matters most.
"""
from __future__ import annotations

import copy
from typing import Callable

import numpy as np

from .fast import Trajectory, simulate


def _seg_mean(seg):
    st = seg.get("stance", 0.0)
    return float(st.get("mean", 0.0)) if isinstance(st, dict) else float(st)


def _set_seg_mean(seg, v):
    st = seg.get("stance", 0.0)
    if isinstance(st, dict):
        st["mean"] = v
    else:
        seg["stance"] = {"mean": v, "sd": 0.3}


def jitter(d: dict, rng: np.random.Generator, scale: float = 1.0) -> dict:
    """Draw one plausible version of the uncertain assumptions."""
    d = copy.deepcopy(d)
    cal = bool(d.get("calibrated"))
    k = (0.5 if cal else 1.0) * scale
    for c in d.get("conversions", []):
        c["base"] = float(c.get("base", -4.0)) + rng.normal(0, 0.5 * k)
    for s in d.get("segments", []):
        _set_seg_mean(s, float(np.clip(_seg_mean(s) + rng.normal(0, 0.1 * k), -1, 1)))
        for o in list((s.get("leaning") or {})):
            s["leaning"][o] = float(np.clip(s["leaning"][o] + rng.normal(0, 0.08 * k), -1, 1))
        s["stubbornness"] = float(np.clip(float(s.get("stubbornness", 0.4)) + rng.normal(0, 0.05 * k), 0.02, 0.98))
    d["persuasion"] = float(np.clip(float(d.get("persuasion", 0.35)) * np.exp(rng.normal(0, 0.25 * k)), 0.02, 0.95))
    if d.get("choice"):
        d["choice"]["turnout_base"] = float(d["choice"].get("turnout_base", -3.5)) + rng.normal(0, 0.3 * k)
    return d


def _outcomes(t: Trajectory, d: dict) -> dict:
    out = {f"action:{k}": float(v[-1]) if v else 0.0 for k, v in t.conversions.items()}
    out["opinion"] = float(t.opinion[-1]) if t.opinion else 0.0
    out["in_favour"] = float(t.opinion_for[-1]) if t.opinion_for else 0.0
    if t.result:
        for o, v in t.result.items():
            out[f"share:{o}"] = float(v)
        out["turnout"] = float(t.turnout[-1]) if t.turnout else 0.0
        out["winner"] = max(sorted(t.result), key=lambda o: t.result[o])
    return out


def monte_carlo(d: dict, runs: int = 30, seed: int = 1000, say: Callable[[str], None] = lambda m: None,
                should_stop: Callable[[], bool] = lambda: False) -> dict:
    rng = np.random.default_rng(seed)
    samples, curves = [], {}
    for i in range(runs):
        if should_stop():
            raise KeyboardInterrupt
        say(f"Run {i + 1}/{runs}")
        di = jitter(d, rng)
        t = simulate(di, int(seed + i))
        samples.append(_outcomes(t, di))
        for k, v in t.conversions.items():
            curves.setdefault(f"action:{k}", []).append(v)
        if t.choice_share:
            for o, v in t.choice_share.items():
                curves.setdefault(f"share:{o}", []).append(v)
    keys = sorted({k for s in samples for k in s if k != "winner"})
    summary = {}
    for k in keys:
        vals = np.array([s.get(k, 0.0) for s in samples], float)
        summary[k] = {"p10": round(float(np.percentile(vals, 10)), 4), "p50": round(float(np.percentile(vals, 50)), 4),
                      "p90": round(float(np.percentile(vals, 90)), 4), "mean": round(float(vals.mean()), 4)}
    bands = {}
    for k, arrs in curves.items():
        n = min(len(a) for a in arrs)
        m = np.array([a[:n] for a in arrs], float)
        bands[k] = {"p10": np.percentile(m, 10, axis=0).round(4).tolist(),
                    "p50": np.percentile(m, 50, axis=0).round(4).tolist(),
                    "p90": np.percentile(m, 90, axis=0).round(4).tolist()}
    targets = {}
    for name, goal in (d.get("targets") or {}).items():
        vals = [s.get(f"action:{name}", 0.0) for s in samples]
        targets[name] = {"goal": goal, "probability": round(sum(v >= goal for v in vals) / len(vals), 3)}
    win = {}
    if any("winner" in s for s in samples):
        for o in d["choice"]["options"]:
            win[o] = round(sum(s.get("winner") == o for s in samples) / len(samples), 3)
    return {"runs": runs, "summary": summary, "bands": bands, "targets": targets, "win_probability": win,
            "samples": samples}


def main_outcome(d: dict) -> str:
    if d.get("choice"):
        return f"share:{d['choice']['options'][0]}"
    if d.get("targets"):
        return f"action:{next(iter(d['targets']))}"
    convs = d.get("conversions") or []
    return f"action:{convs[-1]['name']}" if convs else "opinion"


def sensitivity(d: dict, outcome: str | None = None, seeds=(11, 12), say: Callable[[str], None] = lambda m: None,
                should_stop: Callable[[], bool] = lambda: False) -> dict:
    if outcome is None and d.get("choice"):
        t = simulate(d, seeds[0])
        lead = max(sorted(t.result), key=lambda o: t.result[o]) if t.result else d["choice"]["options"][0]
        outcome = f"share:{lead}"           # what moves the leader's share
    outcome = outcome or main_outcome(d)
    levers = []
    for c in d.get("conversions", []):
        levers.append((f"likelihood of {c['name'].replace('_', ' ')}", ("conv", c["name"]), -0.5, 0.5))
    for s in d.get("segments", []):
        if d.get("choice"):
            for o in d["choice"]["options"]:
                levers.append((f"{s['name'].replace('_', ' ')} support for {o}", ("lean", s["name"], o), -0.15, 0.15))
        else:
            levers.append((f"starting opinion of {s['name'].replace('_', ' ')}", ("seg", s["name"]), -0.15, 0.15))
    levers.append(("persuasion (how fast opinions move)", ("mu",), 0.5, 1.5))
    levers.append(("stubbornness (all groups)", ("stub",), -0.15, 0.15))
    if d.get("choice"):
        levers.append(("turnout level", ("turnout",), -0.5, 0.5))

    def apply(dd, key, delta):
        kind = key[0]
        if kind == "conv":
            c = next(c for c in dd["conversions"] if c["name"] == key[1])
            c["base"] = float(c.get("base", -4)) + delta
        elif kind == "seg":
            s = next(s for s in dd["segments"] if s["name"] == key[1])
            _set_seg_mean(s, float(np.clip(_seg_mean(s) + delta, -1, 1)))
        elif kind == "lean":
            s = next(s for s in dd["segments"] if s["name"] == key[1])
            s.setdefault("leaning", {})[key[2]] = float(np.clip(s["leaning"].get(key[2], 0) + delta, -1, 1))
        elif kind == "mu":
            dd["persuasion"] = float(np.clip(float(dd.get("persuasion", 0.35)) * delta, 0.01, 1))
        elif kind == "stub":
            for s in dd["segments"]:
                s["stubbornness"] = float(np.clip(float(s.get("stubbornness", 0.4)) + delta, 0.02, 0.98))
        elif kind == "turnout":
            dd["choice"]["turnout_base"] = float(dd["choice"].get("turnout_base", -3.5)) + delta

    def value(dd):
        vals = [_outcomes(simulate(dd, s), dd).get(outcome, 0.0) for s in seeds]
        return float(np.mean(vals))

    say("Baseline")
    base = value(d)
    rows = []
    for i, (label, key, lo, hi) in enumerate(levers, 1):
        if should_stop():
            raise KeyboardInterrupt
        say(f"Testing {i}/{len(levers)}: {label}")
        a, b = copy.deepcopy(d), copy.deepcopy(d)
        apply(a, key, lo)
        apply(b, key, hi)
        va, vb = value(a), value(b)
        rows.append({"lever": label, "low": round(va, 4), "high": round(vb, 4),
                     "swing": round(abs(vb - va), 4)})
    rows.sort(key=lambda r: -r["swing"])
    return {"outcome": outcome, "baseline": round(base, 4), "levers": rows}

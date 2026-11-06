"""Calibration, backtesting and a pure-statistics baseline.

Calibration adjusts the scenario's assumptions until fast runs reproduce what really
happened:
  1. starting opinion of each group  <- opinion observations (surveys, ratings)
  2. persuasion (how fast opinions move) <- opinion observed on two or more days
  3. each action's base likelihood   <- the observed counts, prerequisites first
Each step is a bisection on one number, averaged over a few random seeds.

Backtest: calibrate on the early part of the data only, predict the later part, and
compare the error with a statistical baseline (Bass diffusion curve, the standard
model for adoption) fitted to the same early data.
"""
from __future__ import annotations

import copy
import math
from typing import Callable

import numpy as np

from .. import scenario as scenario_mod
from .data import Obs
from .fast import Trajectory, averaged

SEEDS = [11, 12]


def _value(t: Trajectory, o: Obs) -> float:
    r = min(o.round, t.rounds - 1)
    if o.metric == "opinion":
        return t.seg_opinion[o.segment][r] if o.segment else t.opinion[r]
    if o.metric == "opinion_for":
        return t.opinion_for[r]
    if o.metric == "turnout":
        return t.turnout[r] if t.turnout else 0.0
    if o.metric.startswith("share:"):
        return t.choice_share[o.metric[6:]][r] if t.choice_share else 0.0
    return t.conversions[o.metric][r]


def errors(t: Trajectory, obs: list[Obs]) -> list[dict]:
    out = []
    for o in obs:
        sim = _value(t, o)
        out.append({"metric": o.metric, "segment": o.segment, "day": o.day, "actual": o.value,
                    "simulated": round(sim, 3), "error": round(sim - o.value, 3)})
    return out


def score(errs: list[dict]) -> dict:
    """Mean absolute error per metric, plus percentage error for counts."""
    by: dict[str, list[dict]] = {}
    for e in errs:
        by.setdefault(e["metric"] + (f":{e['segment']}" if e["segment"] else ""), []).append(e)
    out = {}
    for k, es in by.items():
        mae = sum(abs(e["error"]) for e in es) / len(es)
        tot = sum(abs(e["actual"]) for e in es)
        out[k] = {"mae": round(mae, 3), "points": len(es),
                  "mape": round(sum(abs(e["error"]) for e in es) / tot, 3) if tot and not k.startswith("opinion") else None}
    return out


def _bisect(f: Callable[[float], float], target: float, lo: float, hi: float, iters: int = 9) -> float:
    """f increasing in x; find x with f(x) ~ target."""
    flo, fhi = f(lo), f(hi)
    if target <= flo:
        return lo
    if target >= fhi:
        return hi
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _order(convs: list[dict]) -> list[dict]:
    done, out = set(), []
    pending = list(convs)
    while pending:
        for c in list(pending):
            if all(r in done for r in (c.get("requires") or [])):
                out.append(c)
                done.add(c["name"])
                pending.remove(c)
                break
        else:
            out += pending
            break
    return out


def calibrate(sc_dict: dict, obs: list[Obs], say: Callable[[str], None] = lambda m: None,
              should_stop: Callable[[], bool] = lambda: False, seeds: list[int] | None = None) -> dict:
    """Return {'scenario': calibrated dict, 'changes': [...], 'fit': {...}}."""
    seeds = seeds or SEEDS
    d = copy.deepcopy(sc_dict)
    scenario_mod.from_dict(copy.deepcopy(d))
    changes = []
    # Actions that really happened imply their gating decisions really passed.
    known = known_polls(d, obs)
    if known:
        d.setdefault("fixed_polls", {}).update(known)
        changes += [{"what": f"decision {k.replace('_', ' ')}", "from": "simulated", "to": "approved (seen in data)"}
                    for k in known]
    max_round = max(o.round for o in obs) + 1
    runs = {"n": 0}

    def run(dd) -> Trajectory:
        if should_stop():
            raise KeyboardInterrupt
        runs["n"] += len(seeds)
        return averaged(dd, seeds, rounds=max_round)

    # 1. starting opinions
    op_obs = sorted([o for o in obs if o.metric == "opinion"], key=lambda o: o.day)
    if op_obs:
        first_day = op_obs[0].day
        early = [o for o in op_obs if o.day == first_day]
        for o in early:
            segs = [s for s in d["segments"] if not o.segment or s["name"] == o.segment]
            say(f"Fitting starting opinion{' of ' + o.segment.replace('_', ' ') if o.segment else ''}")
            before = [_mean(s) for s in segs]

            def f(shift, segs=segs, o=o, before=before):
                for s, b in zip(segs, before):
                    _set_mean(s, max(-1, min(1, b + shift)))
                return _value(run(d), o)

            shift = _bisect(f, o.value, -1.0, 1.0, iters=7)
            for s, b in zip(segs, before):
                _set_mean(s, round(max(-1, min(1, b + shift)), 3))
                changes.append({"what": f"starting opinion of {s['name'].replace('_', ' ')}",
                                "from": round(b, 3), "to": _mean(s)})
        # 2. persuasion, when opinion is seen moving over time
        later = [o for o in op_obs if o.day > first_day]
        if later:
            say("Fitting how fast opinions move")
            best, best_err = d.get("persuasion", 0.35), None
            for mu in (0.1, 0.2, 0.35, 0.5, 0.7):
                d["persuasion"] = mu
                t = run(d)
                err = sum(abs(_value(t, o) - o.value) for o in later)
                if best_err is None or err < best_err:
                    best, best_err = mu, err
            changes.append({"what": "persuasion", "from": sc_dict.get("persuasion", 0.35), "to": best})
            d["persuasion"] = best

    # 2b. choice: poll shares -> group leanings; observed turnout -> turnout level
    share_obs = [o for o in obs if o.metric.startswith("share:")]
    if share_obs and d.get("choice"):
        opts = d["choice"]["options"]
        orig = {(sg["name"], o): float(sg.get("leaning", {}).get(o, 0.0)) for sg in d["segments"] for o in opts}
        for _pass in range(2):
            for opt in opts:
                pts = [o for o in share_obs if o.metric == f"share:{opt}"]
                if not pts:
                    continue
                target = pts[-1]
                segs = [s for s in d["segments"] if not target.segment or s["name"] == target.segment]
                before = [float(s.get("leaning", {}).get(opt, 0.0)) for s in segs]
                say(f"Fitting support for {opt}" + (f" among {target.segment.replace('_', ' ')}" if target.segment else ""))

                def f(shift, segs=segs, before=before, opt=opt, target=target):
                    for sg, b in zip(segs, before):
                        sg.setdefault("leaning", {})[opt] = max(-1, min(1, b + shift))
                    return _value(run(d), target)

                shift = _bisect(f, target.value, -0.8, 0.8, iters=6)
                for sg, b in zip(segs, before):
                    sg["leaning"][opt] = round(max(-1, min(1, b + shift)), 3)
                if _pass == 1:
                    changes.append({"what": f"support for {opt}" + (f" ({target.segment})" if target.segment else " (all groups)"),
                                    "from": round(sum(orig[(sg["name"], opt)] for sg in segs) / len(segs), 3),
                                    "to": round(sum(sg['leaning'][opt] for sg in segs) / len(segs), 3)})
    turn = sorted([o for o in obs if o.metric == "turnout"], key=lambda o: o.day)
    if turn and d.get("choice"):
        say("Fitting turnout")
        before = d["choice"].get("turnout_base", -3.5)

        def f(b):
            d["choice"]["turnout_base"] = b
            return _value(run(d), turn[-1])

        d["choice"]["turnout_base"] = round(_bisect(f, turn[-1].value, -9.0, 2.0, iters=8), 3)
        changes.append({"what": "turnout level (log-odds)", "from": before, "to": d["choice"]["turnout_base"]})

    # 3. action likelihoods, prerequisites first
    for c in _order(d.get("conversions", [])):
        pts = sorted([o for o in obs if o.metric == c["name"]], key=lambda o: o.day)
        if not pts:
            continue
        last = pts[-1]
        say(f"Fitting how likely people are to {c['label'] if c.get('label') else c['name']}")
        before = c.get("base", -4.0)

        def f(b, c=c, last=last):
            c["base"] = b
            return _value(run(d), last)

        b = _bisect(f, last.value, -12.0, 2.0)
        c["base"] = round(b, 3)
        changes.append({"what": f"likelihood of {c['name'].replace('_', ' ')} (log-odds)",
                        "from": before, "to": c["base"]})

    say("Checking the fit")
    t = run(d)
    errs = errors(t, obs)
    scenario_mod.from_dict(copy.deepcopy(d))
    return {"scenario": d, "changes": changes, "fit": {"errors": errs, "score": score(errs)},
            "runs": runs["n"]}


def _cond_polls(cond) -> list[str]:
    if not cond:
        return []
    if "any" in cond:
        return [p for c in cond["any"] for p in _cond_polls(c)]
    return [cond.get("poll")] if str(cond.get("result", "yes")).lower() in ("yes", "true", "pass", "passed") else []


def known_polls(d: dict, obs: list[Obs]) -> dict[str, bool]:
    """Decisions that must have passed, because actions they unlock were observed."""
    seen = {o.metric for o in obs if o.value > 0}
    out = {}
    for c in d.get("conversions", []):
        if c["name"] in seen:
            ps = _cond_polls(c.get("when") or {})
            if len(ps) == 1:            # unambiguous
                out[ps[0]] = True
    return out


def _mean(seg: dict) -> float:
    st = seg.get("stance", 0.0)
    return float(st.get("mean", 0.0)) if isinstance(st, dict) else float(st)


def _set_mean(seg: dict, v: float) -> None:
    st = seg.get("stance", 0.0)
    if isinstance(st, dict):
        st["mean"] = v
    else:
        seg["stance"] = {"mean": v, "sd": 0.3}


def seed_opinions(sc_dict: dict, reviews: dict) -> tuple[dict, list[dict]]:
    """Set starting opinions from reviews/ratings ({segment or '*': (mean, sd, n)})."""
    d = copy.deepcopy(sc_dict)
    changes = []
    for s in d["segments"]:
        src = reviews.get(s["name"]) or reviews.get("*")
        if not src:
            continue
        mean, sd, n = src
        before = _mean(s)
        s["stance"] = {"mean": round(mean, 3), "sd": round(sd, 3)}
        changes.append({"what": f"starting opinion of {s['name'].replace('_', ' ')}", "from": before,
                        "to": mean, "based_on": f"{n} reviews"})
    return d, changes


# ------------------------------------------------------------------ baseline + backtest
def bass_fit(t: np.ndarray, y: np.ndarray):
    """Fit cumulative adoption y(t) with a Bass curve; returns a predict(t) function."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    if len(t) < 3 or y.max() <= 0:
        rate = (y[-1] / t[-1]) if len(t) and t[-1] > 0 else 0.0
        return lambda x: rate * np.asarray(x, float), {"model": "linear", "rate": rate}
    best = None
    for p in np.geomspace(1e-4, 0.5, 30):
        for q in np.linspace(0, 1.5, 31):
            e = np.exp(-(p + q) * t)
            F = (1 - e) / (1 + (q / p) * e)
            denom = float((F * F).sum())
            if denom <= 0:
                continue
            m = max(float((F * y).sum()) / denom, float(y.max()))
            sse = float(((m * F - y) ** 2).sum())
            if best is None or sse < best[0]:
                best = (sse, p, q, m)
    _, p, q, m = best

    def predict(x):
        x = np.asarray(x, float)
        e = np.exp(-(p + q) * x)
        return m * (1 - e) / (1 + (q / p) * e)
    return predict, {"model": "bass", "p": round(p, 5), "q": round(q, 4), "market": round(m, 1)}


def backtest(sc_dict: dict, obs: list[Obs], cutoff_day: float | None = None,
             say: Callable[[str], None] = lambda m: None, should_stop=lambda: False) -> dict:
    days = sorted({o.day for o in obs})
    if len(days) < 3:
        raise ValueError("A backtest needs observations on at least 3 different days.")
    if cutoff_day is None:
        cutoff_day = days[max(1, int(math.floor(len(days) * 0.6)) - 1)]
    train = [o for o in obs if o.day <= cutoff_day]
    test = [o for o in obs if o.day > cutoff_day]
    if not test:
        raise ValueError("Nothing left to predict after the cut-off day.")
    say(f"Calibrating on days up to {cutoff_day:g}, predicting {len(test)} later points")
    cal = calibrate(sc_dict, train, say=say, should_stop=should_stop)
    max_round = max(o.round for o in obs) + 1
    t = averaged(cal["scenario"], SEEDS, rounds=max_round)
    sim_errs = errors(t, test)
    base_errs = []
    for metric in sorted({o.metric for o in test}):
        tr = [o for o in train if o.metric == metric and not o.segment]
        te = [o for o in test if o.metric == metric and not o.segment]
        if not te:
            continue
        if metric.startswith("opinion") or metric.startswith("share:"):
            last = tr[-1].value if tr else 0.0
            pred = lambda x, last=last: np.full(len(np.atleast_1d(x)), last)
            info = {"model": "last value"}
        else:
            pred, info = bass_fit(np.array([o.day for o in tr] or [0.0]), np.array([o.value for o in tr] or [0.0]))
        ys = pred(np.array([o.day for o in te]))
        for o, yhat in zip(te, np.atleast_1d(ys)):
            base_errs.append({"metric": metric, "segment": "", "day": o.day, "actual": o.value,
                              "simulated": round(float(yhat), 3), "error": round(float(yhat) - o.value, 3),
                              "baseline": info})
    s_sim, s_base = score(sim_errs), score(base_errs)
    verdict = {}
    for k in s_sim:
        if k in s_base:
            verdict[k] = "simulation" if s_sim[k]["mae"] <= s_base[k]["mae"] else "baseline"
    return {"cutoff_day": cutoff_day, "train_points": len(train), "test_points": len(test),
            "simulation": {"errors": sim_errs, "score": s_sim},
            "baseline": {"errors": base_errs, "score": s_base}, "better": verdict,
            "calibration": {"changes": cal["changes"]}}

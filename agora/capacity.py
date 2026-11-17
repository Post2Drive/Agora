"""Capacity planning: measure how fast the chosen model setup is, then estimate time, cost and
the sizes (people, rounds, scenarios) that fit a time budget."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from . import settings

PROMPT_TOKENS = 900       # a typical agent prompt
OUT_TOKENS = 180          # a typical agent reply
_META = {"task": "json", "default": {"ok": True}}      # read only by the mock backend


def sample_messages(i: int) -> list[dict]:
    feed = "\n".join(
        f"[p{j}] (WhatsApp · Residents) Neighbour {j} (@n{j}): \"Has anyone tried the free sample yet? "
        f"I heard it is only for registered flats.\" [{j % 4} reactions]" for j in range(8 + i % 3))
    background = ("A company is offering a free seven day sample pack to residents of apartment communities. "
                  "Registration opens after the residents association approves it. ") * 6
    system = ("You are Asha, a 34 year old teacher. You are practical, careful with money and read labels. "
              "You use WhatsApp, Instagram and Facebook and write the way people do on each. Stay in character.")
    user = (f"Background you know:\n{background}\n\nOn your screen now:\n{feed}\n\n"
            "Reply with JSON only, at most 3 actions (an empty list is normal):\n"
            '{"thoughts": "one short sentence", "stance": <-1..1>, "actions": '
            '[{"type": "post", "where": "whatsapp", "text": "..."}]}')
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def benchmark(llm, levels=(1, 2, 4), say=print) -> dict:
    """Send real-sized agent prompts, alone and in parallel, and measure calls per second."""
    llm.generate(sample_messages(0), max_tokens=OUT_TOKENS, temperature=0.8, json_mode=True, seed=0, meta=_META)
    thr, chars, n = {}, [], 1
    for p in levels:
        calls = max(2, p)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=p) as ex:
            outs = list(ex.map(lambda k, base=n: llm.generate(
                sample_messages(base + k), max_tokens=OUT_TOKENS, temperature=0.8, json_mode=True,
                seed=base + k, meta=_META), range(calls)))
        n += calls
        thr[p] = calls / max(time.time() - t0, 1e-6)
        chars += [len(o) for o in outs]
        say(f"  {p} at a time: {thr[p]:.3f} model calls per second")
    ps = sorted(thr)
    best_p, best_t = ps[0], thr[ps[0]]
    for p in ps[1:]:
        if thr[p] >= best_t * 1.15:        # only count a clear gain, not noise
            best_p, best_t = p, thr[p]
        else:
            break
    return {"model": llm.cfg.model, "backend": llm.cfg.backend,
            "levels": {str(p): round(v, 4) for p, v in thr.items()},
            "best_parallel": best_p, "best_throughput": round(best_t, 4),
            "avg_reply_tokens": max(1, int(sum(chars) / len(chars)) // 4),
            "measured": time.strftime("%Y-%m-%d %H:%M")}


def _bench_file():
    return settings.home() / "benchmarks.json"


def save_bench(label: str, model: str, result: dict) -> None:
    p = _bench_file()
    d = {}
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
    d[f"{label}|{model}"] = result
    settings.home().mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def load_bench(label: str, model: str):
    p = _bench_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get(f"{label}|{model}")
    except (OSError, ValueError):
        return None


def awake_share(sc) -> float:
    """Share of people expected to be awake (and so ask the model) in an average round."""
    tot = sum(s.share for s in sc.segments) or 1.0
    act = sum(s.activity * s.share for s in sc.segments) / tot
    return min(1.0, max(0.01, act * 0.55))


def plan(sc, bench, *, agents=None, rounds=None, scenarios=1, awake=None, price=None, observed=None) -> dict:
    explicit_awake = awake is not None
    awake = awake_share(sc) if awake is None else min(1.0, max(0.001, float(awake)))
    people = int(agents) if agents else sc.llm_agents + sum(1 for a in sc.accounts if a.llm)
    rounds = int(rounds) if rounds else sc.rounds
    scenarios = max(1, int(scenarios))
    if observed:                                   # this study has already run: trust its own numbers
        thr = float(observed["throughput"])
        par, out_tok, source = 1, OUT_TOKENS, "observed"
        if not explicit_awake:
            awake = float(observed["calls_per_person_round"])
    elif bench:
        thr = float(bench["best_throughput"]) * float(bench.get("real_factor", 1.0))
        par = int(bench.get("best_parallel", 1))
        out_tok = int(bench.get("avg_reply_tokens", OUT_TOKENS))
        source = "measured"
    else:
        from . import hardware
        prof = hardware.detect()
        thr = 1.0 / (prof.estimate_hours(1) * 3600)
        par, out_tok, source = prof.parallel, OUT_TOKENS, "rough"
    calls = int(people * rounds * awake) * scenarios
    seconds = calls / thr
    cost = None if not price else calls * (PROMPT_TOKENS * price[0] + out_tok * price[1]) / 1e6
    presets = {name: {"hours": h, "people": max(1, int(h * 3600 * thr / (rounds * awake * scenarios)))}
               for name, h in (("Quick", 1), ("Overnight", 10), ("Weekend", 48))}
    return {"people": people, "rounds": rounds, "scenarios": scenarios, "awake": awake, "calls": calls,
            "seconds": seconds, "throughput": thr, "parallel": par, "source": source, "cost": cost,
            "presets": presets}


def observed(project):
    """Real speed of a study that has already run: model calls per second, and calls per person per round.
    None when there is too little to go on, or most replies came from the cache."""
    p = Path(project) / "agora.db"
    if not p.exists():
        return None
    db = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        n, calls, secs, hits = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(llm_calls),0), COALESCE(SUM(seconds),0), COALESCE(SUM(cache_hits),0) "
            "FROM rounds").fetchone()
        rows = db.execute("SELECT kind, attrs FROM agents").fetchall()
    except sqlite3.Error:
        return None
    finally:
        db.close()
    people = sum(1 for k, a in rows if k in ("llm", "account") and json.loads(a or "{}").get("llm", True))
    if n < 3 or calls < 8 or secs <= 0 or people == 0 or hits > 0.2 * calls:
        return None
    return {"rounds": int(n), "calls": int(calls), "seconds": float(secs), "people": people,
            "throughput": calls / secs, "calls_per_person_round": calls / (n * people)}


def learn(label: str, model: str, obs: dict) -> dict:
    """Remember how this setup really performs, so every later plan is corrected the same way."""
    b = load_bench(label, model)
    if b:
        b["real_factor"] = round(obs["throughput"] / float(b["best_throughput"]), 4)
        b["real_from"] = f"{obs['calls']} calls in {obs['seconds'] / 60:.0f} min"
    else:
        b = {"model": model, "backend": label, "levels": {}, "best_parallel": 1,
             "best_throughput": round(obs["throughput"], 4), "avg_reply_tokens": OUT_TOKENS,
             "measured": "from a real run", "real_factor": 1.0,
             "real_from": f"{obs['calls']} calls in {obs['seconds'] / 60:.0f} min"}
    save_bench(label, model, b)
    return b


def describe_source(p: dict, bench, obs) -> str:
    if p["source"] == "observed" and obs:
        return f"observed in this study: {obs['calls']} calls in {obs['seconds'] / 60:.0f} min"
    if p["source"] == "measured" and bench:
        s = f"benchmark of {bench['measured']}"
        f = bench.get("real_factor", 1.0)
        if f and f != 1.0:
            s += f", scaled by x{f:.2f} from a real run ({bench.get('real_from', '')})"
        return s
    return "rough guess; run `agora benchmark` and one real run for better numbers"


def fmt_time(seconds: float) -> str:
    if seconds < 90:
        return f"about {seconds:.0f} seconds"
    if seconds < 5400:
        return f"about {seconds / 60:.0f} minutes"
    if seconds < 2 * 86400:
        return f"about {seconds / 3600:.1f} hours"
    return f"about {seconds / 86400:.1f} days"

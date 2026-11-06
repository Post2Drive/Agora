"""Command line: `agora <command>`. Run `agora --help` for the list."""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from . import __version__, hardware, scenario as scenario_mod
from .sim.engine import DB_FILE, SCENARIO_FILE, Simulation
from .store import Store
from .summary import summarise


def _llm_override(args) -> dict:
    o = {}
    if getattr(args, "mock", False):
        o["backend"] = "mock"
    for k in ("backend", "model", "url", "parallel"):
        v = getattr(args, k, None)
        if v is not None:
            o[k] = v
    return o


def cmd_hardware(args) -> int:
    p = hardware.detect()
    print(f"Machine tier : {p.tier}")
    print(f"RAM          : {p.ram_gb} GB   CPUs: {p.cpus}")
    print(f"GPU          : {p.gpu} ({p.vram_gb} GB)")
    print(f"Suggested    : model {p.model}, {p.llm_agents} LLM voices, "
          f"{p.crowd_agents} crowd agents, parallel {p.parallel}")
    return 0


def cmd_new(args) -> int:
    dst = Path(args.project)
    src = Path(args.template)
    if src.is_dir():
        src = src / SCENARIO_FILE
    if dst.exists() and any(dst.iterdir()):
        print(f"{dst} already exists and is not empty.", file=sys.stderr)
        return 1
    scenario_mod.load(src)                     # validate before copying
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst / SCENARIO_FILE)
    print(f"Created project {dst}. Next: agora check {dst}   then   agora run {dst}")
    return 0


def cmd_check(args) -> int:
    proj = Path(args.project)
    sc = scenario_mod.load(proj / SCENARIO_FILE)
    print(f"Scenario OK: {sc.name} - {len(sc.segments)} segments, {len(sc.accounts)} accounts, "
          f"{len(sc.spaces)} groups/communities, {len(sc.events)} events, "
          f"{len(sc.conversions)} conversions")
    sim = Simulation(proj, _llm_override(args))
    ok, msg = sim.llm.status()
    print(("Model OK: " if ok else "Model problem: ") + msg)
    prof = hardware.detect()
    voices = sc.llm_agents + sum(1 for a in sc.accounts if a.llm)
    act = sum(s.activity * s.share for s in sc.segments) / max(1e-9, sum(s.share for s in sc.segments))
    calls = int(voices * sc.rounds * act * 0.55)
    if sim.llm_cfg.backend != "mock":
        print(f"Estimated model calls: ~{calls}. On this machine ({prof.tier}) that is roughly "
              f"{prof.estimate_hours(calls):.1f} hours. Runs can be stopped and resumed any time.")
    sim.close()
    return 0 if ok else 2


def cmd_run(args) -> int:
    proj = Path(args.project)
    sim = Simulation(proj, _llm_override(args))
    ok, msg = sim.llm.status()
    if not ok:
        print(msg, file=sys.stderr)
        sim.close()
        return 2
    sim.prepare(force=args.force)
    done = sim.store.last_round() + 1
    if done >= sim.sc.rounds:
        print("This run is already complete. See: agora status", proj)
        sim.close()
        return 0
    print(f"{'Resuming' if done else 'Starting'} {sim.sc.name} at round {done}/{sim.sc.rounds} "
          f"with {sim.llm_cfg.backend}:{sim.llm_cfg.model}. Ctrl+C stops safely; run again to resume.")
    t0 = time.time()
    started = done

    def progress(p):
        n = p["round"] - started + 1
        left = p["of"] - p["round"] - 1
        eta = (time.time() - t0) / n * left
        print(f"  round {p['round'] + 1:>3}/{p['of']}  active {p['active']:>5}  posts {p['posts']:>3}  "
              f"conversions {p['conversions']:>3}  model calls {p['llm_calls']:>3} "
              f"(+{p['cache_hits']} cached)  {p['seconds']:.1f}s  ETA {eta / 60:.0f} min", flush=True)

    try:
        sim.run(rounds=args.rounds, progress=progress, force=args.force)
    except KeyboardInterrupt:
        print(f"\nStopped. Completed rounds are saved; run `agora run {proj}` to resume.")
        return 130
    finally:
        sim.close()
    print("Done. Next: agora status", proj)
    return 0


def cmd_status(args) -> int:
    proj = Path(args.project)
    store = Store(proj / DB_FILE)
    sc = scenario_mod.load(proj / SCENARIO_FILE)
    s = summarise(store)
    print(f"{sc.name}: {s['rounds_done']}/{sc.rounds} rounds, {s['llm_calls']} model calls "
          f"({s['cache_hits']} cached), {s['seconds'] / 60:.1f} min")
    for name, p in s["polls"].items():
        print(f"  poll {name}: {'PASSED' if p['passed'] else 'FAILED'} ({p['yes']} yes / {p['no']} no)")
    print("  posts: " + ", ".join(f"{k} {v}" for k, v in s["posts"].items()))
    print("  opinion by segment (start -> now):")
    for seg, d in s["segments"].items():
        print(f"    {seg:<26} {d['agents']:>5} agents  {d['stance_start']:+.2f} -> {d['stance_now']:+.2f}")
    for name, c in s["conversions"].items():
        print(f"  {name}: {c['total']}  " + ", ".join(f"{k} {v}" for k, v in c["by_segment"].items()))
    store.close()
    return 0


def cmd_feed(args) -> int:
    proj = Path(args.project)
    store = Store(proj / DB_FILE)
    where, params = ["p.kind != 'repost'", "p.kind != 'forward'"], []
    if args.platform:
        where.append("p.platform = ?")
        params.append(args.platform)
    if args.space:
        where.append("p.space = ?")
        params.append(args.space)
    rows = store.rows(
        "SELECT p.id, p.round, p.platform, p.space, a.name, a.handle, a.kind, p.kind, p.parent, "
        "p.text, p.stance FROM posts p JOIN agents a ON a.id = p.author WHERE "
        + " AND ".join(where) + " ORDER BY p.id DESC LIMIT ?", (*params, args.last))
    for pid, r, plat, space, name, handle, kind, pk, parent, text, st in reversed(rows):
        loc = plat + (f"/{space}" if space else "")
        rep = f" ↳p{parent}" if pk == "reply" else ""
        print(f"[p{pid} r{r} {loc}{rep}] {name} (@{handle}, {kind}, {st:+.1f}): {text}")
    store.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agora", description="Agora: local multi-agent social simulation")
    ap.add_argument("--version", action="version", version=f"agora {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("hardware", help="detect this machine and suggest settings").set_defaults(f=cmd_hardware)

    p = sub.add_parser("new", help="create a project folder from a scenario")
    p.add_argument("project")
    p.add_argument("--from", dest="template", required=True, help="scenario.yaml or a folder with one")
    p.set_defaults(f=cmd_new)

    def llm_flags(p):
        p.add_argument("--mock", action="store_true", help="no model: fast fake agents for testing")
        p.add_argument("--backend", choices=["ollama", "openai", "mock"])
        p.add_argument("--model")
        p.add_argument("--url")
        p.add_argument("--parallel", type=int)

    p = sub.add_parser("check", help="validate scenario, model and estimate run time")
    p.add_argument("project")
    llm_flags(p)
    p.set_defaults(f=cmd_check)

    p = sub.add_parser("run", help="run or resume a simulation")
    p.add_argument("project")
    p.add_argument("--rounds", type=int, help="only run this many rounds now")
    p.add_argument("--force", action="store_true", help="resume even if scenario.yaml changed")
    llm_flags(p)
    p.set_defaults(f=cmd_run)

    p = sub.add_parser("status", help="summary of a run")
    p.add_argument("project")
    p.set_defaults(f=cmd_status)

    p = sub.add_parser("feed", help="read what agents posted")
    p.add_argument("project")
    p.add_argument("--platform", choices=["x", "reddit", "whatsapp"])
    p.add_argument("--space")
    p.add_argument("--last", type=int, default=30)
    p.set_defaults(f=cmd_feed)

    args = ap.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main())

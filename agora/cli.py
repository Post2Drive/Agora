"""Command line: `agora <command>`. Run `agora --help` for the list."""
from __future__ import annotations

import argparse
import json
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
    demos = {"demo": "nutrivance_sampling", "nutrivance_sampling": "nutrivance_sampling",
             "election": "election", "election-demo": "election"}
    if args.template in demos:
        from importlib import resources
        src = Path(str(resources.files("agora.examples").joinpath(demos[args.template], SCENARIO_FILE)))
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
    from .report.analysis import Analysis
    if sc.choice and s["rounds_done"]:
        an = Analysis(proj)
        c = an.choice()
        an.close()
        print(f"  {c['question']} ({c['basis']}, weighted): " + ", ".join(
            f"{o} {v * 100:.1f}%" for o, v in sorted(c["result"].items(), key=lambda x: -x[1]))
            + f"; turnout {c['turnout'] * 100:.1f}%")
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


def _make_llm(args, project: Path):
    from .pipeline import make_llm
    return make_llm(project, _llm_override(args))


def cmd_create(args) -> int:
    """MiroFish-style entry: upload documents + describe what to predict -> ready project."""
    from .pipeline import CreateOptions, create_project
    proj = Path(args.project)
    if (proj / SCENARIO_FILE).exists() and not args.overwrite:
        print(f"{proj} already has a scenario. Use --overwrite to redraft it.", file=sys.stderr)
        return 1
    opts = CreateOptions(fast=args.fast, personas=not args.no_personas, llm_agents=args.llm_agents,
                         crowd=args.crowd, hours=args.hours, seed=args.seed, llm=_llm_override(args),
                         entity_agents=args.entities)
    try:
        create_project(proj, args.docs, args.prompt, opts, say=lambda m: print(m, flush=True))
    except RuntimeError as e:
        print(f"{e}\n(Use --mock to try the pipeline without a model.)", file=sys.stderr)
        return 2
    print(f"Review {proj / SCENARIO_FILE} and {proj / 'graph.html'}, then:")
    print(f"  agora check {proj}\n  agora run {proj}")
    return 0


def cmd_graph(args) -> int:
    """Add documents and/or rebuild the graph and viewer for an existing project."""
    from .graph import GRAPH_FILE, GraphStore
    from .graph import build as gbuild, ingest as gingest, view as gview
    proj = Path(args.project)
    gs = GraphStore(proj / GRAPH_FILE)
    goal = gs.get_meta("goal") or ""
    if not goal and (proj / "prompt.txt").exists():
        goal = (proj / "prompt.txt").read_text(encoding="utf-8").strip()
    if args.add:
        for r in gingest.ingest(gs, proj, args.add):
            print(f"{r['file']}: " + ("already added" if r["skipped"] else f"{r['chunks']} chunks"))
    llm = None
    if not args.fast:
        _, llm = _make_llm(args, proj)
        ok, msg = llm.status()
        if not ok:
            print(msg, file=sys.stderr)
            return 2
    st = gbuild.build(gs, llm, goal, lambda p: print(f"  chunk {p['chunk']}/{p['of']}", flush=True))
    gbuild.export(gs, proj)
    path = gview.write(gs, proj / "graph.html", title=(goal or proj.name)[:60])
    print(f"{st['nodes']} entities, {st['edges']} relations, types {st['node_types']} -> {path}")
    gs.close()
    return 0


def _project_llm(args, proj: Path):
    from .pipeline import make_llm
    sc = scenario_mod.load(proj / SCENARIO_FILE)
    cfg = {k: v for k, v in sc.llm.items() if k in ("backend", "model", "url", "parallel")}
    cfg.update(_llm_override(args))
    _, llm = make_llm(proj, cfg)
    ok, msg = llm.status()
    if not ok:
        print(msg + "\n(Use --mock to try without a model.)", file=sys.stderr)
        sys.exit(2)
    return llm


def cmd_report(args) -> int:
    from .report.writer import write_report
    proj = Path(args.project)
    write_report(proj, _project_llm(args, proj), say=lambda m: print(m, flush=True))
    print(f"Open {proj / 'report' / 'report.html'}")
    return 0


def cmd_ask(args) -> int:
    from .report.interact import ask
    proj = Path(args.project)
    r = ask(proj, _project_llm(args, proj), args.question)
    print(r["answer"])
    for q in r["quotes"].values():
        print("  " + q)
    return 0


def cmd_chat(args) -> int:
    from .report.interact import chat, people
    proj = Path(args.project)
    if not args.agent:
        for x in people(proj):
            print(f"@{x['handle']:<22} {x['name']:<28} {x['segment']:<26} opinion {x['stance']:+.2f}")
        return 0
    llm = _project_llm(args, proj)
    handle = args.agent.lstrip("@")
    msgs = [args.message] if args.message else []
    if not msgs:
        print(f"Talking to @{handle}. Empty line to stop.")
    while True:
        m = msgs.pop(0) if msgs else (input("you> ").strip() if not args.message else "")
        if not m:
            return 0
        print(f"{handle}> {chat(proj, llm, handle, m)['reply']}")
        if args.message:
            return 0


def cmd_interview(args) -> int:
    from .report.interact import interview
    proj = Path(args.project)
    r = interview(proj, _project_llm(args, proj), args.question, segment=args.segment or "", n=args.n,
                  say=lambda m: print(m, flush=True))
    t = r["tally"]
    print(f"\n{t['yes']} yes, {t['unsure']} unsure, {t['no']} no (average {t['average']:+.2f})")
    for a in r["answers"]:
        print(f"- {a['name']} ({a['segment']}, {a['agree']:+.1f}): {a['answer']}")
    return 0


def cmd_inject(args) -> int:
    from .report.interact import inject
    ev = {"type": "post" if args.account else "news", "text": args.text, "account": args.account,
          "platform": args.platform}
    if args.shift:
        ev["shift"] = {k.strip(): float(v) for k, _, v in (x.rpartition("=") for x in args.shift)}
    r = inject(Path(args.project), ev, args.round)
    print(f"Added at round {r['round'] + 1}. Run `agora run {args.project}` to continue.")
    return 0


def cmd_fork(args) -> int:
    from .report.interact import fork
    dst = fork(Path(args.project), Path(args.new), title=args.title or "")
    print(f"Created {dst}. Edit {dst / SCENARIO_FILE}, then: agora run {dst}")
    return 0


def cmd_compare(args) -> int:
    from .report.interact import compare
    c = compare([Path(p) for p in args.projects])
    cols = [x for x in c["columns"] if x.get("run")]
    w = 22
    print("".ljust(28) + "".join(x["title"][:w - 2].ljust(w) for x in cols))
    for n in c["actions"]:
        print(n.ljust(28) + "".join((f"{x['actions'][n]['count']} ({x['actions'][n]['rate'] * 100:.1f}%)"
                                     if n in x["actions"] else "-").ljust(w) for x in cols))
    print("opinion at end".ljust(28) + "".join(f"{x['opinion_end']:+.2f}".ljust(w) for x in cols))
    print("in favour at end".ljust(28) + "".join(f"{x['for_end'] * 100:.1f}%".ljust(w) for x in cols))
    return 0


def cmd_data(args) -> int:
    from .calibrate.project import save_data
    text = Path(args.file).read_text(encoding="utf-8-sig")
    print(json.dumps(save_data(Path(args.project), args.kind, text), indent=1))
    return 0


def cmd_calibrate(args) -> int:
    from .calibrate.project import apply_calibration, calibrate_project
    proj = Path(args.project)
    res = calibrate_project(proj, say=lambda m: print(m, flush=True))
    print("\nChanges:")
    for c in res["changes"]:
        print(f"  {c['what']}: {c['from']} -> {c['to']}")
    for k, v in (res["fit"].get("score") or {}).items():
        print(f"  fit {k}: average error {v['mae']}" + (f" ({v['mape'] * 100:.1f}%)" if v.get("mape") is not None else ""))
    if args.apply:
        apply_calibration(proj)
        print("Applied to scenario.yaml (previous version saved).")
    else:
        print(f"Review, then: agora calibrate {proj} --apply")
    return 0


def cmd_backtest(args) -> int:
    from .calibrate.project import backtest_project
    r = backtest_project(Path(args.project), args.cutoff, say=lambda m: print(m, flush=True))
    print(f"\nCalibrated on days up to {r['cutoff_day']:g}; predicted {r['test_points']} later points.")
    for k in r["simulation"]["score"]:
        sim = r["simulation"]["score"][k]["mae"]
        base = r["baseline"]["score"].get(k, {}).get("mae")
        print(f"  {k}: simulation error {sim}" + (f", statistical baseline {base} -> better: {r['better'].get(k)}"
                                                  if base is not None else ""))
    return 0


def cmd_forecast(args) -> int:
    from .calibrate.project import forecast_project
    f = forecast_project(Path(args.project), runs=args.runs, with_sensitivity=not args.no_sensitivity,
                         say=lambda m: print(m, flush=True))
    mc = f["monte_carlo"]
    print("\nLikely range (10th-50th-90th percentile):")
    for k, v in mc["summary"].items():
        print(f"  {k}: {v['p10']} / {v['p50']} / {v['p90']}")
    for o, pwin in mc["win_probability"].items():
        print(f"  chance {o} wins: {pwin * 100:.0f}%")
    for n, t in mc["targets"].items():
        print(f"  chance {n} reaches {t['goal']}: {t['probability'] * 100:.0f}%")
    if f.get("sensitivity"):
        print(f"\nWhat matters most for {f['sensitivity']['outcome']}:")
        for r in f["sensitivity"]["levers"][:6]:
            print(f"  {r['lever']}: {r['low']} .. {r['high']}")
    return 0


def cmd_web(args) -> int:
    from .web.server import serve
    serve(Path(args.dir), port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agora", description="Agora: local multi-agent social simulation")
    ap.add_argument("--version", action="version", version=f"agora {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("hardware", help="detect this machine and suggest settings").set_defaults(f=cmd_hardware)

    p = sub.add_parser("web", help="open the Agora website on this computer (http://127.0.0.1:8765)")
    p.add_argument("--dir", default=str(Path.home() / "AgoraProjects"), help="projects folder")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(f=cmd_web)

    p = sub.add_parser("new", help="create a project folder from a scenario")
    p.add_argument("project")
    p.add_argument("--from", dest="template", required=True,
                   help="scenario.yaml, a folder with one, or 'demo'")
    p.set_defaults(f=cmd_new)

    def llm_flags(p):
        p.add_argument("--mock", action="store_true", help="no model: fast fake agents for testing")
        p.add_argument("--backend", choices=["ollama", "openai", "mock"])
        p.add_argument("--model")
        p.add_argument("--url")
        p.add_argument("--parallel", type=int)

    p = sub.add_parser("create", help="upload documents + describe what to predict -> ready project")
    p.add_argument("project")
    p.add_argument("--docs", nargs="+", required=True, help="PDF, DOCX, TXT, MD, CSV, JSON, HTML files")
    p.add_argument("--prompt", required=True, help="what you want to predict, in plain words")
    p.add_argument("--fast", action="store_true", help="build the graph without the model (rougher)")
    p.add_argument("--no-personas", action="store_true", help="skip writing individual personas")
    p.add_argument("--llm-agents", type=int, help="LLM voices (default: fits --hours on this machine)")
    p.add_argument("--crowd", type=int, help="crowd agents (default: up to 3000)")
    p.add_argument("--hours", type=float, default=12, help="run-time budget used to size the population")
    p.add_argument("--entities", type=int, default=20,
                   help="named agents made from people/organisations in the documents (0 = none)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--overwrite", action="store_true")
    llm_flags(p)
    p.set_defaults(f=cmd_create)

    p = sub.add_parser("graph", help="add documents / rebuild the knowledge graph and graph.html")
    p.add_argument("project")
    p.add_argument("--add", nargs="+", help="more documents to add first")
    p.add_argument("--fast", action="store_true")
    llm_flags(p)
    p.set_defaults(f=cmd_graph)

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

    p = sub.add_parser("data", help="add real data: observations (what happened) or reviews")
    p.add_argument("project")
    p.add_argument("kind", choices=["observations", "reviews"])
    p.add_argument("file")
    p.set_defaults(f=cmd_data)

    p = sub.add_parser("calibrate", help="fit the setup's assumptions to your real data")
    p.add_argument("project")
    p.add_argument("--apply", action="store_true", help="write the fitted numbers into scenario.yaml")
    p.set_defaults(f=cmd_calibrate)

    p = sub.add_parser("backtest", help="calibrate on early data, predict later data, compare with a baseline")
    p.add_argument("project")
    p.add_argument("--cutoff", type=float, help="last day used for fitting")
    p.set_defaults(f=cmd_backtest)

    p = sub.add_parser("forecast", help="Monte Carlo ranges, win/target probabilities, sensitivity")
    p.add_argument("project")
    p.add_argument("--runs", type=int, default=30)
    p.add_argument("--no-sensitivity", action="store_true")
    p.set_defaults(f=cmd_forecast)

    p = sub.add_parser("report", help="write the prediction report (report/report.html)")
    p.add_argument("project")
    llm_flags(p)
    p.set_defaults(f=cmd_report)

    p = sub.add_parser("ask", help="ask a question about the results")
    p.add_argument("project")
    p.add_argument("question")
    llm_flags(p)
    p.set_defaults(f=cmd_ask)

    p = sub.add_parser("chat", help="talk to someone from the simulation (no --agent: list people)")
    p.add_argument("project")
    p.add_argument("--agent", help="@handle")
    p.add_argument("--message", help="send one message and exit")
    llm_flags(p)
    p.set_defaults(f=cmd_chat)

    p = sub.add_parser("interview", help="ask the same question to a sample of people")
    p.add_argument("project")
    p.add_argument("question")
    p.add_argument("--segment")
    p.add_argument("-n", type=int, default=8)
    llm_flags(p)
    p.set_defaults(f=cmd_interview)

    p = sub.add_parser("inject", help="add news (or a post with --account) at the next round")
    p.add_argument("project")
    p.add_argument("text")
    p.add_argument("--account")
    p.add_argument("--platform")
    p.add_argument("--round", type=int, help="0-based round (default: next)")
    p.add_argument("--shift", nargs="+", help='news effect, e.g. "Daniel Okafor=-0.15" or stance=-0.1')
    p.set_defaults(f=cmd_inject)

    p = sub.add_parser("fork", help="copy a study's setup into a new project to try a variation")
    p.add_argument("project")
    p.add_argument("new")
    p.add_argument("--title")
    p.set_defaults(f=cmd_fork)

    p = sub.add_parser("compare", help="compare results of two or more projects")
    p.add_argument("projects", nargs="+")
    p.set_defaults(f=cmd_compare)

    p = sub.add_parser("status", help="summary of a run")
    p.add_argument("project")
    p.set_defaults(f=cmd_status)

    p = sub.add_parser("feed", help="read what agents posted")
    p.add_argument("project")
    from .platforms import REGISTRY
    p.add_argument("--platform", choices=list(REGISTRY))
    p.add_argument("--space")
    p.add_argument("--last", type=int, default=30)
    p.set_defaults(f=cmd_feed)

    args = ap.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main())

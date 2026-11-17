"""The upload -> graph -> setup pipeline, shared by the command line and the web app."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import hardware, scenario as scenario_mod
from .llm import LLMConfig, make_backend
from .settings import safe_study_llm

SCENARIO_FILE = "scenario.yaml"


class Stopped(Exception):
    """Raised when the user asked to stop a running job."""


@dataclass
class CreateOptions:
    fast: bool = False                 # graph without the model
    personas: bool = True              # write an individual persona per LLM voice
    llm_agents: int | None = None      # None = fit `hours` on this machine
    crowd: int | None = None
    hours: float = 12.0
    seed: int = 42
    llm: dict | None = None            # simulation model: backend/model/url/parallel overrides
    llm_build: dict | None = None      # model for graph, people and report (default: same as llm)
    entity_agents: int = 20            # named agents made from people/organisations in the documents


def public_cfg(d: dict | None) -> dict:
    """The model choice as stored in scenario.yaml: never a key, no cloud URLs."""
    d = {k: v for k, v in (d or {}).items() if v not in (None, "")}
    out = {k: d[k] for k in ("backend", "model", "parallel") if k in d}
    if d.get("url") and d.get("backend", "ollama") not in ("claude", "chatgpt"):
        out["url"] = d["url"]
    return out


def build_llm(project: Path, sc=None, mock: bool = False):
    """Model for graph, people, report, chat and interviews: llm_build, else the simulation model."""
    if mock:
        return make_llm(project, {"backend": "mock"})[1]
    if sc is None:
        sc = scenario_mod.load(Path(project) / SCENARIO_FILE)
    return make_llm(project, public_cfg(sc.llm_build or sc.llm))[1]


def make_llm(project: Path, overrides: dict | None = None):
    cfg = LLMConfig.from_dict({"backend": "ollama", "model": hardware.detect().model,
                               **{k: v for k, v in (overrides or {}).items() if v not in (None, "")}})
    return cfg, make_backend(cfg, cache_path=Path(project) / "llm_cache.db")


CLOUD_PEOPLE = 100        # default AI people when the simulation runs on Claude or ChatGPT


def size_population(rounds: int, hours: float, llm_agents=None, crowd=None,
                    cloud: bool = False) -> tuple[int, int]:
    """Every person is an AI agent (as in MiroFish). Locally the number fits the time budget
    on this machine; a crowd of rule-based agents is only added if asked for explicitly."""
    prof = hardware.detect()
    voices = llm_agents
    if voices is None and cloud:
        voices = CLOUD_PEOPLE
    if voices is None:
        voices = 10
        while (voices < prof.llm_agents and
               prof.estimate_hours(int((voices + 10) * rounds * 0.25)) <= hours):
            voices += 10
    return int(voices), int(crowd or 0)


def create_project(project: str | Path, files: list[str | Path], goal: str,
                   opts: CreateOptions | None = None,
                   say: Callable[[str], None] = print,
                   should_stop: Callable[[], bool] = lambda: False) -> dict:
    """Read documents, build the graph, draft scenario.yaml. Returns a short summary."""
    from .graph import GRAPH_FILE, GraphStore
    from .graph import build as gbuild, draft as gdraft, ingest as gingest, view as gview

    opts = opts or CreateOptions()
    proj = Path(project)
    proj.mkdir(parents=True, exist_ok=True)
    goal = goal.strip()
    if not goal:
        raise ValueError("Describe what you want to predict.")
    cfg, llm = make_llm(proj, opts.llm_build or opts.llm)
    ok, msg = llm.status()
    if not ok:
        raise RuntimeError(msg)
    (proj / "prompt.txt").write_text(goal + "\n", encoding="utf-8")
    gs = GraphStore(proj / GRAPH_FILE)
    try:
        gs.set_meta("goal", goal)
        say("1/4 Reading documents")
        for r in gingest.ingest(gs, proj, files):
            say(f"    {r['file']}: " + ("already added" if r["skipped"] else f"{r['chunks']} chunks"))

        say("2/4 Building the knowledge graph" + (" (fast, no model)" if opts.fast else ""))
        t0 = time.time()

        def gprog(p):
            if should_stop():
                raise Stopped()
            eta = (time.time() - t0) / p["chunk"] * (p["of"] - p["chunk"])
            say(f"    chunk {p['chunk']}/{p['of']}: {p['entities']} entities, "
                f"{p['relations']} relations  (about {eta / 60:.0f} min left)")

        st = gbuild.build(gs, None if opts.fast else llm, goal, gprog)
        gbuild.export(gs, proj)
        gview.write(gs, proj / "graph.html", title=goal[:60])
        say(f"    {st['nodes']} entities, {st['edges']} relations")

        if should_stop():
            raise Stopped()
        say("3/4 Drafting the simulation")
        days_guess = 7
        cloud = (opts.llm or {}).get("backend") in ("claude", "chatgpt")
        voices, crowd = size_population(days_guess * 6, opts.hours, opts.llm_agents, opts.crowd, cloud)
        sim = public_cfg(opts.llm) or {"backend": "ollama", "model": cfg.model if cfg.backend == "ollama"
                                        else hardware.detect().model}
        keep = safe_study_llm(sim)

        def dprog(m):
            if should_stop():
                raise Stopped()
            say(f"    {m}")

        sc = gdraft.draft(gs, llm, goal, llm_agents=voices, crowd_agents=crowd, llm_cfg=keep,
                          rich_personas=opts.personas, seed=opts.seed, progress=dprog,
                          entity_limit=opts.entity_agents)
        if sc["rounds"] != days_guess * 6 and opts.llm_agents is None:
            sc["population"]["llm_agents"] = min(
                sc["population"]["llm_agents"], size_population(sc["rounds"], opts.hours, None, crowd, cloud)[0])
        if opts.llm_build and public_cfg(opts.llm_build) != sim:
            sc["llm_build"] = public_cfg(opts.llm_build)
        n_docs = gs.rows("SELECT COUNT(*) FROM documents")[0][0]
        (proj / SCENARIO_FILE).write_text(gdraft.to_yaml(sc, goal, n_docs), encoding="utf-8")
    finally:
        gs.close()
        if hasattr(llm, "close"):
            llm.close()
    scenario_mod.load(proj / SCENARIO_FILE)
    summary = {"segments": len(sc["segments"]), "accounts": len(sc["accounts"]),
               "spaces": sum(len(v) for v in sc["spaces"].values()), "events": len(sc["events"]),
               "conversions": len(sc["conversions"]), "voices": len(sc.get("voices", [])),
               "nodes": st["nodes"], "edges": st["edges"]}
    say("4/4 Ready: " + ", ".join(f"{v} {k}" for k, v in summary.items()))
    return summary

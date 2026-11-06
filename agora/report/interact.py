"""Stage 5 - interaction: talk to anyone in the simulated world, interview a group, ask
the report agent questions, add events while a run is going, fork and compare studies."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np

from .. import scenario as scenario_mod
from ..llm import LLMBackend, LLMError, parse_json
from ..platforms import REGISTRY
from ..sim.llm_agent import stance_words
from .analysis import Analysis, nice, pct
from .evidence import PostIndex
from .writer import _CITE, check


def _db(project: Path, write: bool = False) -> sqlite3.Connection:
    path = Path(project) / "agora.db"
    if not path.exists():
        raise FileNotFoundError("This project has not been run yet.")
    if write:
        db = sqlite3.connect(str(path), timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        return db
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=15)


# ------------------------------------------------------------------ people
def people(project: str | Path, segment: str = "", query: str = "", limit: int = 200) -> list[dict]:
    """LLM voices and named accounts (the agents who can be interviewed)."""
    db = _db(Path(project))
    try:
        rows = db.execute(
            "SELECT a.id, a.handle, a.name, a.kind, a.segment, a.persona, a.initial_stance, s.stance, "
            " (SELECT COUNT(*) FROM posts p WHERE p.author = a.id AND p.kind IN ('post','reply')), "
            " (SELECT group_concat(name, ',') FROM conversions c WHERE c.agent = a.id) "
            "FROM agents a JOIN agent_state s ON s.id = a.id WHERE a.kind IN ('llm','account') "
            "ORDER BY a.kind = 'account' DESC, a.id").fetchall()
    finally:
        db.close()
    out = []
    for aid, h, n, k, g, persona, s0, s1, nposts, convs in rows:
        if segment and g != segment:
            continue
        if query and query.lower() not in f"{n} {h} {persona}".lower():
            continue
        out.append({"id": aid, "handle": h, "name": n, "kind": k, "segment": g, "persona": persona,
                    "stance_start": round(s0, 3), "stance": round(s1, 3), "posts": nposts,
                    "actions": (convs or "").split(",") if convs else []})
    return out[:limit]


def profile(project: str | Path, handle: str) -> dict:
    db = _db(Path(project))
    try:
        row = db.execute("SELECT a.id, a.handle, a.name, a.kind, a.segment, a.persona, a.platforms, "
                         "a.initial_stance, s.stance, s.memory, a.attrs FROM agents a JOIN agent_state s "
                         "ON s.id = a.id WHERE a.handle = ?", (handle,)).fetchone()
        if row is None:
            raise KeyError(f"No one called @{handle}")
        aid = row[0]
        posts = db.execute("SELECT id, round, platform, space, kind, text, stance FROM posts WHERE author = ? "
                           "AND kind IN ('post','reply') ORDER BY id DESC LIMIT 30", (aid,)).fetchall()
        thoughts = db.execute("SELECT round, text FROM thoughts WHERE agent = ? ORDER BY round DESC LIMIT 15",
                              (aid,)).fetchall()
        convs = db.execute("SELECT name, round FROM conversions WHERE agent = ?", (aid,)).fetchall()
        votes = db.execute("SELECT name, vote, reason FROM polls WHERE agent = ?", (aid,)).fetchall()
        traj = db.execute("SELECT round, stance FROM opinions WHERE agent = ? ORDER BY round", (aid,)).fetchall()
        chats = db.execute("SELECT role, text FROM chats WHERE thread = ? ORDER BY id", (f"agent:{handle}",)).fetchall()
    finally:
        db.close()
    return {"id": aid, "handle": row[1], "name": row[2], "kind": row[3], "segment": row[4], "persona": row[5],
            "platforms": json.loads(row[6]), "stance_start": row[7], "stance": row[8],
            "memory": json.loads(row[9]), "attrs": json.loads(row[10]),
            "posts": [{"id": p[0], "round": p[1], "platform": p[2], "space": p[3], "kind": p[4], "text": p[5],
                       "stance": p[6]} for p in posts],
            "thoughts": [{"round": r, "text": t} for r, t in thoughts],
            "actions": [{"name": n, "round": r} for n, r in convs],
            "votes": [{"poll": n, "vote": "yes" if v else "no", "reason": why} for n, v, why in votes],
            "trajectory": traj, "chat": [{"role": r, "text": t} for r, t in chats]}


def _save_chat(project: Path, thread: str, turns: list[tuple[str, str]]) -> None:
    db = _db(project, write=True)
    try:
        with db:
            db.executemany("INSERT INTO chats (thread, role, text) VALUES (?,?,?)",
                           [(thread, r, t) for r, t in turns])
    finally:
        db.close()


def _agent_messages(sc, p: dict, question: str, history: list[dict], brief: bool = False) -> list[dict]:
    plats = ", ".join(REGISTRY[x].label for x in p["platforms"] if x in REGISTRY)
    system = (f"You are {p['name']}. {p['persona']}\nYou took part in what happened below and are now "
              "being asked about it by a researcher. Answer as yourself, in the first person, honestly "
              "and consistently with what you said and did. Use plain everyday English. Never say you are "
              "an AI or a simulation. " + ("Answer in 1-3 sentences." if brief else "Keep answers to 2-5 sentences."))
    posts = "\n".join(f"- on {REGISTRY[x['platform']].label}{' in ' + x['space'] if x['space'] else ''}: "
                      f"\"{x['text'][:200]}\"" for x in p["posts"][:8])
    ctx = (f"Situation:\n{sc.context.strip()}\n\nYou use: {plats}.\n"
           f"Your feeling about {sc.topic} now: {stance_words(p['stance'])} "
           f"(at the start you were {stance_words(p['stance_start'])}).\n"
           + (f"Things you did: {', '.join(nice(a['name']) for a in p['actions'])}.\n" if p["actions"] else
              "You did not take any of the actions on offer.\n")
           + ("".join(f"You voted {v['vote']} on {nice(v['poll'])}: {v['reason']}\n" for v in p["votes"]))
           + (f"Some things you posted:\n{posts}\n" if posts else "You did not post anything.\n")
           + ("Your recent memory:\n" + "\n".join(f"- {m}" for m in p["memory"][-10:]) if p["memory"] else ""))
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": ctx + "\n\n(The interview starts now.)"},
            {"role": "assistant", "content": "Okay, ask me."}]
    for h in history[-10:]:
        msgs.append({"role": "user" if h["role"] == "user" else "assistant", "content": h["text"]})
    msgs.append({"role": "user", "content": question})
    return msgs


def _mock_reply(p: dict) -> str:
    s = p["stance"]
    return ("Honestly I liked it, and I'd tell my neighbours to try it." if s > 0.25 else
            "I'm not convinced yet; I'd want to hear from people I trust first." if s < -0.25 else
            "I haven't made up my mind. It depends on what others in the building say.")


def chat(project: str | Path, llm: LLMBackend, handle: str, message: str) -> dict:
    project = Path(project)
    sc = scenario_mod.load(project / "scenario.yaml")
    p = profile(project, handle)
    msgs = _agent_messages(sc, p, message, p["chat"])
    try:
        reply = llm.generate(msgs, max_tokens=300, temperature=0.7, meta={"default_text": _mock_reply(p)}).strip()
    except LLMError as e:
        raise RuntimeError(f"The model is not available: {e}") from e
    reply = reply or "…"
    _save_chat(project, f"agent:{handle}", [("user", message), ("agent", reply)])
    return {"reply": reply, "handle": handle, "name": p["name"]}


def interview(project: str | Path, llm: LLMBackend, question: str, segment: str = "", n: int = 8,
              seed: int = 7, say=lambda m: None) -> dict:
    """Ask the same question to a sample of the AI voices (optionally one group)."""
    project = Path(project)
    sc = scenario_mod.load(project / "scenario.yaml")
    pool = [x for x in people(project, segment=segment, limit=10_000) if x["kind"] == "llm"]
    if not pool:
        raise ValueError("No AI voices to interview" + (f" in {nice(segment)}" if segment else "") + ".")
    rng = np.random.default_rng(seed)
    pick = sorted(rng.choice(len(pool), size=min(n, len(pool)), replace=False).tolist())
    answers = []
    for k, i in enumerate(pick, 1):
        say(f"Asking {k}/{len(pick)}: {pool[i]['name']}")
        p = profile(project, pool[i]["handle"])
        msgs = _agent_messages(sc, p, question + '\nReply with JSON only: {"answer": "...", '
                               '"agree": <number from -1 (strongly no) to 1 (strongly yes)>}', [], brief=True)
        try:
            raw = llm.generate(msgs, max_tokens=220, temperature=0.6, json_mode=True, seed=seed + i,
                               meta={"task": "json", "default": {"answer": _mock_reply(p), "agree": round(p["stance"], 2)}})
        except LLMError as e:
            raise RuntimeError(f"The model is not available: {e}") from e
        d = parse_json(raw)
        try:
            agree = max(-1.0, min(1.0, float(d.get("agree", p["stance"]))))
        except (TypeError, ValueError):
            agree = p["stance"]
        answers.append({"handle": p["handle"], "name": p["name"], "segment": p["segment"],
                        "answer": str(d.get("answer") or raw).strip()[:600], "agree": round(agree, 2),
                        "stance": round(p["stance"], 2)})
    vals = [a["agree"] for a in answers]
    tally = {"yes": sum(v > 0.2 for v in vals), "unsure": sum(-0.2 <= v <= 0.2 for v in vals),
             "no": sum(v < -0.2 for v in vals), "average": round(sum(vals) / len(vals), 2)}
    result = {"question": question, "segment": segment, "answers": answers, "tally": tally}
    _save_chat(project, "interviews", [("question", json.dumps({"q": question, "segment": segment})),
                                       ("result", json.dumps(result))])
    return result


def ask(project: str | Path, llm: LLMBackend, question: str) -> dict:
    """Ask the report agent: answers from the computed results and real posts, with citations."""
    project = Path(project)
    an = Analysis(project)
    try:
        a = an.everything()
    finally:
        an.close()
    posts = PostIndex(project)
    evidence = posts.search(question, k=8)
    rep = project / "report" / "report.json"
    summary = ""
    if rep.exists():
        r = json.loads(rep.read_text(encoding="utf-8"))
        summary = "\n".join(f"{s['title']}: {s['text']}" for s in r["sections"][:3])
    actions = "Actions: " + "; ".join(f"{nice(f['name'])} {f['count']} of {f['eligible']} ({pct(f['rate'])})"
                                      + (" BLOCKED" if f["blocked_by"] else "") for f in a["funnel"])
    facts = "\n".join([
        f"Question studied: {' '.join(a['scenario']['question'].split())}",
        actions,
        "Opinion by group (start -> end): " + "; ".join(f"{nice(g)} {d.get('start', 0):+.2f} -> {d['end']:+.2f}"
                                                        for g, d in a["opinion"]["segments"].items()),
        f"Overall: {pct(a['opinion']['start'].get('for', 0))} -> {pct(a['opinion']['end'].get('for', 0))} in favour",
        "Decisions: " + "; ".join(f"{nice(d['name'])} {'approved' if d['passed'] else 'rejected'} {d['yes']}-{d['no']}"
                                  for d in a["decisions"]),
        "Most influential: " + ", ".join(f"{i['name']} ({nice(i['segment'])})" for i in a["influencers"][:5])])
    msgs = [{"role": "system", "content": "You answer questions about a social simulation's results. Use only the "
             "facts and posts given; if they do not answer the question, say so. Cite posts like [p123]. "
             "Be concise: 2-6 sentences."},
            {"role": "user", "content": f"Facts:\n{facts}\n\n{('Report so far:' + chr(10) + summary + chr(10)) if summary else ''}"
             f"Posts found for this question:\n" + ("\n".join(evidence) or "(none)") + f"\n\nQuestion: {question}"}]
    fallback = actions + ". " + (" ".join(evidence[:2]) if evidence else "")
    try:
        raw = llm.generate(msgs, max_tokens=400, temperature=0.2, meta={"default_text": fallback})
    except LLMError as e:
        raise RuntimeError(f"The model is not available: {e}") from e
    answer = check(raw, facts + "\n" + "\n".join(evidence) + "\n" + summary, set(posts.by_id)) or \
        "The results don't contain enough to answer that."
    cited = sorted({int(x) for x in _CITE.findall(answer)})
    _save_chat(project, "report", [("user", question), ("agent", answer)])
    return {"answer": answer, "quotes": {pid: posts.line(pid) for pid in cited}}


def history(project: str | Path, thread: str) -> list[dict]:
    db = _db(Path(project))
    try:
        return [{"role": r, "text": t} for r, t in
                db.execute("SELECT role, text FROM chats WHERE thread = ? ORDER BY id", (thread,))]
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


# ------------------------------------------------------------------ events during a run
def inject(project: str | Path, event: dict, at_round: int | None = None) -> dict:
    """Add a news item or an official post at the next round (or a given future round)."""
    project = Path(project)
    sc = scenario_mod.load(project / "scenario.yaml")
    db = _db(project, write=True)
    try:
        done = db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
        r = done if at_round is None else int(at_round)
        if r < done:
            raise ValueError(f"Round {r + 1} has already happened.")
        if r >= sc.rounds:
            raise ValueError("The simulation has no rounds left. Fork the study to try a longer run.")
        t = str(event.get("type", "news"))
        text = str(event.get("text", "")).strip()
        if not text:
            raise ValueError("Write what happens.")
        ev = {"round": r, "type": t, "text": text[:1500]}
        shift = event.get("shift") or {}
        if shift:
            valid = set(sc.choice.options) if sc.choice else set()
            clean = {}
            for k, v in shift.items():
                if k != "stance" and k not in valid:
                    raise ValueError(f"Unknown option '{k}' in shift.")
                clean[k] = max(-1.0, min(1.0, float(v)))
            if t != "news":
                raise ValueError("Only news can shift opinions directly.")
            ev["shift"] = clean
        if t == "post":
            acc = event.get("account")
            accounts = {a.id: a for a in sc.accounts}
            if acc not in accounts:
                raise ValueError("Choose which account posts it.")
            plat = event.get("platform") or accounts[acc].platforms[0]
            if plat not in REGISTRY:
                raise ValueError(f"Unknown app '{plat}'.")
            ev.update(account=acc, platform=plat, spaces=list(event.get("spaces") or []))
        elif t != "news":
            raise ValueError("You can add news or a post.")
        with db:
            db.execute("INSERT INTO injected (round, event) VALUES (?, ?)", (r, json.dumps(ev)))
    finally:
        db.close()
    return {"ok": True, "round": r}


def injected(project: str | Path) -> list[dict]:
    try:
        db = _db(Path(project))
    except FileNotFoundError:
        return []
    try:
        return [{"round": r, **json.loads(e)} for r, e in
                db.execute("SELECT round, event FROM injected ORDER BY id")]
    except sqlite3.OperationalError:       # run database still being created
        return []
    finally:
        db.close()


# ------------------------------------------------------------------ fork and compare
FORK_FILES = ("scenario.yaml", "prompt.txt", "graph.db", "graph.html", "graph.json", "graph.graphml")


def fork(project: str | Path, new: str | Path, title: str = "") -> Path:
    src, dst = Path(project), Path(new)
    if dst.exists():
        raise FileExistsError(f"{dst} already exists")
    dst.mkdir(parents=True)
    for f in FORK_FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    if (src / "sources").is_dir():
        shutil.copytree(src / "sources", dst / "sources")
    old = {}
    if (src / "agora.json").exists():
        old = json.loads((src / "agora.json").read_text(encoding="utf-8"))
    (dst / "agora.json").write_text(json.dumps({"title": title or f"{old.get('title', src.name)} (variant)",
                                                "forked_from": src.name}), encoding="utf-8")
    return dst


def compare(projects: list[str | Path]) -> dict:
    cols = []
    for p in projects:
        p = Path(p)
        title = p.name
        if (p / "agora.json").exists():
            title = json.loads((p / "agora.json").read_text(encoding="utf-8")).get("title", p.name)
        try:
            an = Analysis(p)
            try:
                f, op, dec, ov = an.funnel(), an.opinion(), an.decisions(), an.overview()
            finally:
                an.close()
        except FileNotFoundError:
            cols.append({"id": p.name, "title": title, "run": False})
            continue
        cols.append({"id": p.name, "title": title, "run": True,
                     "rounds": f"{ov['rounds_done']}/{ov['rounds_total']}",
                     "actions": {x["name"]: {"count": x["count"], "rate": x["rate"], "eligible": x["eligible"],
                                             "blocked": bool(x["blocked_by"])} for x in f},
                     "opinion_end": op["end"].get("mean"), "for_end": op["end"].get("for"),
                     "against_end": op["end"].get("against"),
                     "segments": {g: d["end"] for g, d in op["segments"].items()},
                     "decisions": {d["name"]: d["passed"] for d in dec}, "posts": ov["posts"]})
    names = sorted({n for c in cols if c.get("run") for n in c["actions"]})
    segs = sorted({g for c in cols if c.get("run") for g in c["segments"]})
    decs = sorted({n for c in cols if c.get("run") for n in c["decisions"]})
    return {"columns": cols, "actions": names, "segments": segs, "decisions": decs}

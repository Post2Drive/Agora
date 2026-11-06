"""The report agent.

For each section it gets (1) the exact numbers from `analysis`, (2) real posts found by
searching what agents said, and writes a few paragraphs. Then the text is checked:
citations to posts that do not exist are removed, and any sentence containing a number
that is not in the facts it was given is dropped. Numbers in the tables are always
computed, never written by the model.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

from ..llm import LLMBackend, LLMError, parse_json
from .analysis import Analysis, label, money, nice, pct
from .evidence import PostIndex

SYSTEM = ("You are a careful research analyst writing one section of a prediction report about a "
          "social simulation. Use ONLY the numbers and quotes provided. Never invent numbers. "
          "When you use a quote or example, cite it exactly like [p123]. Plain, direct English, "
          "short paragraphs, no headings, no bullet lists, no preamble.")

_CITE = re.compile(r"\[p(\d+)\]")
_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(%|percent)?")


# ------------------------------------------------------------------ facts per section
def _segments(a: dict) -> str:
    return "\n".join(f"- {nice(g)}: opinion {d.get('start', 0):+.2f} -> {d['end']:+.2f} "
                     f"(change {d['change']:+.2f}), {d['agents']} people"
                     for g, d in a["opinion"]["segments"].items())


def _funnel(a: dict) -> str:
    lines = []
    for f in a["funnel"]:
        extra = f" BLOCKED because decision '{nice(f['blocked_by'])}' was rejected" if f["blocked_by"] else ""
        lines.append(f"- {nice(f['name'])} ({f['label']}): {f['count']} of {f['eligible']} eligible "
                     f"= {pct(f['rate'])}{extra}")
        for g, d in f["by_segment"].items():
            if d["eligible"]:
                lines.append(f"    - {nice(g)}: {d['count']} of {d['eligible']} = {pct(d['rate'])}")
    return "\n".join(lines)


def _dist(d: dict) -> str:
    return (f"{pct(d.get('for', 0))} for, {pct(d.get('undecided', 0))} undecided, "
            f"{pct(d.get('against', 0))} against")


def _decisions(a: dict) -> str:
    out = []
    for d in a["decisions"]:
        out.append(f"- {nice(d['name'])}: {'APPROVED' if d['passed'] else 'REJECTED'} "
                   f"({d['yes']} yes, {d['no']} no)")
        out += [f"    - {v['name']} voted {v['vote']}: {v['reason']}" for v in d["votes"][:6] if v["reason"]]
    return "\n".join(out) or "No formal decisions in this scenario."


def _themes(a: dict) -> str:
    t = a["themes"]
    pos = ", ".join(f"'{x['phrase']}' ({x['posts']} posts)" for x in t.get("positive", []))
    neg = ", ".join(f"'{x['phrase']}' ({x['posts']} posts)" for x in t.get("negative", []))
    return (f"Positive posts: {t.get('positive_posts', 0)}; common phrases: {pos or 'none'}\n"
            f"Negative posts: {t.get('negative_posts', 0)}; common phrases: {neg or 'none'}")


def _drivers(a: dict) -> str:
    inf = "\n".join(f"- {i['name']} (@{i['handle']}, {nice(i['segment'])}, opinion {i['stance']:+.2f}): "
                    f"{i['posts']} posts, {i['engagement']} reactions, shared {i['shared']} times"
                    for i in a["influencers"][:6])
    plats = ", ".join(f"{label(p)} {n}" for p, n in a["overview"]["posts_by_platform"].items())
    tone = ", ".join(f"{label(p)} {v:+.2f}" for p, v in a["opinion"]["post_tone_by_platform"].items())
    groups = ", ".join(f"{g['space']} ({g['messages']})" for g in a["spread"]["busiest_groups"][:6])
    return (f"Most influential voices:\n{inf}\nPosts per app: {plats}\nAverage tone of posts per app "
            f"(-1..+1): {tone}\nBusiest groups: {groups}")


def _econ(a: dict) -> str:
    e = a["economics"]
    if not e:
        return ""
    c = e["currency"]
    per = ", ".join(f"{money(v, c)} per {nice(k)}" for k, v in e["cost_per"].items())
    return (f"Money: total cost {money(e['total_cost'], c)}, value {money(e['total_value'], c)}, "
            f"net {money(e['net'], c)}; {per}")


def _base(a: dict) -> str:
    o = a["overview"]
    return (f"Question: {a['scenario']['question']}\n"
            f"Simulated {o['days']} days ({o['rounds_done']} of {o['rounds_total']} rounds) with "
            f"{o['llm_voices']} AI voices who write, {o['crowd']} crowd agents who react, and "
            f"{o['accounts']} named accounts. {o['posts']} posts and messages, {o['shares']} shares/forwards.")


SECTIONS = [
    ("summary", "Summary",
     "Answer the prediction question directly in one paragraph of 4-6 sentences: the most likely "
     "outcome, the key numbers, and how confident to be.",
     lambda a: "\n".join([_base(a), "Actions:", _funnel(a), "Decisions:", _decisions(a),
                          f"Opinion overall: start {_dist(a['opinion']['start'])}; end {_dist(a['opinion']['end'])}",
                          _econ(a)]),
     "overall reaction"),
    ("opinion", "How opinion moved",
     "Explain how opinion changed overall and in each group, which groups moved most and why, "
     "using 1-2 quotes as examples.",
     lambda a: "\n".join([f"Overall: start {_dist(a['opinion']['start'])}; end {_dist(a['opinion']['end'])}; "
                          f"average {a['opinion']['start'].get('mean', 0):+.2f} -> {a['opinion']['end'].get('mean', 0):+.2f}",
                          "By group:", _segments(a)]),
     "changed my mind convinced trust worried"),
    ("voices", "What people said",
     "Describe what supporters said and what critics or doubters said, quoting 2-4 real posts with "
     "their [p123] citations. Name concerns that keep coming up.",
     lambda a: _themes(a) + "\nMost-engaged supportive posts:\n" +
     "\n".join(f"- [p{p['id']}] {p['author']}: \"{p['text'][:200]}\"" for p in a["top_posts"]["positive"][:4]) +
     "\nMost-engaged critical posts:\n" +
     "\n".join(f"- [p{p['id']}] {p['author']}: \"{p['text'][:200]}\"" for p in a["top_posts"]["negative"][:4]),
     "worried catch doubt concern price trust safe free"),
    ("drivers", "Who and what drove it",
     "Explain which people, apps and groups drove the conversation and in which direction.",
     _drivers, "group forwarded shared everyone"),
    ("decisions", "Decisions",
     "Explain each decision, how members voted and the reasons they gave, and what it changed.",
     _decisions, "approve committee association decision"),
    ("risks", "How far to trust this",
     "Explain the main uncertainties: which inputs are assumptions, how many people actually wrote with "
     "the model, and what real data would make the prediction sharper. Be honest and specific.",
     lambda a: "\n".join([_base(a),
                          "Opinion starting points, stubbornness and the action likelihoods in the setup are "
                          "assumptions unless calibrated with real data.",
                          f"Only {a['overview']['llm_voices']} people wrote with the model; the other "
                          f"{a['overview']['crowd']} reacted using opinion-dynamics rules.",
                          f"Model calls made: {a['overview']['llm_calls']}."]),
     ""),
    ("recommendations", "What to do next",
     "Give 3-5 concrete recommendations that follow from these results (what to change, test or "
     "measure), each in one or two sentences, as a single paragraph.",
     lambda a: "\n".join([_funnel(a), _segments(a), _themes(a), _econ(a)]),
     "should would better if only wish"),
]


# ------------------------------------------------------------------ checking
def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM.finditer(text):
        n = m.group(1).replace(",", "")
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def check(text: str, facts: str, known_posts: set[int]) -> str:
    """Drop invented citations, and sentences with numbers that are not in the facts."""
    text = _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in known_posts else "", text)
    allowed = {str(i) for i in range(0, 11)}
    for n in _numbers(facts):
        allowed.add(n)
        try:                                   # "28.1" in the facts also allows "28"
            x = float(n)
            allowed |= {str(round(x)), str(int(x)), f"{x:.1f}".rstrip("0").rstrip(".")}
        except ValueError:
            pass
    keep = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        nums = _numbers(_CITE.sub("", sent))
        if nums - allowed:
            continue
        keep.append(sent)
    out = " ".join(keep)
    out = re.sub(r"\s+([.,;:])", r"\1", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def _fallback(key: str, a: dict) -> str:
    """No-model text: plain statements of the computed results."""
    o, op = a["overview"], a["opinion"]
    if key == "summary":
        acts = "; ".join(f"{nice(f['name'])}: {f['count']} of {f['eligible']} eligible ({pct(f['rate'])})"
                         + (f", blocked by {nice(f['blocked_by'])}" if f["blocked_by"] else "")
                         for f in a["funnel"])
        return (f"Over {o['days']} simulated days, {acts or 'no actions were defined'}. "
                f"Overall opinion moved from {op['start'].get('mean', 0):+.2f} to {op['end'].get('mean', 0):+.2f} "
                f"(share in favour {pct(op['start'].get('for', 0))} to {pct(op['end'].get('for', 0))}).")
    if key == "opinion":
        return " ".join(f"{nice(g)} moved from {d.get('start', 0):+.2f} to {d['end']:+.2f}."
                        for g, d in op["segments"].items())
    if key == "voices":
        t = a["themes"]
        return (f"{t.get('positive_posts', 0)} posts were supportive and {t.get('negative_posts', 0)} critical. "
                + " ".join(f"[p{p['id']}]" for p in a["top_posts"]["positive"][:2] + a["top_posts"]["negative"][:2]))
    if key == "drivers":
        top = a["influencers"][:3]
        return "The most influential voices were " + ", ".join(f"{i['name']} ({nice(i['segment'])})" for i in top) + "." if top else ""
    if key == "decisions":
        return " ".join(f"{nice(d['name'])} was {'approved' if d['passed'] else 'rejected'} "
                        f"({d['yes']} yes, {d['no']} no)." for d in a["decisions"])
    if key == "risks":
        return (f"Only {o['llm_voices']} people wrote with the model; {o['crowd']} reacted by rules. "
                "Starting opinions and action likelihoods are assumptions until calibrated with real data.")
    return "Compare this run with a variation of the setup, and collect real results to calibrate it."


# ------------------------------------------------------------------ main
# ------------------------------------------------------------------ the agent
TOOLS_HELP = """Tools (call one at a time with JSON):
- {"tool": "search_posts", "query": "..."}      find what people actually said
- {"tool": "search_memory", "query": "..."}     search the documents' knowledge graph and the record of what happened
- {"tool": "insight", "query": "..."}            break a question into sub-questions and search each
- {"tool": "stats", "name": "funnel|opinion|decisions|drivers|themes|economics"}  exact numbers
- {"tool": "interview", "question": "...", "segment": "<group or empty>"}  ask a few simulated people (max once)
When you have enough, reply {"write": "<the section text>"}."""

STAT_FNS = {"funnel": _funnel, "opinion": _segments, "decisions": _decisions, "drivers": _drivers,
            "themes": _themes, "economics": _econ}
LIBRARY = {k: (title, instr, fn, q) for k, title, instr, fn, q in SECTIONS}


class Toolbox:
    def __init__(self, project: Path, a: dict, posts: PostIndex, llm, log: list):
        self.project, self.a, self.posts, self.llm, self.log = project, a, posts, llm, log
        self.interviews = 0
        self._facts = None

    def _graph(self):
        if self._facts is None:
            from ..graph import GRAPH_FILE, GraphStore
            from ..graph.retrieve import FactIndex
            facts = []
            if (self.project / GRAPH_FILE).exists():
                gs = GraphStore(self.project / GRAPH_FILE)
                facts = FactIndex.from_graph(gs).facts
                gs.close()
            from ..sim.memory import WorldMemory
            from ..sim.world import World
            from ..store import Store
            from .. import scenario as scenario_mod
            st = Store(self.project / "agora.db")
            try:
                sc = scenario_mod.load(self.project / "scenario.yaml")
                mem = WorldMemory.load(sc, World.load(st), st)
                facts += [t for _, _, t in mem.episodes]
            finally:
                st.close()
            from ..graph.retrieve import FactIndex as FI
            self._facts = FI(facts)
        return self._facts

    def call(self, d: dict, section: str) -> str:
        tool = str(d.get("tool", "")).strip()
        q = str(d.get("query") or d.get("question") or "")[:300]
        if tool == "search_posts":
            res = "\n".join(self.posts.search(q, k=6)) or "(no matching posts)"
        elif tool == "search_memory":
            res = "\n".join(f"- {x}" for x in self._graph().search(q, k=6)) or "(nothing found)"
        elif tool == "insight":
            subs = [q]
            if self.llm is not None:
                try:
                    j = self.llm.generate_json([{"role": "user", "content":
                        f"Split this research question into 3 short search queries.\nQuestion: {q}\n"
                        'Reply with JSON only: {"queries": ["...", "...", "..."]}'}],
                        max_tokens=150, temperature=0.2, seed=7,
                        meta={"task": "json", "default": {"queries": [q]}})
                    subs = [str(x) for x in (j.get("queries") or [q])][:3] or [q]
                except LLMError:
                    pass
            parts = []
            for sq in subs:
                hits = self.posts.search(sq, k=3) + [f"- {x}" for x in self._graph().search(sq, k=2)]
                parts.append(f"Q: {sq}\n" + ("\n".join(hits) or "(nothing)"))
            res = "\n".join(parts)
        elif tool == "stats":
            fn = STAT_FNS.get(str(d.get("name", "")).strip().lower())
            res = fn(self.a) if fn else "Unknown stats name. Use funnel, opinion, decisions, drivers, themes or economics."
        elif tool == "interview":
            if self.interviews >= 1 or self.llm is None:
                res = "(interview budget used)"
            else:
                from .interact import interview
                self.interviews += 1
                seg = str(d.get("segment") or "")
                if seg not in self.a["scenario"]["segments"]:
                    seg = ""
                r = interview(self.project, self.llm, q or "What do you think about it?", segment=seg, n=4)
                t = r["tally"]
                res = (f"Asked {len(r['answers'])} people: {t['yes']} yes, {t['unsure']} unsure, {t['no']} no.\n"
                       + "\n".join(f"- {x['name']} ({x['segment'].replace('_', ' ')}): \"{x['answer'][:200]}\""
                                   for x in r["answers"]))
        else:
            res = "Unknown tool."
        self.log.append({"section": section, "tool": tool, "input": d, "result": res[:2000]})
        return res


def plan_outline(llm, a: dict) -> list[dict]:
    default = [{"key": k, "title": LIBRARY[k][0], "goal": LIBRARY[k][1]} for k in LIBRARY]
    if llm is None:
        return default
    brief = "\n".join([_base(a), "Actions:", _funnel(a), "Decisions:", _decisions(a)[:600]])
    try:
        d = llm.generate_json([{"role": "system", "content": SYSTEM},
                               {"role": "user", "content":
                                f"Plan a prediction report.\n{brief}\n\nStandard sections you can use: "
                                + ", ".join(f"{k} ({LIBRARY[k][0]})" for k in LIBRARY)
                                + "\nChoose 5-8 sections in a sensible order. Always include summary first and "
                                  "risks near the end. You may add up to 2 custom sections specific to this question.\n"
                                  'Reply with JSON only: {"sections": [{"key": "summary or custom", "title": "...", '
                                  '"goal": "what this section must answer"}]}'}],
                              max_tokens=500, temperature=0.2, seed=3,
                              meta={"task": "json", "default": {"sections": default}})
    except LLMError:
        return default
    out, seen = [], set()
    for x in d.get("sections") or []:
        if not isinstance(x, dict):
            continue
        key = str(x.get("key", "custom")).strip().lower()
        key = key if key in LIBRARY else "custom"
        title = str(x.get("title") or (LIBRARY[key][0] if key in LIBRARY else "")).strip()[:80]
        if not title or (key in seen and key != "custom"):
            continue
        seen.add(key)
        out.append({"key": key, "title": title,
                    "goal": str(x.get("goal") or (LIBRARY[key][1] if key in LIBRARY else ""))[:300]})
    if not out:
        return default
    if out[0]["key"] != "summary":
        out = [s for s in default if s["key"] == "summary"] + [s for s in out if s["key"] != "summary"]
    if "risks" not in seen:
        out.append(next(s for s in default if s["key"] == "risks"))
    return out[:9]


def _general_facts(a: dict) -> str:
    return "\n".join([_base(a), "Actions:", _funnel(a), "Opinion by group:", _segments(a), _themes(a), _econ(a)])


def write_section(llm, tb: Toolbox, a: dict, sec: dict, i: int, known: set[int], max_steps: int = 3) -> str:
    key = sec["key"]
    facts = LIBRARY[key][2](a) if key in LIBRARY else _general_facts(a)
    query = LIBRARY[key][3] if key in LIBRARY else sec["title"]
    notes = []
    if query:
        notes.append("Posts found for this section:\n" + "\n".join(tb.posts.search(f"{a['scenario']['topic']} {query}", k=5)))
    for step in range(max_steps):
        prompt = (f"Section {i}: {sec['title']}\nGoal: {sec['goal']}\n\nFacts (the only numbers you may use):\n{facts}\n\n"
                  + ("\n\n".join(notes) + "\n\n" if notes else "") + TOOLS_HELP
                  + f"\nYou have {max_steps - step} tool call(s) left.")
        default = ({"tool": "search_posts", "query": sec["title"]} if step == 0 else
                   {"write": _fallback(key, a) if key in LIBRARY else ""})
        try:
            raw = llm.generate([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                               max_tokens=600, temperature=0.3, seed=100 + i * 10 + step, json_mode=True,
                               meta={"task": "json", "default": default})
        except LLMError:
            break
        d = parse_json(raw)
        if d.get("write") or not d.get("tool"):
            # a model that ignores the JSON format and just writes prose: take the prose
            text = str(d.get("write") or d.get("text") or ("" if d else raw))
            evid = facts + "\n" + "\n".join(notes)
            return check(text, evid, known)
        notes.append(f"Tool {d.get('tool')} result:\n" + tb.call(d, sec["title"]))
    # out of steps: write with what we have
    try:
        raw = llm.generate([{"role": "system", "content": SYSTEM}, {"role": "user", "content":
                            f"Section: {sec['title']}\nGoal: {sec['goal']}\n\nFacts:\n{facts}\n\n"
                            + "\n\n".join(notes) + "\n\nNow write the section."}],
                           max_tokens=450, temperature=0.3, seed=100 + i,
                           meta={"default_text": _fallback(key, a) if key in LIBRARY else ""})
        return check(raw, facts + "\n" + "\n".join(notes), known)
    except LLMError:
        return ""


def write_report(project: str | Path, llm: LLMBackend | None,
                 say: Callable[[str], None] = lambda m: None,
                 should_stop: Callable[[], bool] = lambda: False) -> dict:
    project = Path(project)
    an = Analysis(project)
    try:
        a = an.everything()
    finally:
        an.close()
    posts = PostIndex(project)
    known = set(posts.by_id)
    log: list[dict] = []
    tb = Toolbox(project, a, posts, llm, log)
    say("Planning the report")
    outline = plan_outline(llm, a)
    sections = []
    for i, sec in enumerate(outline, 1):
        if should_stop():
            raise KeyboardInterrupt
        say(f"Researching and writing {i}/{len(outline)}: {sec['title']}")
        text = write_section(llm, tb, a, sec, i, known) if llm is not None else ""
        if len(text) < 40 and sec["key"] in LIBRARY:     # our own computed sentences
            text = _CITE.sub(lambda m: m.group(0) if int(m.group(1)) in known else "", _fallback(sec["key"], a))
        if len(text) < 20:
            continue
        sections.append({"key": sec["key"], "title": sec["title"], "text": text})
        for e in log:
            if e["section"] == sec["title"] and "said" not in e:
                say(f"  used {e['tool']}: {str(e['input'].get('query') or e['input'].get('name') or e['input'].get('question') or '')[:60]}")
                e["said"] = True
    cited = sorted({int(x) for s in sections for x in _CITE.findall(s["text"])})
    report = {"title": a["scenario"]["question"], "generated": time.strftime("%Y-%m-%d %H:%M"),
              "model": f"{llm.cfg.backend}:{llm.cfg.model}" if llm is not None else "none",
              "sections": sections, "analysis": a, "outline": outline,
              "research": [{k: v for k, v in e.items() if k != "said"} for e in log],
              "quotes": {pid: posts.line(pid) for pid in cited}}
    out = project / "report"
    out.mkdir(exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str),
                                     encoding="utf-8")
    from .render import to_html, to_markdown
    (out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    (out / "report.html").write_text(to_html(report), encoding="utf-8")
    say("Report saved: report/report.html and report/report.md")
    return report

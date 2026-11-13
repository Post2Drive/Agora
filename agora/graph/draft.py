"""Stage 2 - environment setup: turn the prediction prompt + knowledge graph into a
runnable scenario (segments, named accounts, groups, timeline, conversions, personas).

Small local models are unreliable at writing one big structured file, so drafting is
split into short, separate JSON questions. Every answer is cleaned and checked; anything
unusable falls back to a sensible default. The result is a normal scenario.yaml you
can read and edit before running.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Callable

from .. import scenario as scenario_mod
from ..llm import LLMBackend, LLMError
from ..llm.base import StepFailed, ask_json
from .store import GraphStore

from ..platforms import REGISTRY, is_spaced, resolve

PLATFORMS = tuple(REGISTRY)
SPACED = tuple(k for k in REGISTRY if is_spaced(k))
FEEDS = tuple(k for k in REGISTRY if not is_spaced(k))
PLATFORM_LIST = ", ".join(f'"{k}"' for k in REGISTRY)
ROUND_HOURS = 4


# ------------------------------------------------------------------ helpers
def slug(s: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")[:n] or "item"


def _num(v, lo, hi, default):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def _plats(v, default=("whatsapp", "instagram")) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,/;]+|\s+and\s+", v)
    out = []
    for p in v or []:
        k = resolve(p)
        if k and k not in out:
            out.append(k)
    return out or list(default)


def graph_brief(gs: GraphStore, max_nodes: int = 25, max_facts: int = 25) -> str:
    nodes = gs.rows("SELECT name, type, description FROM nodes ORDER BY mentions DESC LIMIT ?",
                    (max_nodes,))
    facts = gs.rows("SELECT DISTINCT fact FROM edges WHERE fact != '' ORDER BY id LIMIT ?",
                    (max_facts,))
    lines = ["Key entities:"] + [f"- {n} ({t}): {d[:160]}" for n, t, d in nodes]
    if facts:
        lines += ["Key facts:"] + [f"- {f[0][:200]}" for f in facts]
    return "\n".join(lines)


def doc_excerpt(gs: GraphStore, limit: int = 2500) -> str:
    text = "\n\n".join(t for (t,) in gs.rows("SELECT text FROM chunks ORDER BY id"))
    return text[:limit]


def _ask(llm: LLMBackend | None, prompt: str, default: dict, seed: int, max_tokens=900, *,
         step: str = "setup", check=None, tries: int = 3) -> dict:
    """One short JSON question. With a model: bad replies are retried, then StepFailed (nothing made up).
    Without a model (an explicit --fast build) the built-in default is used, by request."""
    if llm is None:
        return default
    return ask_json(llm, [{"role": "user", "content": prompt}], check or (lambda d: bool(d)),
                    step=step, tries=tries, max_tokens=max_tokens, temperature=0.3, seed=seed,
                    meta={"task": "json", "default": default})


def _ok_frame(d: dict) -> bool:
    return bool(str(d.get("topic") or "").strip()) and bool(str(d.get("question") or "").strip())


def _ok_segments(d: dict) -> bool:
    names = {slug(s["name"], 30) for s in (d.get("segments") or []) if isinstance(s, dict) and s.get("name")}
    return len(names) >= 2


def _ok_accounts(d: dict) -> bool:
    return isinstance(d.get("accounts"), list)


def _ok_places(d: dict) -> bool:
    return any(isinstance(a, dict) and a.get("name") for a in (d.get("actions") or []))


def _ok_events(d: dict) -> bool:
    return any(isinstance(e, dict) and (e.get("text") or e.get("question")) for e in (d.get("events") or []))


def _ok_profile(d: dict) -> bool:
    return bool(str(d.get("persona") or "").strip())


def _ok_persona(d: dict) -> bool:
    return bool(str(d.get("name") or "").strip()) and len(str(d.get("persona") or "").strip()) >= 20


HEAD = """You are setting up a social simulation that predicts how real people will react.
Prediction goal: {goal}

What the documents say:
{brief}

Document excerpt:
\"\"\"{excerpt}\"\"\"
"""

FRAME = HEAD + """
Write the simulation framing. Use only facts from the documents in "context".
Reply with JSON only:
{{"name": "short-kebab-name", "topic": "what people are reacting to, as a short noun phrase",
 "question": "the prediction question in one sentence",
 "context": "80-150 words of plain facts everyone in the simulation knows",
 "days": <how many days to simulate, 3-30>,
 "options": [if the question is a choice between named options - candidates, parties, products,
             plans - list them (2-6); otherwise an empty list]}}"""

SEGMENTS = HEAD + """
Who reacts? Describe 3-6 groups of ordinary people affected by this (not organizations).
- share: fraction of the population (all add up to 1)
- stance: their likely starting opinion on {topic}, from -1 (against) to 1 (for)
- stubbornness: 0 (easily persuaded) to 1 (never changes)
- activity: 0 (rarely online) to 1 (always online)
- platforms: the apps they really use, from: {platforms}{options_note}
Reply with JSON only:
{{"segments": [{{"name": "young_professionals", "share": 0.3, "persona": "one or two sentences",
  "stance": 0.1, "stubbornness": 0.4, "activity": 0.5, "platforms": ["whatsapp", "instagram"],
  "occupations": ["..."], "age": [25, 35]}}]}}"""

ACCOUNTS = HEAD + """
Which specific organizations or people from the documents will actively speak or decide
(a brand, an official, a committee, a journalist)? Pick 1-8.
Reply with JSON only:
{{"accounts": [{{"id": "short_id", "name": "...", "persona": "who they are and how they communicate",
  "stance": 0.0, "influence": 2.0, "platforms": ["instagram", "whatsapp"], "decides": true}}]}}
Platforms: {platforms}"""

PLACES = HEAD + """
Where do people talk about {topic}, and what real-world actions do we want to predict?
Groups exist on: {spaced} (e.g. residents' WhatsApp group, a Telegram channel, a subreddit,
a local Facebook group). Public feeds ({feeds}) need no groups.
Actions: things a person does, like register, sign up, buy, vote, attend, complain.
Reply with JSON only:
{{"spaces": [{{"platform": "whatsapp", "name": "...", "size": 200, "description": "..."}},
            {{"platform": "facebook_groups", "name": "...", "size": 300, "description": "..."}}],
 "actions": [{{"name": "register", "label": "what the person does, in plain words",
              "open_day": 1, "close_day": 3, "requires": ""}}]}}"""

EVENTS = HEAD + """
Build the timeline over {days} days. Event types:
- "news": something everyone hears about
- "post": an account posts an announcement (needs "account" from: {accounts}; "platform": one of {platforms})
- "decision": a yes/no decision by some accounts (needs "name", "question", "voters": list of account ids)
Later events may say "if_decision": "<decision name>" to happen only if that decision was yes.
Reply with JSON only:
{{"events": [{{"day": 0, "type": "news", "text": "..."}},
            {{"day": 1, "type": "decision", "name": "approval", "question": "...", "voters": ["id"]}},
            {{"day": 1, "type": "post", "account": "id", "platform": "whatsapp", "text": "...", "if_decision": "approval"}}]}}"""

ENTITY_PROFILE = """You are creating a social-media agent for a simulation, based on a real
{kind} that appears in the documents.
Prediction goal: {goal}
Topic people react to: {topic}

Entity: {name} ({etype})
What the documents say about it:
{context}

{instruction}
Reply with JSON only:
{{"bio": "one-line public bio", "persona": "3-4 sentences: who they are, what they want, how they talk and react online",
 "stance": <-1 (against) to 1 (for) on {topic}>, "influence": <1 (few followers) to 5 (very influential)>,
 "activity": <0 (rarely posts) to 1 (posts a lot)>, "platforms": [apps from {platforms}],
 "active_hours": [start hour, end hour], {fields}}}"""

INDIVIDUAL = ("Write the profile of this person as they would behave online.",
              '"age": 40, "gender": "female|male|other", "profession": "...", "mbti": "e.g. ISTJ", '
              '"country": "...", "interests": ["...", "..."]')
GROUP = ("This is an organisation or group: write how its official account behaves online (tone, "
         "what it posts, how it responds to criticism).",
         '"profession": "what kind of organisation", "country": "...", "interests": ["...", "..."]')
INDIVIDUAL_TYPES = ("person", "people", "individual", "official", "expert", "journalist", "influencer",
                    "leader", "candidate", "politician", "doctor", "resident", "customer", "student", "user")


def entity_agents(gs: GraphStore, llm: LLMBackend | None, goal: str, topic: str, existing: list[dict],
                  limit: int = 20, seed: int = 42, say=lambda m: None) -> list[dict]:
    """Turn the most-mentioned people and organisations in the graph into named agents."""
    taken = {slug(a["name"], 40) for a in existing} | {a["id"] for a in existing}
    rows = gs.rows("SELECT id, name, type, description, mentions FROM nodes ORDER BY mentions DESC, id")
    cands = []
    for nid, name, etype, desc, mentions in rows:
        t = (etype or "").lower()
        if t in ("place", "product", "event", "policy", "concept"):
            continue
        if slug(name, 40) in taken:
            continue
        cands.append((nid, name, etype, desc, mentions))
        if len(cands) >= limit:
            break
    out = []
    for i, (nid, name, etype, desc, mentions) in enumerate(cands, 1):
        say(f"profiling {name} ({i}/{len(cands)})")
        facts = [f for (f,) in gs.rows(
            "SELECT e.fact FROM edges e WHERE (e.src = ? OR e.dst = ?) AND e.fact != '' LIMIT 8", (nid, nid))]
        context = "\n".join([desc or ""] + [f"- {f}" for f in facts]).strip() or "(little detail)"
        individual = any(k in (etype or "").lower() for k in INDIVIDUAL_TYPES)
        instr, fields = INDIVIDUAL if individual else GROUP
        default = {"bio": (desc or name)[:120], "persona": desc or f"{name}.", "stance": 0.0,
                   "influence": min(5, 1 + mentions / 2), "activity": 0.3,
                   "platforms": ["x", "facebook"] if not individual else ["x", "instagram"]}
        try:
            d = _ask(llm, ENTITY_PROFILE.format(kind="person" if individual else "organisation or group",
                                                goal=goal, topic=topic, name=name, etype=etype, context=context,
                                                instruction=instr, platforms=PLATFORM_LIST, fields=fields),
                     default, seed * 7 + nid, max_tokens=500, step=f"profile of {name}", check=_ok_profile)
        except StepFailed:
            say(f"SKIPPED {name}: the model could not write a usable profile for it")
            continue
        aid = slug(name, 24)
        n = 2
        while aid in taken:
            aid, n = f"{slug(name, 21)}_{n}", n + 1
        taken.add(aid)
        ah = d.get("active_hours")
        ah = [int(_num(ah[0], 0, 24, 8)), int(_num(ah[1], 0, 24, 23))] if isinstance(ah, list) and len(ah) == 2 else []
        profile = {"kind": "individual" if individual else "group", "source": name,
                   "bio": str(d.get("bio") or "")[:200]}
        for k in ("age", "gender", "profession", "mbti", "country"):
            if d.get(k) not in (None, ""):
                profile[k] = d[k] if k == "age" and isinstance(d[k], int) else str(d[k])[:60]
        if isinstance(d.get("interests"), list):
            profile["interests"] = [str(x)[:40] for x in d["interests"][:6]]
        plats = [p for p in _plats(d.get("platforms"), ("x", "facebook")) if not is_spaced(p)] or ["x"]
        out.append({"id": aid, "name": str(name)[:80], "persona": str(d.get("persona") or default["persona"])[:600],
                    "segment": "entities", "stance": round(_num(d.get("stance"), -1, 1, 0.0), 2),
                    "stubbornness": 0.8, "activity": round(_num(d.get("activity"), 0.02, 1, 0.3), 2),
                    "influence": round(_num(d.get("influence"), 0.5, 5, 2.0), 2), "platforms": plats,
                    "active_hours": ah, "profile": profile})
    return out


PERSONA = """Create one realistic person for a social simulation.
Situation: {context}
Group: {segment} - {persona}
Typical jobs: {occupations}. Age range: {age0}-{age1}.
Make them specific and different from: {others}.
Reply with JSON only:
{{"name": "first name", "age": 30, "occupation": "...",
 "persona": "2-3 sentences: background, habits, what they care about, how they would feel about {topic}"}}"""


# ------------------------------------------------------------------ defaults
def default_frame(goal: str, gs: GraphStore) -> dict:
    lines = []
    for ln in doc_excerpt(gs, 4000).splitlines():
        ln = ln.strip().lstrip("#*- ").strip()
        if len(ln) > 40 and "|" not in ln and not ln.startswith("[page"):
            lines.append(ln)
    context = " ".join(lines)[:900]
    top = gs.rows("SELECT name FROM nodes WHERE type IN ('Product','Policy','Event','Concept') "
                  "ORDER BY mentions DESC LIMIT 1")
    topic = top[0][0] if top else goal.rstrip(".?!")[:90]
    return {"name": slug(topic, 30).replace("_", "-"), "topic": topic,
            "question": goal, "context": context, "days": 7}


DEFAULT_SEGMENTS = [
    {"name": "early_adopters", "share": 0.25, "persona": "Curious people who like trying new things and talk about them.",
     "stance": 0.3, "stubbornness": 0.3, "activity": 0.6, "platforms": ["instagram", "whatsapp", "x", "reddit"]},
    {"name": "mainstream", "share": 0.5, "persona": "Ordinary busy people who follow what friends and neighbours say.",
     "stance": 0.0, "stubbornness": 0.45, "activity": 0.4, "platforms": ["whatsapp", "instagram", "facebook"]},
    {"name": "skeptics", "share": 0.25, "persona": "Cautious people who distrust new offers and ask hard questions.",
     "stance": -0.3, "stubbornness": 0.6, "activity": 0.4, "platforms": ["whatsapp", "facebook", "reddit"]},
]


def default_accounts(gs: GraphStore) -> dict:
    rows = gs.rows("SELECT name, description FROM nodes WHERE type IN ('Organization','Person') "
                   "ORDER BY mentions DESC LIMIT 2")
    return {"accounts": [{"id": slug(n, 20), "name": n, "persona": d or f"{n}.", "stance": 0.3,
                          "influence": 2.5, "platforms": ["instagram", "x", "whatsapp"], "decides": False}
                         for n, d in rows]}


def default_places(topic: str) -> dict:
    return {"spaces": [{"platform": "whatsapp", "name": "Neighbourhood Group", "size": 200},
                       {"platform": "whatsapp", "name": "Friends and Family", "size": 120},
                       {"platform": "facebook_groups", "name": "Local Community Group", "size": 250}],
            "actions": [{"name": "take_up", "label": f"take up {topic}", "open_day": 0,
                         "close_day": 999, "requires": ""}]}


# ------------------------------------------------------------------ cleaning
def clean_segments(raw: dict) -> list[dict]:
    segs, names = [], set()
    for s in (raw.get("segments") or [])[:6]:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        name = slug(s["name"], 30)
        if name in names:
            continue
        names.add(name)
        age = s.get("age") if isinstance(s.get("age"), list) and len(s.get("age")) == 2 else [22, 65]
        a0, a1 = int(_num(age[0], 16, 90, 22)), int(_num(age[1], 16, 95, 65))
        lean = {}
        if isinstance(s.get("leaning"), dict):
            for o, v in s["leaning"].items():
                lean[str(o).strip()[:60]] = round(_num(v, -1, 1, 0.0), 2)
        segs.append({
            "leaning": lean,
            "name": name, "share": _num(s.get("share"), 0.01, 1, 1 / 3),
            "persona": str(s.get("persona") or name.replace("_", " "))[:400],
            "stance": {"mean": round(_num(s.get("stance"), -1, 1, 0.0), 2), "sd": 0.3},
            "stubbornness": round(_num(s.get("stubbornness"), 0.05, 0.95, 0.45), 2),
            "activity": round(_num(s.get("activity"), 0.05, 1, 0.4), 2),
            "platforms": _plats(s.get("platforms")),
            "occupations": [str(o)[:40] for o in (s.get("occupations") or [])][:6],
            "age": [min(a0, a1), max(a0, a1)]})
    if len(segs) < 2:
        return clean_segments({"segments": DEFAULT_SEGMENTS})
    total = sum(s["share"] for s in segs)
    for s in segs:
        s["share"] = round(s["share"] / total, 3)
    return segs


def clean_accounts(raw: dict) -> list[dict]:
    out, ids = [], set()
    for a in (raw.get("accounts") or [])[:8]:
        if not isinstance(a, dict) or not (a.get("name") or a.get("id")):
            continue
        aid = slug(a.get("id") or a.get("name"), 24)
        while aid in ids:
            aid += "_2"
        ids.add(aid)
        out.append({"id": aid, "name": str(a.get("name") or aid)[:80],
                    "persona": str(a.get("persona") or a.get("name"))[:500],
                    "segment": "accounts", "stance": round(_num(a.get("stance"), -1, 1, 0.0), 2),
                    "stubbornness": 0.85, "activity": 0.3,
                    "influence": round(_num(a.get("influence"), 0.5, 5, 2.5), 2),
                    "platforms": _plats(a.get("platforms"), ("instagram", "whatsapp")),
                    "spaces": ["*"], "_decides": bool(a.get("decides"))})
    return out


def clean_places(raw: dict, segs: list[dict]) -> tuple[dict, list[dict]]:
    spaces: dict[str, list] = {}
    seen = set()
    for s in (raw.get("spaces") or [])[:10]:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        plat = resolve(s.get("platform", "whatsapp"))
        if plat is None or not is_spaced(plat):
            continue
        name = str(s["name"]).strip()[:60]
        if plat == "reddit" and not name.startswith("r/"):
            name = "r/" + slug(name, 20)
        if (plat, name) in seen:
            continue
        seen.add((plat, name))
        spaces.setdefault(plat, []).append({"name": name, "size": int(_num(s.get("size"), 20, 5000, 200)),
                                            "description": str(s.get("description") or "")[:200]})
    used = {p for s in segs for p in s["platforms"]}
    for plat in [p for p in SPACED if p in used and p not in spaces]:
        label = REGISTRY[plat].label
        spaces[plat] = ([{"name": "r/local", "size": 250}] if plat == "reddit" else
                        [{"name": f"Local {label} group", "size": 200}])
    acts, names = [], set()
    for a in (raw.get("actions") or [])[:4]:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        n = slug(a["name"], 30)
        if n in names:
            continue
        names.add(n)
        acts.append({"name": n, "label": str(a.get("label") or n.replace("_", " "))[:160],
                     "open_day": _num(a.get("open_day"), 0, 365, 0),
                     "close_day": _num(a.get("close_day"), 0, 9999, 9999),
                     "requires": slug(a["requires"], 30) if a.get("requires") else ""})
    for a in acts:
        if a["requires"] not in names:
            a["requires"] = ""
    return spaces, acts


def clean_events(raw: dict, accounts: list[dict], days: int, rph: int) -> list[dict]:
    ids = {a["id"]: a for a in accounts}
    by_name = {slug(a["name"], 24): a["id"] for a in accounts}
    deciders = [a["id"] for a in accounts if a.get("_decides")] or [a["id"] for a in accounts]
    events, polls = [], set()
    rounds = days * rph
    items = [e for e in (raw.get("events") or []) if isinstance(e, dict)]
    items.sort(key=lambda e: _num(e.get("day"), 0, days, 0))
    for e in items[:20]:
        r = min(rounds - 1, int(_num(e.get("day"), 0, days, 0) * rph))
        t = str(e.get("type", "news")).lower()
        cond = slug(e["if_decision"], 30) if e.get("if_decision") else ""
        when = {"poll": cond, "result": "yes"} if cond in polls else {}
        if t in ("decision", "poll", "vote"):
            name = slug(e.get("name") or f"decision_{len(polls) + 1}", 30)
            voters = [ids.get(v) and v or by_name.get(slug(v, 24)) for v in (e.get("voters") or [])]
            voters = [v for v in voters if v] or deciders
            if not voters or name in polls or not e.get("question"):
                continue
            polls.add(name)
            events.append({"at_round": r, "type": "poll", "name": name,
                           "question": str(e["question"])[:300], "voters": voters, "threshold": 0.5})
        elif t == "post":
            acc = e.get("account")
            acc = acc if acc in ids else by_name.get(slug(acc or "", 24))
            if not acc or not e.get("text"):
                continue
            plat = _plats([e.get("platform") or ids[acc]["platforms"][0]])[0]
            if plat not in ids[acc]["platforms"]:
                ids[acc]["platforms"].append(plat)
            ev = {"at_round": r, "type": "post", "account": acc, "platform": plat,
                  "text": str(e["text"])[:600]}
            if is_spaced(plat):
                ev["spaces"] = ["*"]
            if when:
                ev["when"] = when
            events.append(ev)
        elif e.get("text"):
            ev = {"at_round": r, "type": "news", "text": str(e["text"])[:400]}
            if when:
                ev["when"] = when
            events.append(ev)
    return events


# ------------------------------------------------------------------ main entry
def draft(gs: GraphStore, llm: LLMBackend | None, goal: str, *, llm_agents: int = 40,
          crowd_agents: int = 0, llm_cfg: dict | None = None, rich_personas: bool = True,
          entity_limit: int = 20,
          seed: int = 42, start: datetime | None = None,
          progress: Callable[[str], None] | None = None) -> dict:
    say = progress or (lambda m: None)
    brief, excerpt = graph_brief(gs), doc_excerpt(gs)
    ctx = {"goal": goal, "brief": brief, "excerpt": excerpt, "platforms": PLATFORM_LIST,
           "spaced": ", ".join(REGISTRY[k].label for k in SPACED),
           "feeds": ", ".join(REGISTRY[k].label for k in FEEDS)}

    say("framing the question")
    fr_def = default_frame(goal, gs)
    fr = _ask(llm, FRAME.format(**ctx), fr_def, seed + 1, step="framing the question", check=_ok_frame)
    topic = str(fr.get("topic") or fr_def["topic"])[:120]
    days = int(_num(fr.get("days"), 3, 30, 7))
    ctx["topic"] = topic

    options = [str(o).strip()[:60] for o in (fr.get("options") or []) if str(o).strip()][:6]
    seen_o: dict[str, str] = {}
    for o in options:
        seen_o.setdefault(o.lower(), o)
    options = list(seen_o.values()) if len(seen_o) >= 2 else []
    ctx["options_note"] = (("\n- leaning: how much they like each option, -1..1, as "
                            + "{" + ", ".join(f'"{o}": 0.0' for o in options) + "}") if options else "")
    say("describing who reacts")
    segs = clean_segments(_ask(llm, SEGMENTS.format(**ctx), {"segments": DEFAULT_SEGMENTS}, seed + 2,
                               step="who reacts (groups of people)", check=_ok_segments))

    say("picking the organisations and people who speak")
    accounts = clean_accounts(_ask(llm, ACCOUNTS.format(**ctx), default_accounts(gs), seed + 3,
                                   step="who speaks and decides", check=_ok_accounts))

    if entity_limit:
        say("turning people and organisations in the documents into agents")
        accounts += entity_agents(gs, llm, goal, topic, accounts, limit=entity_limit, seed=seed, say=say)

    say("finding where people talk and what they might do")
    spaces, acts = clean_places(_ask(llm, PLACES.format(**ctx), default_places(topic), seed + 4,
                                     step="where people talk and what actions to predict",
                                     check=_ok_places), segs)
    if not acts:
        if llm is not None:
            raise StepFailed("Step 'actions to predict' failed: the model named no usable action. "
                             "Nothing was made up. Try a larger model and run again.")
        acts = default_places(topic)["actions"]

    say("building the timeline")
    ctx["days"] = days
    ctx["accounts"] = ", ".join(a["id"] for a in accounts) or "(none)"
    rph = int(24 / ROUND_HOURS)
    ev_def = {"events": [{"day": 0, "type": "news", "text": fr_def["context"][:200]}]}
    events = clean_events(_ask(llm, EVENTS.format(**ctx), ev_def, seed + 5, 1200,
                               step="timeline of events", check=_ok_events), accounts, days, rph)
    if not events:
        if llm is not None:
            raise StepFailed("Step 'timeline of events' failed: none of the model's events were usable. "
                             "Nothing was made up. Try a larger model and run again.")
        events = clean_events(ev_def, accounts, days, rph)

    rounds = days * rph
    polls = [e["name"] for e in events if e["type"] == "poll"]
    conversions = []
    for a in acts:
        c = {"name": a["name"], "label": a["label"],
             "open_round": int(min(rounds - 1, a["open_day"] * rph)),
             "close_round": int(min(rounds, a["close_day"] * rph + rph - 1)),
             "base": -5.0 if a["requires"] else -4.2, "stance_weight": 3.0, "exposure_weight": 0.5}
        if a["requires"]:
            c["requires"] = [a["requires"]]
        if polls and not a["requires"]:
            # actions usually depend on the first approval-type decision
            c["when"] = {"poll": polls[0], "result": "yes"}
            c["open_round"] = max(c["open_round"],
                                  next(e["at_round"] for e in events if e.get("name") == polls[0]) + 1)
        c["close_round"] = max(c["close_round"], c["open_round"])
        conversions.append(c)

    for a in accounts:
        a.pop("_decides", None)
    choice = None
    if options:
        for g in segs:
            low = {k.lower(): v for k, v in (g.get("leaning") or {}).items()}
            g["leaning"] = {o: low.get(o.lower(), 0.0) for o in options}
        choice = {"name": "choice", "question": str(fr.get("question") or goal)[:300], "options": options,
                  "open_round": int(rounds * 0.8), "close_round": rounds - 1,
                  "weights": {g["name"]: g["share"] for g in segs}}
    else:
        for g in segs:
            g.pop("leaning", None)
    sc = {
        "name": slug(fr.get("name") or fr_def["name"], 40).replace("_", "-"),
        "topic": topic,
        "question": str(fr.get("question") or goal)[:400],
        "context": str(fr.get("context") or fr_def["context"])[:1500],
        "seed": seed,
        "start": (start or datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
                  + timedelta(days=1)).isoformat(timespec="minutes"),
        "rounds": rounds, "round_hours": ROUND_HOURS,
        "population": {"llm_agents": llm_agents, "crowd_agents": crowd_agents},
        "llm": dict(llm_cfg or {}),
        "segments": segs, "accounts": accounts, "spaces": spaces,
        "events": events, "conversions": conversions,
    }
    if choice:
        sc["choice"] = choice
    sc = repair(sc)

    if rich_personas and llm is not None:
        sc["voices"] = personas(llm, sc, seed, say)
    return sc


def repair(sc: dict) -> dict:
    """Drop whatever still fails validation, one item at a time."""
    for _ in range(40):
        try:
            scenario_mod.from_dict(json.loads(json.dumps(sc)))
            return sc
        except scenario_mod.ScenarioError as e:
            msg = str(e)
            m = re.search(r"round (\d+)", msg)
            if msg.startswith(("Event", "Poll")) and m:
                r = int(m.group(1))
                idx = next(i for i, ev in enumerate(sc["events"]) if ev["at_round"] == r)
                sc["events"].pop(idx)
                continue
            m = re.match(r"Conversion (\S+):", msg)
            if m:
                sc["conversions"] = [c for c in sc["conversions"] if c["name"] != m.group(1)]
                continue
            raise
    raise scenario_mod.ScenarioError("Could not repair drafted scenario")


def personas(llm: LLMBackend, sc: dict, seed: int, say) -> list[dict]:
    from ..sim.population import _alloc
    counts = _alloc(sc["population"]["llm_agents"], [s["share"] for s in sc["segments"]])
    voices = []
    total, k = sum(counts), 0
    for seg, n in zip(sc["segments"], counts):
        made: list[str] = []
        for i in range(n):
            k += 1
            if k == 1 or k % 10 == 0 or k == total:
                say(f"writing persona {k}/{total}")
            # only the test (mock) backend reads this canned answer; real models ignore it
            default = ({"name": f"Mock{k}", "age": sum(seg["age"]) // 2, "occupation": "",
                        "persona": f"A made-up person from the {seg['name']} group, for tests only."}
                       if llm.cfg.backend == "mock" else {})
            d = _ask(llm, PERSONA.format(context=sc["context"][:600], segment=seg["name"],
                                         persona=seg["persona"],
                                         occupations=", ".join(seg.get("occupations") or ["any"]),
                                         age0=seg["age"][0], age1=seg["age"][1],
                                         others="; ".join(made[-4:]) or "nobody yet",
                                         topic=sc["topic"]),
                     default, seed * 1000 + k, max_tokens=300, step=f"persona {k} of {total}",
                     check=_ok_persona, tries=5)
            name = str(d.get("name") or "").strip().split()[0][:24] if d.get("name") else ""
            text = str(d.get("persona") or "").strip()
            age = int(_num(d.get("age"), seg["age"][0], seg["age"][1], sum(seg["age"]) // 2))
            v = {"segment": seg["name"], "name": name, "age": age,
                 "occupation": str(d.get("occupation") or "")[:60], "persona": text[:600]}
            voices.append(v)
            made.append(f"{name}, {age}, {v['occupation']}")
    return voices


def to_yaml(sc: dict, goal: str, n_docs: int) -> str:
    import yaml
    head = (f"# Drafted by Agora from {n_docs} document(s) for:\n#   {goal}\n"
            "# Everything below is editable. Opinion, activity and conversion numbers are\n"
            "# starting assumptions - check them, then calibrate with real data (Phase 4).\n\n")
    return head + yaml.safe_dump(sc, sort_keys=False, allow_unicode=True, width=100)

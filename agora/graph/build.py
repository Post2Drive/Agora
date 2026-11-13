"""Stage 1b - graph building.

1. Ontology: the model reads your prediction prompt and a sample of the documents and
   proposes which kinds of things (entity types) and links (relation types) matter.
2. Extraction: every chunk is read once; entities and relations are pulled out with the
   ontology as a guide. Each chunk is saved as soon as it is done, so a long build can
   be stopped and resumed.
3. Merge: the same thing mentioned under different names (aliases, acronyms, case)
   becomes one node. Every relation keeps the sentence-level fact and the chunk it came
   from, so the report can cite sources.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import networkx as nx

from ..llm import LLMBackend, LLMError, parse_json
from . import heuristic
from .store import GraphStore

DEFAULT_ONTOLOGY = {
    "entity_types": [
        {"name": "Person", "description": "a named individual"},
        {"name": "Organization", "description": "company, brand, association, authority, group"},
        {"name": "Community", "description": "a group of people: residents, customers, users, voters"},
        {"name": "Product", "description": "product, service, offer or programme"},
        {"name": "Place", "description": "city, area, building, venue"},
        {"name": "Event", "description": "something that happens at a time: launch, approval, campaign stage"},
        {"name": "Policy", "description": "a rule, condition, price or requirement"},
        {"name": "Concept", "description": "anything else that matters to the question"},
    ],
    "relation_types": [
        {"name": "OFFERS", "description": "an organization offers a product or programme"},
        {"name": "TARGETS", "description": "something is aimed at a community or place"},
        {"name": "REQUIRES", "description": "something needs approval, payment or a condition"},
        {"name": "MEMBER_OF", "description": "a person or group belongs to a community/organization"},
        {"name": "LOCATED_IN", "description": "located in a place"},
        {"name": "INFLUENCES", "description": "affects opinions or decisions of"},
        {"name": "HAS_PROPERTY", "description": "a product or thing has a stated attribute"},
        {"name": "RELATED_TO", "description": "any other meaningful link"},
    ],
}

ONTOLOGY_PROMPT = """You design a knowledge graph for a social simulation.
Prediction goal: {goal}

Document sample:
\"\"\"{sample}\"\"\"

List 5-9 entity types and 5-10 relation types that matter for this goal.
Include types for the PEOPLE and GROUPS whose reactions we will simulate.
Reply with JSON only:
{{"entity_types": [{{"name": "Organization", "description": "..."}}],
 "relation_types": [{{"name": "OFFERS", "description": "..."}}]}}"""

EXTRACT_PROMPT = """Extract a knowledge graph from the text, for this prediction goal: {goal}

Entity types: {etypes}
Relation types: {rtypes}

Text:
\"\"\"{text}\"\"\"

Rules:
- Only things stated in the text. Do not invent.
- Use the most complete name; put short forms and acronyms in "aliases".
- "fact" is one short sentence from the text that states the relation.
Reply with JSON only:
{{"entities": [{{"name": "...", "type": "...", "description": "one sentence", "aliases": []}}],
 "relations": [{{"source": "entity name", "target": "entity name", "type": "...", "fact": "..."}}]}}"""


def norm(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", str(name).lower())
    s = re.sub(r"\b(the|pvt|ltd|limited|inc|llc|private)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _clean_type(t: str, allowed: list[str], default: str) -> str:
    t = re.sub(r"[^A-Za-z_ ]", "", str(t or "")).strip()
    for a in allowed:
        if a.lower() == t.lower():
            return a
    return default


def make_ontology(gs: GraphStore, llm: LLMBackend | None, goal: str) -> dict:
    cached = gs.get_meta("ontology")
    if cached:
        return cached
    onto = DEFAULT_ONTOLOGY
    if llm is not None:
        sample = "\n\n".join(t for (t,) in gs.rows("SELECT text FROM chunks ORDER BY id LIMIT 3"))[:3500]
        try:
            d = llm.generate_json(
                [{"role": "user", "content": ONTOLOGY_PROMPT.format(goal=goal, sample=sample)}],
                max_tokens=600, temperature=0.2, seed=1,
                meta={"task": "json", "default": DEFAULT_ONTOLOGY})
        except LLMError:
            d = {}
        et = [x for x in d.get("entity_types", []) if isinstance(x, dict) and x.get("name")]
        rt = [x for x in d.get("relation_types", []) if isinstance(x, dict) and x.get("name")]
        if len(et) >= 3 and len(rt) >= 2:
            names = {x["name"].lower() for x in et}
            for must in ("Person", "Organization", "Community"):
                if must.lower() not in names:
                    et.append(next(x for x in DEFAULT_ONTOLOGY["entity_types"] if x["name"] == must))
            if "related_to" not in {x["name"].lower() for x in rt}:
                rt.append({"name": "RELATED_TO", "description": "any other meaningful link"})
            onto = {"entity_types": et[:12], "relation_types": rt[:12]}
    gs.set_meta("ontology", onto)
    return onto


def extract_chunk(llm: LLMBackend | None, text: str, goal: str, onto: dict, seed: int) -> dict | None:
    """Entities and relations in one chunk. Without a model (the user's explicit choice) a
    rule-based reader is used; with a model, failures are retried and then left for later
    (None), never replaced by rule-based guesses."""
    if llm is None:
        return heuristic.extract(text)
    et = [x["name"] for x in onto["entity_types"]]
    rt = [x["name"] for x in onto["relation_types"]]
    prompt = EXTRACT_PROMPT.format(goal=goal, etypes=", ".join(et), rtypes=", ".join(rt), text=text)
    for t in range(3):
        try:
            d = llm.generate_json([{"role": "user", "content": prompt}], max_tokens=1200,
                                  temperature=0.1 + 0.2 * t, seed=seed + 7919 * t,
                                  meta={"task": "json", "default": heuristic.extract(text)})
        except LLMError:
            continue
        ents = [e for e in d.get("entities", []) if isinstance(e, dict) and str(e.get("name", "")).strip()]
        rels = [r for r in d.get("relations", []) if isinstance(r, dict)
                and str(r.get("source", "")).strip() and str(r.get("target", "")).strip()]
        if ents:
            return {"entities": ents, "relations": rels}
    return None


def build(gs: GraphStore, llm: LLMBackend | None, goal: str,
          progress: Callable[[dict], None] | None = None) -> dict:
    """Extract every pending chunk, then merge into nodes and edges."""
    onto = make_ontology(gs, llm, goal)
    pending = gs.rows("SELECT id, text FROM chunks WHERE status != 'done' ORDER BY id")
    total = gs.rows("SELECT COUNT(*) FROM chunks")[0][0]
    failed = 0
    for i, (cid, text) in enumerate(pending):
        res = extract_chunk(llm, text, goal, onto, seed=cid)
        if res is None:                       # stays pending: retried on the next build
            failed += 1
            res = {"entities": [], "relations": []}
        else:
            with gs.db:
                gs.db.execute("UPDATE chunks SET status='done', raw=? WHERE id=?", (json.dumps(res), cid))
        if progress:
            progress({"chunk": total - len(pending) + i + 1, "of": total, "failed": res is None,
                      "entities": len(res["entities"]), "relations": len(res["relations"])})
    done = gs.rows("SELECT COUNT(*) FROM chunks WHERE status='done'")[0][0]
    if total and not done:
        raise LLMError("The model could not read any part of the documents. Check the model, or "
                       "choose a stronger one for 'Graph, people and report'.")
    st = merge(gs, onto)
    st["failed_chunks"] = failed
    return st


def merge(gs: GraphStore, onto: dict) -> dict:
    """Rebuild nodes/edges from all extracted chunks (cheap, deterministic)."""
    etypes = [x["name"] for x in onto["entity_types"]]
    rtypes = [x["name"] for x in onto["relation_types"]]
    nodes: dict[str, dict] = {}
    alias: dict[str, str] = {}
    chunk_rows = gs.rows("SELECT id, raw FROM chunks WHERE status='done' ORDER BY id")

    def resolve(name: str) -> str:
        k = norm(name)
        return alias.get(k, k)

    # pass 1: entities and aliases
    for cid, raw in chunk_rows:
        for e in json.loads(raw).get("entities", []):
            name = str(e["name"]).strip()[:120]
            k = resolve(name)
            if not k:
                continue
            n = nodes.get(k)
            if n is None:
                n = nodes[k] = {"name": name, "types": {}, "desc": [], "aliases": set(),
                                "chunks": set(), "mentions": 0}
            t = _clean_type(e.get("type"), etypes, "Concept")
            n["types"][t] = n["types"].get(t, 0) + 1
            d = str(e.get("description") or "").strip()
            if d and d not in n["desc"]:
                n["desc"].append(d[:300])
            n["chunks"].add(cid)
            n["mentions"] += 1
            if len(name) > len(n["name"]) and norm(name) == k:
                n["name"] = name
            for a in e.get("aliases") or []:
                ak = norm(a)
                if ak and ak != k and ak not in nodes:
                    alias[ak] = k
                    n["aliases"].add(str(a).strip()[:60])
    # alias keys that were also created as separate nodes before the alias was seen: fold in
    for ak, k in list(alias.items()):
        if ak in nodes and k in nodes and ak != k:
            src, dst = nodes.pop(ak), nodes[k]
            for t, c in src["types"].items():
                dst["types"][t] = dst["types"].get(t, 0) + c
            dst["desc"] += [d for d in src["desc"] if d not in dst["desc"]]
            dst["aliases"] |= src["aliases"] | {src["name"]}
            dst["chunks"] |= src["chunks"]
            dst["mentions"] += src["mentions"]

    # pass 2: relations (unknown endpoints become Concept nodes)
    edges = []
    for cid, raw in chunk_rows:
        for r in json.loads(raw).get("relations", []):
            ends = []
            for side in ("source", "target"):
                name = str(r[side]).strip()[:120]
                k = resolve(name)
                if k and k not in nodes:
                    nodes[k] = {"name": name, "types": {"Concept": 1}, "desc": [], "aliases": set(),
                                "chunks": {cid}, "mentions": 1}
                ends.append(k)
            if not all(ends) or ends[0] == ends[1]:
                continue
            edges.append((ends[0], ends[1], _clean_type(r.get("type"), rtypes, "RELATED_TO"),
                          str(r.get("fact") or "").strip()[:300], cid))

    keys = sorted(nodes, key=lambda k: (-nodes[k]["mentions"], k))
    ids = {k: i for i, k in enumerate(keys)}
    seen_edges = set()
    with gs.db:
        gs.db.execute("DELETE FROM nodes")
        gs.db.execute("DELETE FROM edges")
        gs.db.execute("DELETE FROM node_chunks")
        for k in keys:
            n = nodes[k]
            t = max(n["types"], key=n["types"].get)
            gs.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?)",
                          (ids[k], k, n["name"], t, " ".join(n["desc"][:3])[:600],
                           json.dumps(sorted(n["aliases"])), n["mentions"]))
            gs.db.executemany("INSERT OR IGNORE INTO node_chunks VALUES (?,?)",
                              [(ids[k], c) for c in n["chunks"]])
        for s, d, t, fact, cid in edges:
            key = (s, d, t, fact.lower())
            if key in seen_edges:
                continue
            seen_edges.add(key)
            gs.db.execute("INSERT INTO edges (src, dst, type, fact, chunk) VALUES (?,?,?,?,?)",
                          (ids[s], ids[d], t, fact, cid))
    return stats(gs)


def stats(gs: GraphStore) -> dict:
    types = dict(gs.rows("SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY 2 DESC"))
    return {"documents": gs.rows("SELECT COUNT(*) FROM documents")[0][0],
            "chunks": gs.rows("SELECT COUNT(*) FROM chunks")[0][0],
            "nodes": gs.rows("SELECT COUNT(*) FROM nodes")[0][0],
            "edges": gs.rows("SELECT COUNT(*) FROM edges")[0][0], "node_types": types}


def to_networkx(gs: GraphStore) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for nid, _, name, t, desc, aliases, mentions in gs.rows("SELECT * FROM nodes"):
        g.add_node(nid, name=name, type=t, description=desc, aliases=aliases, mentions=mentions)
    for eid, s, d, t, fact, cid in gs.rows("SELECT * FROM edges"):
        g.add_edge(s, d, key=eid, type=t, fact=fact, chunk=cid)
    return g


def export(gs: GraphStore, folder) -> dict:
    from pathlib import Path
    folder = Path(folder)
    g = to_networkx(gs)
    nx.write_graphml(g, folder / "graph.graphml")
    data = nx.node_link_data(g, edges="links")
    (folder / "graph.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"graphml": str(folder / "graph.graphml"), "json": str(folder / "graph.json")}

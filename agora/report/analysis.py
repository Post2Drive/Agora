"""Deterministic analysis of a finished (or running) simulation.

Every number in a report comes from here, not from the language model. The model
only writes prose around these numbers, so a small local model cannot invent results.
"""
from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from pathlib import Path

from .. import scenario as scenario_mod
from ..platforms import REGISTRY

STOP = set("""a an the and or of to in on at for by with from is are was were be been am it its this that these those as
not no but if then than so such can will would could should may might per each every one any all into about after before
your you we our they their them he she his her i me my mine us just do does did done have has had having get got
there here what which who whom how when where why also too very really more most much many some only own same other
yes ok okay oh hmm like im ive dont cant wont its thats theres lets anyone someone something anything everyone
will would think know see going go get one two first new good""".split())
_TOK = re.compile(r"[a-z][a-z0-9']+")


def _words(text: str) -> list[str]:
    return [w.strip("'") for w in _TOK.findall(text.lower()) if w.strip("'") not in STOP and len(w) > 2]


class Analysis:
    def __init__(self, project: str | Path):
        self.dir = Path(project)
        self.sc = scenario_mod.load(self.dir / "scenario.yaml")
        path = self.dir / "agora.db"
        if not path.exists():
            raise FileNotFoundError("This project has not been run yet.")
        self.db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        self.q = lambda sql, a=(): self.db.execute(sql, a).fetchall()

    def close(self):
        self.db.close()

    # ---------------------------------------------------------------- pieces
    def overview(self) -> dict:
        q = self.q
        done = q("SELECT COUNT(*) FROM rounds")[0][0]
        kinds = dict(q("SELECT kind, COUNT(*) FROM agents GROUP BY kind"))
        posts = dict(q("SELECT platform, COUNT(*) FROM posts WHERE kind IN ('post','reply') GROUP BY platform"))
        shares = q("SELECT COUNT(*) FROM posts WHERE kind IN ('repost','forward')")[0][0]
        eng = dict(q("SELECT substr(type,1,instr(type||':',':')-1), COUNT(*) FROM engagements GROUP BY 1"))
        t = q("SELECT COALESCE(SUM(seconds),0), COALESCE(SUM(llm_calls),0) FROM rounds")[0]
        return {"rounds_done": done, "rounds_total": self.sc.rounds,
                "days": round(done * self.sc.round_hours / 24, 1),
                "llm_voices": kinds.get("llm", 0), "crowd": kinds.get("crowd", 0),
                "accounts": kinds.get("account", 0), "posts_by_platform": posts,
                "posts": sum(posts.values()), "shares": shares, "engagements": eng,
                "seconds": t[0], "llm_calls": t[1]}

    def opinion(self) -> dict:
        q = self.q
        last = q("SELECT MAX(round) FROM opinions")[0][0]
        rows = q("SELECT a.segment, o.round, AVG(o.stance), COUNT(*) FROM opinions o JOIN agents a "
                 "ON a.id = o.agent WHERE a.kind != 'account' AND o.round IN (-1, ?) "
                 "GROUP BY a.segment, o.round", (last,))
        seg: dict[str, dict] = {}
        for g, r, avg, n in rows:
            d = seg.setdefault(g, {"agents": n})
            d["start" if r == -1 else "end"] = round(avg, 3)
        for d in seg.values():
            d.setdefault("end", d.get("start", 0.0))
            d["change"] = round(d["end"] - d.get("start", 0.0), 3)

        def dist(r):
            vals = [v for (v,) in q("SELECT o.stance FROM opinions o JOIN agents a ON a.id=o.agent "
                                    "WHERE a.kind != 'account' AND o.round = ?", (r,))]
            if not vals:
                return {}
            n = len(vals)
            mean = sum(vals) / n
            return {"for": round(sum(v > 0.2 for v in vals) / n, 3),
                    "undecided": round(sum(-0.2 <= v <= 0.2 for v in vals) / n, 3),
                    "against": round(sum(v < -0.2 for v in vals) / n, 3),
                    "mean": round(mean, 3),
                    "spread": round(math.sqrt(sum((v - mean) ** 2 for v in vals) / n), 3)}
        trend = q("SELECT o.round, a.segment, AVG(o.stance) FROM opinions o JOIN agents a "
                  "ON a.id=o.agent WHERE a.kind != 'account' GROUP BY o.round, a.segment ORDER BY o.round")
        by_platform = {p: round(v, 3) for p, v in q(
            "SELECT platform, AVG(stance) FROM posts WHERE kind IN ('post','reply') GROUP BY platform")}
        return {"segments": seg, "start": dist(-1), "end": dist(last if last is not None else -1),
                "trend": [(r, g, round(v, 4)) for r, g, v in trend], "post_tone_by_platform": by_platform}

    def _eligible(self, c) -> list[int]:
        """Agents who could take this action at all (ignoring timing)."""
        q = self.q
        agents = q("SELECT id, segment FROM agents WHERE kind != 'account'")
        ok = {a for a, s in agents if not c.eligible_segments or s in c.eligible_segments}
        if c.eligible_spaces:
            marks = ",".join("?" * len(c.eligible_spaces))
            members = {a for (a,) in q(f"SELECT DISTINCT agent FROM memberships WHERE space IN ({marks})",
                                       c.eligible_spaces)}
            ok &= members
        if c.requires:
            marks = ",".join("?" * len(c.requires))
            done = {a for (a,) in q(f"SELECT DISTINCT agent FROM conversions WHERE name IN ({marks})",
                                    c.requires)}
            ok &= done
        return sorted(ok)

    def funnel(self) -> list[dict]:
        q = self.q
        polls = {n: bool(p) for n, p in q("SELECT name, passed FROM poll_results")}
        seg_size = dict(q("SELECT segment, COUNT(*) FROM agents WHERE kind != 'account' GROUP BY segment"))
        out = []
        for c in self.sc.conversions:
            elig = self._eligible(c)
            rows = q("SELECT c.agent, c.round, a.segment, a.kind FROM conversions c JOIN agents a "
                     "ON a.id = c.agent WHERE c.name = ? ORDER BY c.round", (c.name,))
            n = len(rows)
            blocked = ""
            for p in _cond_polls(c.when):
                if p in polls and not polls[p]:
                    blocked = p
            elig_set = set(elig)
            by_seg_n = Counter(r[2] for r in rows)
            elig_seg = Counter()
            if elig:
                marks = ",".join("?" * len(elig))
                elig_seg = Counter(dict(q(f"SELECT segment, COUNT(*) FROM agents WHERE id IN ({marks}) "
                                          "GROUP BY segment", elig)))
            rounds = [r[1] for r in rows]
            out.append({
                "name": c.name, "label": c.label, "count": n, "eligible": len(elig),
                "rate": round(n / len(elig), 4) if elig else 0.0,
                "rate_of_population": round(n / max(1, sum(seg_size.values())), 4),
                "blocked_by": blocked, "requires": c.requires,
                "by_segment": {g: {"count": by_seg_n.get(g, 0), "eligible": elig_seg.get(g, 0),
                                   "rate": round(by_seg_n.get(g, 0) / elig_seg[g], 4) if elig_seg.get(g) else 0.0}
                               for g in seg_size},
                "llm_voices": sum(1 for r in rows if r[3] == "llm"),
                "outside_eligible": sum(1 for r in rows if r[0] not in elig_set),
                "median_round": rounds[len(rounds) // 2] if rounds else None,
                "first_round": rounds[0] if rounds else None,
                "window": [c.open_round, min(c.close_round, self.sc.rounds - 1)],
                "per_round": q("SELECT round, COUNT(*) FROM conversions WHERE name = ? GROUP BY round "
                               "ORDER BY round", (c.name,))})
        return out

    def decisions(self) -> list[dict]:
        q = self.q
        out = []
        for name, r, yes, no, passed in q("SELECT name, round, yes, no, passed FROM poll_results"):
            votes = q("SELECT a.name, a.handle, p.vote, p.reason FROM polls p JOIN agents a "
                      "ON a.id = p.agent WHERE p.name = ? ORDER BY p.vote DESC, a.id", (name,))
            out.append({"name": name, "round": r, "yes": yes, "no": no, "passed": bool(passed),
                        "votes": [{"name": n, "handle": h, "vote": "yes" if v else "no", "reason": why}
                                  for n, h, v, why in votes][:30]})
        return out

    def influencers(self, k: int = 10) -> list[dict]:
        rows = self.q(
            "SELECT p.author, a.name, a.handle, a.kind, a.segment, COUNT(DISTINCT p.id), "
            "  COALESCE(SUM(e.n), 0), s.stance FROM posts p JOIN agents a ON a.id = p.author "
            "  JOIN agent_state s ON s.id = a.id "
            "  LEFT JOIN (SELECT post, COUNT(*) n FROM engagements GROUP BY post) e ON e.post = p.id "
            "WHERE p.kind IN ('post','reply') GROUP BY p.author ORDER BY 7 DESC, 6 DESC LIMIT ?", (k,))
        shares = dict(self.q("SELECT s.author, COUNT(*) FROM posts f JOIN posts s ON s.id = f.root "
                             "WHERE f.kind IN ('repost','forward') GROUP BY s.author"))
        return [{"id": aid, "name": n, "handle": h, "kind": kd, "segment": g, "posts": np_,
                 "engagement": int(e), "shared": shares.get(aid, 0), "stance": round(st, 3)}
                for aid, n, h, kd, g, np_, e, st in rows]

    def top_posts(self, k: int = 6) -> dict:
        base = ("SELECT p.id, p.platform, p.space, p.round, p.text, p.stance, a.name, a.handle, a.segment, "
                " (SELECT COUNT(*) FROM engagements e WHERE e.post = p.id) + "
                " 2 * (SELECT COUNT(*) FROM posts r WHERE r.root = p.id AND r.kind IN ('repost','forward')) + "
                " 2 * (SELECT COUNT(*) FROM posts c WHERE c.parent = p.id AND c.kind = 'reply') AS score "
                "FROM posts p JOIN agents a ON a.id = p.author "
                "WHERE p.kind IN ('post','reply') AND p.text != '' AND a.kind != 'account' AND {cond} "
                "ORDER BY score DESC, p.id LIMIT ?")
        cols = ["id", "platform", "space", "round", "text", "stance", "author", "handle", "segment", "score"]
        get = lambda cond: [dict(zip(cols, r)) for r in self.q(base.format(cond=cond), (k,))]
        return {"positive": get("p.stance > 0.2"), "negative": get("p.stance < -0.2"),
                "undecided": get("p.stance BETWEEN -0.2 AND 0.2")}

    def themes(self, k: int = 8) -> dict:
        rows = self.q("SELECT p.id, p.text, p.stance FROM posts p JOIN agents a ON a.id = p.author "
                      "WHERE p.kind IN ('post','reply') AND p.text != '' AND a.kind != 'account'")
        topic_words = set(_words(self.sc.topic))
        groups = {"positive": [], "negative": []}
        for pid, text, st in rows:
            if st > 0.2:
                groups["positive"].append((pid, text))
            elif st < -0.2:
                groups["negative"].append((pid, text))
        out = {}
        for g, items in groups.items():
            uni, bi, example = Counter(), Counter(), {}
            for pid, text in items:
                w = [x for x in _words(text) if x not in topic_words]
                seen = set()
                for t in w + [f"{a} {b}" for a, b in zip(w, w[1:])]:
                    if t in seen:
                        continue
                    seen.add(t)
                    (bi if " " in t else uni)[t] += 1
                    example.setdefault(t, pid)
            ranked = [(t, c) for t, c in bi.most_common(k) if c >= 2]
            ranked += [(t, c) for t, c in uni.most_common(k * 2)
                       if c >= 2 and not any(t in b for b, _ in ranked)]
            ranked.sort(key=lambda x: -x[1])
            out[g] = [{"phrase": t, "posts": c, "example": example[t]} for t, c in ranked[:k]]
            out[g + "_posts"] = len(items)
        return out

    def spread(self) -> dict:
        q = self.q
        by_space = q("SELECT platform, space, COUNT(*) FROM posts WHERE kind IN ('post','reply') "
                     "AND space != '' GROUP BY platform, space ORDER BY 3 DESC LIMIT 12")
        fwd = q("SELECT platform, space, COUNT(*) FROM posts WHERE kind = 'forward' "
                "GROUP BY platform, space ORDER BY 3 DESC LIMIT 8")
        return {"busiest_groups": [{"platform": p, "space": s, "messages": n} for p, s, n in by_space],
                "forwarded_into": [{"platform": p, "space": s, "forwards": n} for p, s, n in fwd]}

    def economics(self, funnel: list[dict]) -> dict:
        e = self.sc.economics or {}
        if not e:
            return {}
        cost, value = e.get("cost") or {}, e.get("value") or {}
        counts = {f["name"]: f["count"] for f in funnel}
        total_cost = float(e.get("fixed_cost", 0)) + sum(cost.get(n, 0) * counts.get(n, 0) for n in cost)
        total_value = sum(value.get(n, 0) * counts.get(n, 0) for n in value)
        per = {n: round(total_cost / counts[n], 2) for n in counts if counts[n]}
        return {"currency": e.get("currency", ""), "total_cost": round(total_cost, 2),
                "total_value": round(total_value, 2), "net": round(total_value - total_cost, 2),
                "cost_per": per}

    def choice(self) -> dict:
        """Election / multi-option results: intentions over time, votes, turnout, weighting."""
        ch = self.sc.choice
        if not ch:
            return {}
        q = self.q
        opts = list(ch.options)
        seg_size = dict(q("SELECT segment, COUNT(*) FROM agents WHERE kind != 'account' GROUP BY segment"))
        weights = {g: float(ch.weights.get(g, 0)) for g in seg_size} if ch.weights else {}
        if not weights or sum(weights.values()) <= 0:
            weights = {g: n for g, n in seg_size.items()}
        tot_w = sum(weights.values())
        weights = {g: w / tot_w for g, w in weights.items()}

        def weighted(by_seg: dict[str, dict[str, float]]) -> dict[str, float]:
            out = {o: 0.0 for o in opts}
            for g, shares in by_seg.items():
                for o in opts:
                    out[o] += weights.get(g, 0.0) * shares.get(o, 0.0)
            z = sum(out.values())
            return {o: round(v / z, 4) if z else 0.0 for o, v in out.items()}

        # intentions over time (decided only)
        rows = q("SELECT round, segment, option, n FROM intentions ORDER BY round")
        per_round: dict[int, dict[str, dict[str, int]]] = {}
        for r, g, o, n in rows:
            per_round.setdefault(r, {}).setdefault(g, {})[o] = n
        trend = []
        for r in sorted(per_round):
            segs = per_round[r]
            shares = {g: {o: c.get(o, 0) / max(1, sum(v for k, v in c.items() if k != "undecided")) for o in opts}
                      for g, c in segs.items()}
            und = sum(c.get("undecided", 0) for c in segs.values()) / max(1, sum(sum(c.values()) for c in segs.values()))
            raw_tot = {o: sum(c.get(o, 0) for c in segs.values()) for o in opts}
            z = sum(raw_tot.values()) or 1
            trend.append({"round": r, "raw": {o: round(v / z, 4) for o, v in raw_tot.items()},
                          "weighted": weighted(shares), "undecided": round(und, 4)})
        # votes
        votes = q("SELECT a.segment, c.option, COUNT(*) FROM choices c JOIN agents a ON a.id = c.agent "
                  "GROUP BY a.segment, c.option")
        vs: dict[str, dict[str, int]] = {}
        for g, o, n in votes:
            vs.setdefault(g, {})[o] = n
        voted = sum(sum(c.values()) for c in vs.values())
        by_segment = {}
        for g, size in seg_size.items():
            c = vs.get(g, {})
            n = sum(c.values())
            by_segment[g] = {"turnout": round(n / size, 4) if size else 0.0, "voters": n, "size": size,
                             "shares": {o: round(c.get(o, 0) / n, 4) if n else 0.0 for o in opts},
                             "weight": round(weights.get(g, 0.0), 4)}
        raw = {o: round(sum(c.get(o, 0) for c in vs.values()) / voted, 4) if voted else 0.0 for o in opts}
        # weighting: each group's share of the real electorate x its turnout
        tw = {g: weights.get(g, 0) * d["turnout"] for g, d in by_segment.items()}
        z = sum(tw.values())
        wshare = {o: 0.0 for o in opts}
        for g, d in by_segment.items():
            for o in opts:
                wshare[o] += (tw[g] / z if z else 0) * d["shares"][o]
        wshare = {o: round(v, 4) for o, v in wshare.items()}
        status = "final" if self.q("SELECT COUNT(*) FROM rounds")[0][0] > ch.close_round or \
            self.q("SELECT COUNT(*) FROM rounds")[0][0] >= self.sc.rounds else ("voting" if voted else "before voting")
        result = wshare if voted else (trend[-1]["weighted"] if trend else {o: 0.0 for o in opts})
        ranked = sorted(opts, key=lambda o: -result[o])
        return {"name": ch.name, "question": ch.question, "options": opts, "status": status,
                "votes_cast": voted, "electorate": sum(seg_size.values()),
                "turnout": round(voted / max(1, sum(seg_size.values())), 4),
                "weighted_turnout": round(sum(weights.get(g, 0) * d["turnout"] for g, d in by_segment.items()), 4),
                "raw_share": raw, "weighted_share": wshare, "result": result,
                "basis": "votes" if voted else "latest intentions",
                "leader": ranked[0], "runner_up": ranked[1] if len(ranked) > 1 else "",
                "margin": round(result[ranked[0]] - (result[ranked[1]] if len(ranked) > 1 else 0), 4),
                "by_segment": by_segment, "weights": {g: round(w, 4) for g, w in weights.items()},
                "trend": trend}

    def everything(self) -> dict:
        f = self.funnel()
        return {"scenario": {"name": self.sc.name, "question": " ".join(self.sc.question.split()), "topic": self.sc.topic,
                             "segments": [s.name for s in self.sc.segments],
                             "platforms": sorted({p for s in self.sc.segments for p in s.platforms})},
                "overview": self.overview(), "opinion": self.opinion(), "funnel": f,
                "decisions": self.decisions(), "influencers": self.influencers(),
                "top_posts": self.top_posts(), "themes": self.themes(), "spread": self.spread(),
                "economics": self.economics(f), "choice": self.choice()}


def _cond_polls(cond: dict) -> list[str]:
    if not cond:
        return []
    if "any" in cond:
        return [p for c in cond["any"] for p in _cond_polls(c)]
    return [cond.get("poll")]


def label(key: str) -> str:
    return REGISTRY[key].label if key in REGISTRY else key


def nice(name: str) -> str:
    return str(name).replace("_", " ")


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def money(x: float, cur: str) -> str:
    sym = {"INR": "₹", "GBP": "£", "USD": "$", "EUR": "€"}.get(cur.upper(), cur + " " if cur else "")
    return f"{sym}{x:,.0f}"



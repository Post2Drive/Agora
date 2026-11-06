"""Quick numeric summary of a project's run (the full report agent is Phase 3)."""
from __future__ import annotations

from .store import Store


def summarise(store: Store) -> dict:
    q = store.rows
    last = store.last_round()
    seg_rows = q("SELECT a.segment, a.kind, COUNT(*), AVG(s.stance), AVG(a.initial_stance) "
                 "FROM agents a JOIN agent_state s ON a.id = s.id GROUP BY a.segment, a.kind")
    segments: dict[str, dict] = {}
    for seg, kind, n, now, start in seg_rows:
        d = segments.setdefault(seg, {"agents": 0, "stance_start": 0.0, "stance_now": 0.0})
        tot = d["agents"] + n
        d["stance_start"] = (d["stance_start"] * d["agents"] + start * n) / tot
        d["stance_now"] = (d["stance_now"] * d["agents"] + now * n) / tot
        d["agents"] = tot
    conv = q("SELECT c.name, a.segment, COUNT(*) FROM conversions c JOIN agents a ON a.id=c.agent "
             "GROUP BY c.name, a.segment")
    conversions: dict[str, dict] = {}
    for name, seg, n in conv:
        conversions.setdefault(name, {"total": 0, "by_segment": {}})
        conversions[name]["total"] += n
        conversions[name]["by_segment"][seg] = n
    posts = dict(q("SELECT platform, COUNT(*) FROM posts GROUP BY platform"))
    polls = {n: {"yes": y, "no": no, "passed": bool(p)}
             for n, _, y, no, p in q("SELECT * FROM poll_results")}
    timing = q("SELECT COALESCE(SUM(seconds),0), COALESCE(SUM(llm_calls),0), "
               "COALESCE(SUM(cache_hits),0) FROM rounds")[0]
    trend = q("SELECT o.round, AVG(o.stance) FROM opinions o GROUP BY o.round ORDER BY o.round")
    return {"rounds_done": last + 1, "segments": segments, "conversions": conversions,
            "posts": posts, "polls": polls, "seconds": timing[0], "llm_calls": timing[1],
            "cache_hits": timing[2], "stance_trend": trend}

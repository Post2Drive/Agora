"""Turn a report into Markdown and a self-contained, printable HTML page (charts as SVG)."""
from __future__ import annotations

import html
import re

from .analysis import label, money, nice, pct

SEG_COLORS = ["#2f6f8f", "#c46b2d", "#7a5aa6", "#3d8b5a", "#b8456b", "#8a7a2e", "#3f7fbf", "#a0522d"]


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _cite_html(text: str) -> str:
    return re.sub(r"\[p(\d+)\]", r'<a class="cite" href="#q\1">[p\1]</a>', _e(text))


# ------------------------------------------------------------------ markdown
def to_markdown(r: dict) -> str:
    a = r["analysis"]
    lines = [f"# {r['title']}", "",
             f"_Agora simulation report · {r['generated']} · model {r['model']}_", ""]
    for s in r["sections"]:
        lines += [f"## {s['title']}", "", s["text"], ""]
        if s["key"] == "summary" and a.get("choice"):
            c = a["choice"]
            lines += ["| Option | Share | ", "|---|---:|"] + [f"| {o} | {pct(v)} |" for o, v in
                                                          sorted(c["result"].items(), key=lambda x: -x[1])]
            lines += [f"\nTurnout {pct(c['turnout'])}; based on {c['basis']}, weighted to the electorate.", ""]
        if s["key"] == "summary" and a["funnel"]:
            lines += ["| Action | People | Eligible | Rate |", "|---|---:|---:|---:|"]
            lines += [f"| {f['label']} | {f['count']} | {f['eligible']} | {pct(f['rate'])} |" for f in a["funnel"]]
            lines.append("")
        if s["key"] == "opinion":
            lines += ["| Group | Start | End | Change |", "|---|---:|---:|---:|"]
            lines += [f"| {nice(g)} | {d.get('start', 0):+.2f} | {d['end']:+.2f} | {d['change']:+.2f} |"
                      for g, d in a["opinion"]["segments"].items()]
            lines.append("")
    if r["quotes"]:
        lines += ["## Quoted posts", ""] + [f"- {q}" for q in r["quotes"].values() if q] + [""]
    lines += ["---", "Numbers come from the simulation; opinion starting points and action likelihoods "
              "are assumptions until calibrated with real data."]
    return "\n".join(lines)


# ------------------------------------------------------------------ charts
def _line_chart(series, ymin, ymax, xmax, w=640, h=230) -> str:
    L, R, T, B = 44, 10, 10, 26
    iw, ih = w - L - R, h - T - B
    X = lambda x: L + (x / xmax if xmax else 0) * iw
    Y = lambda y: T + ih - (y - ymin) / ((ymax - ymin) or 1) * ih
    g = []
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        g.append(f'<line x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" class="tick" text-anchor="end">{v:.1f}</text>')
    for i in range(5):
        x = xmax * i / 4
        g.append(f'<text x="{X(x):.1f}" y="{h - 6}" class="tick" text-anchor="middle">{x:.0f}</text>')
    for name, color, pts in series:
        if pts:
            p = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
            g.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{p}"/>')
    legend = "".join(f'<span><i style="background:{c}"></i>{_e(n)}</span>' for n, c, _ in series)
    return f'<svg viewBox="0 0 {w} {h}" role="img">{"".join(g)}</svg><div class="legend">{legend}</div>'


def _dist_bars(start: dict, end: dict) -> str:
    def bar(d, lab):
        if not d:
            return ""
        parts = [("against", "var(--bad)"), ("undecided", "var(--mid)"), ("for", "var(--good)")]
        segs = "".join(f'<i style="width:{d.get(k, 0) * 100:.1f}%;background:{c}" title="{k} {pct(d.get(k, 0))}"></i>'
                       for k, c in parts)
        return (f'<div class="dist"><span>{lab}</span><div class="stack">{segs}</div>'
                f'<span class="small">{pct(d.get("for", 0))} for · {pct(d.get("against", 0))} against</span></div>')
    return bar(start, "Start") + bar(end, "End")


def _funnel_bars(funnel: list[dict]) -> str:
    out = []
    for f in funnel:
        note = f' <span class="pill bad">blocked: {_e(nice(f["blocked_by"]))} rejected</span>' if f["blocked_by"] else ""
        out.append(f'<div class="fn"><div class="fnh"><b>{_e(f["label"])}</b>{note}'
                   f'<span class="spacer"></span><b>{f["count"]:,}</b>&nbsp;of {f["eligible"]:,} '
                   f'({pct(f["rate"])})</div><div class="bar"><i style="width:{min(100, f["rate"] * 100):.1f}%"></i></div>')
        rows = [(g, d) for g, d in f["by_segment"].items() if d["eligible"]]
        if rows:
            out.append('<div class="fnseg">' + "".join(
                f'<span>{_e(nice(g))}: {pct(d["rate"])} <span class="muted">({d["count"]}/{d["eligible"]})</span></span>'
                for g, d in rows) + "</div>")
        out.append("</div>")
    return "".join(out)


# ------------------------------------------------------------------ html
CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b18;--muted:#6d6a62;--line:#e3e0d8;--card:#fff;--sunk:#f1efe9;--accent:#2f5d50;
--good:#3d8b5a;--bad:#b84a4a;--mid:#c9c4b8}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141412;--fg:#ecebe5;--muted:#9d9a90;
--line:#33322c;--card:#1c1c19;--sunk:#24241f;--accent:#7fb8a6;--good:#7fc79a;--bad:#e07a7a;--mid:#4a4840}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 Georgia,"Iowan Old Style",serif}
main{max-width:860px;margin:0 auto;padding:48px 24px 80px}
h1{font:600 30px/1.25 system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:-.02em;margin:0 0 8px}
h2{font:600 20px/1.3 system-ui,-apple-system,"Segoe UI",sans-serif;margin:40px 0 10px;padding-top:16px;border-top:1px solid var(--line)}
h3{font:600 15px system-ui,sans-serif;margin:20px 0 8px}
.meta,.small,.tick,.legend,table,.fnseg,.dist,.pill,.kpi span{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.meta{color:var(--muted);font-size:14px}.muted{color:var(--muted)}.small{font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.kpi b{display:block;font:600 26px system-ui,sans-serif;letter-spacing:-.02em}.kpi span{font-size:13px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0}th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line)}
th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}td.n{text-align:right;font-variant-numeric:tabular-nums}
svg{width:100%;height:auto;display:block}.grid{stroke:var(--line)}.tick{font-size:11px;fill:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted);margin-top:4px}.legend i{display:inline-block;width:12px;height:3px;margin-right:5px;vertical-align:middle;border-radius:2px}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0}
.fn{margin:14px 0}.fnh{display:flex;gap:6px;align-items:baseline;font-family:system-ui,sans-serif;font-size:14px;flex-wrap:wrap}.spacer{flex:1}
.bar{height:10px;background:var(--sunk);border-radius:9px;overflow:hidden;margin:6px 0}.bar i{display:block;height:100%;background:var(--accent)}
.fnseg{display:flex;flex-wrap:wrap;gap:14px;font-size:12.5px}
.dist{display:grid;grid-template-columns:50px 1fr 200px;gap:10px;align-items:center;font-size:13px;margin:6px 0}
.stack{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--sunk)}.stack i{display:block;height:100%}
.pill{font-size:12px;padding:2px 8px;border-radius:99px;background:var(--sunk)}.pill.ok{color:var(--good)}.pill.bad{color:var(--bad)}
a.cite{color:var(--accent);text-decoration:none;font-family:system-ui,sans-serif;font-size:.85em}
.quotes li{margin:8px 0;font-size:14px}.quotes li:target{background:var(--sunk);border-radius:6px}
.note{font-size:13px;color:var(--muted);border-left:3px solid var(--line);padding-left:12px;margin-top:40px;font-family:system-ui,sans-serif}
@media print{body{background:#fff;color:#000}h2{break-after:avoid}.chart,.kpi{break-inside:avoid}}
"""


def to_html(r: dict) -> str:
    a = r["analysis"]
    o, op = a["overview"], a["opinion"]
    c = a.get("choice") or {}
    kpis = ""
    if c:
        for opt, v in sorted(c["result"].items(), key=lambda x: -x[1]):
            kpis += f'<div class="kpi"><b>{pct(v)}</b><span>{_e(opt)}{" · leads" if opt == c["leader"] else ""}</span></div>'
        kpis += f'<div class="kpi"><b>{pct(c["turnout"])}</b><span>turnout ({c["votes_cast"]:,} votes)</span></div>'
    kpis += "".join(f'<div class="kpi"><b>{f["count"]:,}</b><span>{_e(f["label"])} · {pct(f["rate"])} of eligible</span></div>'
                    for f in a["funnel"])
    if not c:
        kpis += f'<div class="kpi"><b>{op["start"].get("mean", 0):+.2f} → {op["end"].get("mean", 0):+.2f}</b><span>average opinion (−1 to +1)</span></div>'
    if a["economics"]:
        e = a["economics"]
        kpis += f'<div class="kpi"><b>{money(e["net"], e["currency"])}</b><span>net value (cost {money(e["total_cost"], e["currency"])})</span></div>'
    segs = list(op["segments"])
    trend = [(nice(g), SEG_COLORS[i % len(SEG_COLORS)], [(rd + 1, v) for rd, gg, v in op["trend"] if gg == g])
             for i, g in enumerate(segs)]
    body = []
    keys = {s["key"] for s in r["sections"]}
    opinion_html = (f'<div class="chart"><h3>Opinion by group over time <span class="small muted">(round)</span></h3>'
                    f'{_line_chart(trend, -1, 1, max(1, o["rounds_done"]))}</div>'
                    f'<div class="chart"><h3>For, undecided, against</h3>{_dist_bars(op["start"], op["end"])}</div>'
                    "<table><thead><tr><th>Group</th><th>People</th><th>Start</th><th>End</th><th>Change</th></tr></thead><tbody>"
                    + "".join(f'<tr><td>{_e(nice(g))}</td><td class="n">{d["agents"]:,}</td><td class="n">{d.get("start", 0):+.2f}</td>'
                              f'<td class="n">{d["end"]:+.2f}</td><td class="n">{d["change"]:+.2f}</td></tr>'
                              for g, d in op["segments"].items()) + "</tbody></table>")
    choice_html = ""
    if c:
        cols = [SEG_COLORS[i % len(SEG_COLORS)] for i in range(len(c["options"]))]
        series = [(o, cols[i], [(t["round"] + 1, t["weighted"][o]) for t in c["trend"]]) for i, o in enumerate(c["options"])]
        bars = "".join(f'<div class="fn"><div class="fnh"><b>{_e(o)}</b><span class="spacer"></span><b>{pct(c["result"][o])}</b></div>'
                       f'<div class="bar"><i style="width:{c["result"][o] * 100:.1f}%;background:{cols[i]}"></i></div></div>'
                       for i, o in enumerate(sorted(c["options"], key=lambda o: -c["result"][o])))
        seg_rows = "".join(f'<tr><td>{_e(nice(g))}</td><td class="n">{pct(d["weight"])}</td><td class="n">{pct(d["turnout"])}</td>'
                           + "".join(f'<td class="n">{pct(d["shares"][o])}</td>' for o in c["options"]) + "</tr>"
                           for g, d in c["by_segment"].items())
        choice_html = (f'<div class="chart"><h3>{_e(c["question"])} <span class="small muted">({_e(c["basis"])}, weighted to the electorate)</span></h3>{bars}</div>'
                       f'<div class="chart"><h3>Vote intention over time <span class="small muted">(decided voters, weighted)</span></h3>'
                       f'{_line_chart(series, 0, 1, max(1, o["rounds_done"]))}</div>'
                       '<table><thead><tr><th>Group</th><th>Weight</th><th>Turnout</th>'
                       + "".join(f"<th>{_e(x)}</th>" for x in c["options"]) + f"</tr></thead><tbody>{seg_rows}</tbody></table>")
    range_html = ""
    f = a.get("forecast") or {}
    if f:
        mc = f["monte_carlo"]
        rows = "".join(f'<tr><td>{_e(k.split(":", 1)[-1].replace("_", " "))}</td>'
                       + "".join(f'<td class="n">{(pct(v[q]) if (k.startswith("share:") or k in ("turnout", "in_favour")) else f"{v[q]:,.0f}" if k.startswith("action:") else f"{v[q]:+.2f}")}</td>' for q in ("p10", "p50", "p90"))
                       + "</tr>" for k, v in mc["summary"].items())
        range_html = (f'<table><thead><tr><th>Outcome</th><th>Low (10%)</th><th>Middle</th><th>High (90%)</th></tr></thead><tbody>{rows}</tbody></table>'
                      f'<p class="small muted">{mc["runs"]} runs with varied assumptions{" after calibration" if f.get("calibrated") else ""}.</p>')
        if mc.get("win_probability"):
            range_html += '<div class="chart"><h3>Chance of winning</h3>' + "".join(
                f'<div class="fn"><div class="fnh"><b>{_e(o)}</b><span class="spacer"></span><b>{pct(w)}</b></div>'
                f'<div class="bar"><i style="width:{w * 100:.1f}%"></i></div></div>'
                for o, w in sorted(mc["win_probability"].items(), key=lambda x: -x[1])) + "</div>"
        sens = f.get("sensitivity")
        if sens and sens["levers"]:
            top = sens["levers"][:8]
            mx = max(r["swing"] for r in top) or 1
            range_html += (f'<div class="chart"><h3>What moves {_e(sens["outcome"].split(":", 1)[-1])} most</h3>' + "".join(
                f'<div class="fn"><div class="fnh"><span>{_e(r["lever"])}</span><span class="spacer"></span>'
                f'<span class="small muted">{r["low"]:.3g} → {r["high"]:.3g}</span></div>'
                f'<div class="bar"><i style="width:{r["swing"] / mx * 100:.1f}%"></i></div></div>' for r in top) + "</div>")
    drivers_html = ""
    if a["influencers"]:
        drivers_html = ("<table><thead><tr><th>Voice</th><th>Group</th><th>Posts</th><th>Reactions</th><th>Shared</th><th>Opinion</th></tr></thead><tbody>"
                        + "".join(f'<tr><td>{_e(i["name"])} <span class="muted small">@{_e(i["handle"])}</span></td><td>{_e(nice(i["segment"]))}</td>'
                                  f'<td class="n">{i["posts"]}</td><td class="n">{i["engagement"]:,}</td><td class="n">{i["shared"]}</td>'
                                  f'<td class="n">{i["stance"]:+.2f}</td></tr>' for i in a["influencers"][:8]) + "</tbody></table>")
        plats = o["posts_by_platform"]
        if plats:
            drivers_html += "<p class='small muted'>Posts per app: " + ", ".join(
                f"{_e(label(p))} {n}" for p, n in sorted(plats.items(), key=lambda x: -x[1])) + "</p>"
    decisions_html = ""
    for d in a["decisions"]:
        decisions_html += (f'<h3>{_e(nice(d["name"]))} <span class="pill {"ok" if d["passed"] else "bad"}">'
                           f'{"approved" if d["passed"] else "rejected"} {d["yes"]}–{d["no"]}</span></h3>')
        decisions_html += ("<table><tbody>" + "".join(
            f'<tr><td>{_e(v["name"])}</td><td>{v["vote"]}</td><td class="small">{_e(v["reason"])}</td></tr>'
            for v in d["votes"][:12]) + "</tbody></table>")
    for i, s in enumerate(r["sections"]):
        body.append(f'<h2 id="{_e(s["key"])}-{i}">{_e(s["title"])}</h2>')
        body += [f"<p>{_cite_html(p)}</p>" for p in s["text"].split("\n") if p.strip()]
        if i == 0:
            body.append(f'<div class="kpis">{kpis}</div>')
            if c:
                body.append(choice_html)
            if a["funnel"]:
                body.append(f'<div class="chart"><h3>Real-world actions</h3>{_funnel_bars(a["funnel"])}</div>')
            if "opinion" not in keys and not c:
                body.append(opinion_html)
        elif s["key"] == "opinion":
            body.append(opinion_html)
        elif s["key"] == "choice" and c and i != 0:
            pass
        elif s["key"] == "drivers":
            body.append(drivers_html)
        elif s["key"] == "range":
            body.append(range_html)
        elif s["key"] == "decisions":
            body.append(decisions_html)
    if "decisions" not in keys and decisions_html:
        body.append(f'<h2 id="decision-detail">Decision details</h2>{decisions_html}')
    if "range" not in keys and range_html:
        body.append(f'<h2 id="range-detail">Range of outcomes</h2>{range_html}')
    if "drivers" not in keys and drivers_html:
        body.append(f'<h2 id="voices-detail">Most influential voices</h2>{drivers_html}')
    research = r.get("research") or []
    if research:
        body.append('<h2 id="research">How this report was researched</h2><ol class="quotes">' + "".join(
            f'<li><b>{_e(e["section"])}</b>: {_e(e["tool"])} '
            f'<span class="muted">{_e(e["input"].get("query") or e["input"].get("name") or e["input"].get("question") or "")}</span></li>'
            for e in research) + "</ol>")
    quotes = "".join(f'<li id="q{pid}">{_e(q)}</li>' for pid, q in r["quotes"].items() if q)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Agora report</title><style>{CSS}</style></head>
<body><main><div class="meta">Agora simulation report · {_e(r["generated"])} · model {_e(r["model"])}</div>
<h1>{_e(r["title"])}</h1>
<p class="meta">{o["days"]} simulated days · {o["llm_voices"]} AI voices · {o["crowd"]:,} crowd agents · {o["posts"]:,} posts · {o["shares"]:,} shares and forwards</p>
{"".join(body)}
{f'<h2 id="quotes">Quoted posts</h2><ol class="quotes">{quotes}</ol>' if quotes else ""}
<p class="note">Every number on this page is computed from the simulation. The text is written by a language model from
those numbers; sentences with numbers it was not given are removed. Starting opinions and action likelihoods are
assumptions until calibrated with real data — read results as comparisons and directions, not exact forecasts.</p>
</main></body></html>"""

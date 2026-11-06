"""Real-world data that calibrates a simulation.

observations.csv - what actually happened, over time. Either long form:
    day,metric,value[,segment]          e.g.  2,register_lakeview,41
or wide form:
    day,register_lakeview,buy           e.g.  2,41,0
`day` is the day of the campaign (1 = first simulated day); a `date` column
(YYYY-MM-DD) works too and is converted using the scenario's start date.
Metrics are action names from the scenario (cumulative counts unless a `kind` column
says `new`), or `opinion` (average on -1..+1, or a 1-5 rating which is converted).

reviews.csv - what people said before the simulation, to set starting opinions:
    text[,rating][,segment]
Ratings 1-5 are used directly; without ratings a small word list scores the text.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

POS = set("""good great love loved excellent amazing helpful helped better best happy recommend recommended
works worked effective fresh tasty easy useful nice wonderful satisfied trust trusted improved""".split())
NEG = set("""bad worse worst hate hated useless waste scam fake expensive costly poor terrible awful
disappointed disappointing side bloating nothing didnt doesnt not never refund problem issue issues""".split())


class DataError(ValueError):
    pass


@dataclass
class Obs:
    day: float
    round: int
    metric: str
    value: float
    segment: str = ""


def _rows(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows]


def _num(v: str, what: str) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except ValueError as e:
        raise DataError(f"'{v}' is not a number ({what})") from e


def load_observations(path_or_text, sc) -> list[Obs]:
    text = Path(path_or_text).read_text(encoding="utf-8-sig") if isinstance(path_or_text, Path) else str(path_or_text)
    rows = _rows(text)
    if not rows:
        raise DataError("No rows found.")
    cols = set(rows[0])
    names = {c.name for c in sc.conversions}
    options = {o.lower(): o for o in (sc.choice.options if sc.choice else [])}
    start = sc.start.date() if isinstance(sc.start, datetime) else sc.start
    per_day = 24 / sc.round_hours

    def day_of(r) -> float:
        if r.get("day"):
            return _num(r["day"], "day")
        if r.get("date"):
            try:
                d = date.fromisoformat(r["date"][:10])
            except ValueError as e:
                raise DataError(f"'{r['date']}' is not a date like 2026-11-20") from e
            return (d - start).days + 1
        raise DataError("Each row needs a 'day' or 'date' column.")

    out: list[Obs] = []
    if "metric" in cols and "value" in cols:              # long form
        items = [(r, r["metric"], r["value"]) for r in rows]
    else:                                                  # wide form
        metric_cols = [c for c in cols if c not in ("day", "date", "segment", "kind")]
        items = [(r, c, r[c]) for r in rows for c in metric_cols if r.get(c) not in ("", None)]
    new_flags = {}
    for r, metric, value in items:
        raw_metric = metric.strip()
        low = raw_metric.lower()
        if low.startswith("share:"):
            low = low[6:].strip()
        if low in options:                                   # poll share for an option
            metric = f"share:{options[low]}"
        else:
            metric = re.sub(r"[^a-z0-9_]+", "_", low).strip("_")
            if metric not in names and metric not in ("opinion", "opinion_for", "turnout"):
                allowed = sorted(names) + ["opinion", "opinion_for"] + (
                    ["turnout"] + [o for o in options.values()] if options else [])
                raise DataError(f"Unknown metric '{raw_metric}'. Use one of: {', '.join(allowed)}")
        d = day_of(r)
        v = _num(value, metric)
        if metric == "opinion" and v > 1:                  # 1-5 rating -> -1..+1
            v = (v - 3) / 2
        if metric in ("opinion_for", "turnout") or metric.startswith("share:"):
            if v > 1:                                      # percentage
                v = v / 100
        seg = r.get("segment", "")
        if seg and seg not in {s.name for s in sc.segments}:
            raise DataError(f"Unknown segment '{seg}'")
        rnd = max(0, min(sc.rounds - 1, int(round(d * per_day)) - 1))
        out.append(Obs(day=d, round=rnd, metric=metric, value=v, segment=seg))
        if r.get("kind", "").lower() == "new":
            new_flags[metric] = True
    # daily "new" counts -> cumulative, so everything is compared the same way
    for metric in new_flags:
        total = 0.0
        for o in sorted((o for o in out if o.metric == metric), key=lambda o: o.day):
            total += o.value
            o.value = total
    out.sort(key=lambda o: (o.metric, o.day))
    return out


def score_text(text: str) -> float:
    w = re.findall(r"[a-z']+", text.lower().replace("n't", "nt"))
    p = sum(x in POS for x in w)
    n = sum(x in NEG for x in w)
    return 0.0 if p + n == 0 else (p - n) / (p + n)


def load_reviews(path_or_text, sc) -> dict:
    """Summarise reviews into starting opinions: {segment or '*': (mean, sd, n)}."""
    text = Path(path_or_text).read_text(encoding="utf-8-sig") if isinstance(path_or_text, Path) else str(path_or_text)
    rows = _rows(text)
    if not rows:
        raise DataError("No rows found.")
    segs = {s.name for s in sc.segments}
    groups: dict[str, list[float]] = {}
    for r in rows:
        if r.get("rating"):
            v = (min(5.0, max(1.0, _num(r["rating"], "rating"))) - 3) / 2
        elif r.get("text") or r.get("review") or r.get("comment"):
            v = score_text(r.get("text") or r.get("review") or r.get("comment"))
        else:
            continue
        g = r.get("segment", "") or "*"
        if g != "*" and g not in segs:
            raise DataError(f"Unknown segment '{g}'")
        groups.setdefault(g, []).append(v)
    out = {}
    for g, vals in groups.items():
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0.3
        out[g] = (round(m, 3), round(max(0.1, min(0.6, sd)), 3), len(vals))
    return out

"""Fast runs for calibration and forecasting.

A full run with a local model can take hours, so fitting and Monte Carlo use fast
runs: the same engine, the same crowd and opinion dynamics, but the few LLM voices are
replaced by rule-based stand-ins (the mock backend). Crowd agents are 95%+ of the
population, so counts and opinion shifts are driven by the same mechanics; what the
fast runs do not capture is the specific wording and arguments of the voices.
"""
from __future__ import annotations

import copy
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..sim.engine import Simulation


@dataclass
class Trajectory:
    rounds: int
    conversions: dict[str, list[int]]           # cumulative per round
    opinion: list[float]                        # population mean per round
    opinion_for: list[float]                    # share > 0.2 per round
    seg_opinion: dict[str, list[float]]
    eligible: dict[str, int]

    def final(self, name: str) -> int:
        return self.conversions[name][-1] if self.conversions.get(name) else 0


def _clean(sc: dict) -> dict:
    d = copy.deepcopy(sc)
    d.pop("raw", None)
    d["llm"] = {"backend": "mock", "cache": False}
    return d


def simulate(sc: dict, seed: int, rounds: int | None = None, workdir: Path | None = None) -> Trajectory:
    d = _clean(sc)
    d["seed"] = int(seed)
    if rounds:
        d["rounds"] = min(int(rounds), int(d["rounds"]))
    tmp = Path(tempfile.mkdtemp(prefix="agora-fast-", dir=workdir))
    try:
        (tmp / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True),
                                           encoding="utf-8")
        sim = Simulation(tmp)
        try:
            sim.prepare()
            sim.run()
        finally:
            sim.close()
        return read_trajectory(tmp, d)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_trajectory(project: Path, d: dict) -> Trajectory:
    db = sqlite3.connect(project / "agora.db")
    try:
        n = db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
        names = [c["name"] for c in d.get("conversions", [])]
        conv = {k: [0] * n for k in names}
        for r, name, c in db.execute("SELECT round, name, COUNT(*) FROM conversions GROUP BY round, name"):
            if name in conv and 0 <= r < n:
                conv[name][r] += c
        for k in conv:
            tot = 0
            for i in range(n):
                tot += conv[k][i]
                conv[k][i] = tot
        op = [0.0] * n
        opf = [0.0] * n
        for r, m, f in db.execute(
                "SELECT o.round, AVG(o.stance), AVG(o.stance > 0.2) FROM opinions o JOIN agents a "
                "ON a.id = o.agent WHERE a.kind != 'account' AND o.round >= 0 GROUP BY o.round"):
            if r < n:
                op[r], opf[r] = m, f
        seg: dict[str, list[float]] = {}
        for r, g, m in db.execute(
                "SELECT o.round, a.segment, AVG(o.stance) FROM opinions o JOIN agents a ON a.id = o.agent "
                "WHERE a.kind != 'account' AND o.round >= 0 GROUP BY o.round, a.segment"):
            seg.setdefault(g, [0.0] * n)
            if r < n:
                seg[g][r] = m
        from ..report.analysis import Analysis
        an = Analysis(project)
        try:
            eligible = {f["name"]: f["eligible"] for f in an.funnel()}
        finally:
            an.close()
    finally:
        db.close()
    return Trajectory(n, conv, op, opf, seg, eligible)


def averaged(sc: dict, seeds: list[int], rounds: int | None = None) -> Trajectory:
    """Mean trajectory over several seeds (smooths randomness while fitting)."""
    ts = [simulate(sc, s, rounds) for s in seeds]
    n = min(t.rounds for t in ts)
    avg = lambda arrs: [sum(a[i] for a in arrs) / len(arrs) for i in range(n)]
    return Trajectory(
        n, {k: avg([t.conversions[k] for t in ts]) for k in ts[0].conversions},
        avg([t.opinion for t in ts]), avg([t.opinion_for for t in ts]),
        {g: avg([t.seg_opinion[g] for t in ts if g in t.seg_opinion]) for g in ts[0].seg_opinion},
        ts[0].eligible)

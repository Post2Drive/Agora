"""Daily rhythm, active hours and feed ranking settings."""
import sqlite3

import yaml

from agora.sim.engine import Simulation
from agora.sim.timing import Rhythm
from conftest import make_project


def test_rhythm_and_active_hours():
    r = Rhythm({"peak_hours": [20], "peak": 2.0})
    assert r.factor(20) == 2.0 and r.factor(3) < 0.1
    assert r.factor(12, [8, 18]) == r.factor(12)
    assert r.factor(20, [8, 18]) < r.factor(20) * 0.1
    assert r.factor(1, [22, 6]) == r.factor(1)              # overnight window
    assert Rhythm({"by_hour": [1.0] * 24}).factor(4) == 1.0


def test_minutes_per_round_and_validation(tmp_path):
    from agora import scenario
    d = yaml.safe_load((make_project(tmp_path) / "scenario.yaml").read_text())
    d.pop("round_hours")
    d["minutes_per_round"] = 60
    assert scenario.from_dict(d).round_hours == 1.0
    d["feeds"] = {"reddit": {"recency": 1}}
    import pytest
    with pytest.raises(scenario.ScenarioError, match="not a feed app"):
        scenario.from_dict(d)


def test_echo_chamber_setting_changes_what_people_see(tmp_path):
    import numpy as np
    from agora.sim.platforms import FeedIndex
    p = make_project(tmp_path, "w", rounds=30)
    s = Simulation(p)
    s.prepare()
    s.run()
    w = s.world

    def closeness(echo):
        idx = FeedIndex(w, 30 * 4.0, feeds={"x": {"echo_chamber": echo, "relevance": 0.0}})
        vals = []
        for a in w.agents:
            if "x" not in a.platforms:
                continue
            for pid in idx._feed("x", a, 2, np.random.default_rng(a.id)):
                vals.append(1 - abs(w.posts[w.posts[pid].root].stance - a.stance) / 2)
        return sum(vals) / len(vals)

    assert closeness(1.0) > closeness(0.0)
    s.close()


def test_active_hours_respected(tmp_path):
    d = yaml.safe_load((make_project(tmp_path, "tmp") / "scenario.yaml").read_text())
    for s in d["segments"]:
        s["active_hours"] = [9, 17]
    p = make_project(tmp_path, "day", segments=d["segments"], rounds=24)
    s = Simulation(p)
    s.prepare()
    s.run()
    s.close()
    db = sqlite3.connect(p / "agora.db")
    rows = db.execute("SELECT r.sim_time, r.active FROM rounds r").fetchall()
    night = [n for t, n in rows if int(t[11:13]) < 6]
    day = [n for t, n in rows if 9 <= int(t[11:13]) < 17]
    assert max(night) < min(day)

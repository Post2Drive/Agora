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


def _agree_share(p):
    """How often LLM voices liked posts close to their own view."""
    db = sqlite3.connect(p / "agora.db")
    rows = db.execute("SELECT ABS(po.stance - s.stance) FROM engagements e JOIN posts po ON po.id = e.post "
                      "JOIN agent_state s ON s.id = e.agent WHERE e.type='like' AND po.platform IN ('x','instagram','facebook')").fetchall()
    return sum(d < 0.5 for (d,) in rows) / max(1, len(rows))


def test_echo_chamber_setting_changes_what_people_see(tmp_path):
    feeds = {k: {"echo_chamber": 0.0} for k in ("x", "instagram", "facebook", "youtube")}
    strong = {k: {"echo_chamber": 1.0} for k in ("x", "instagram", "facebook", "youtube")}
    a = make_project(tmp_path, "open", feeds=feeds, rounds=30)
    b = make_project(tmp_path, "echo", feeds=strong, rounds=30)
    for p in (a, b):
        s = Simulation(p)
        s.prepare()
        s.run()
        s.close()
    assert _agree_share(b) > _agree_share(a)


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

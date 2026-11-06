import sqlite3

import pytest

from agora.sim.engine import Simulation
from conftest import make_project

TABLES = ["agents", "agent_state", "follows", "memberships", "posts", "engagements",
          "conversions", "opinions", "thoughts", "polls", "poll_results", "event_log"]


def dump(project):
    db = sqlite3.connect(project / "agora.db")
    out = {t: sorted(db.execute(f"SELECT * FROM {t}").fetchall(), key=repr) for t in TABLES}
    out["rounds"] = db.execute("SELECT round, sim_time, active FROM rounds ORDER BY round").fetchall()
    db.close()
    return out


def run(project, rounds=None):
    sim = Simulation(project)
    sim.prepare()
    sim.run(rounds=rounds)
    sim.close()


def test_full_run_produces_everything(project):
    run(project)
    d = dump(project)
    assert len(d["rounds"]) == 72
    kinds = {r[8] for r in d["posts"]}
    assert {"post", "reply", "repost"} <= kinds
    platforms = {r[3] for r in d["posts"]}
    assert {"x", "reddit", "whatsapp", "instagram", "facebook", "facebook_groups"} <= platforms
    assert {r[0] for r in d["poll_results"]} == {"lakeview_approval", "palmgrove_approval"}
    names = {r[2] for r in d["conversions"]}
    assert names & {"register_lakeview", "register_palmgrove"}
    assert any(r[1] == "experience" for r in d["event_log"])


def test_same_seed_same_result(tmp_path):
    a, b = make_project(tmp_path, "a"), make_project(tmp_path, "b")
    run(a)
    run(b)
    assert dump(a) == dump(b)


def test_different_seed_differs(tmp_path):
    a, b = make_project(tmp_path, "a"), make_project(tmp_path, "b", seed=7)
    run(a, 10)
    run(b, 10)
    assert dump(a)["posts"] != dump(b)["posts"]


def test_resume_matches_uninterrupted(tmp_path):
    whole, parts = make_project(tmp_path, "whole"), make_project(tmp_path, "parts")
    run(whole)
    run(parts, 5)
    run(parts, 20)
    run(parts)
    assert dump(whole) == dump(parts)


def test_crash_mid_round_leaves_no_trace_and_resumes(tmp_path, monkeypatch):
    whole, crashy = make_project(tmp_path, "whole"), make_project(tmp_path, "crashy")
    run(whole)

    sim = Simulation(crashy)
    sim.prepare()
    real_step = sim.step

    def boom(r):
        out = real_step(r)
        if r == 20:
            raise KeyboardInterrupt      # e.g. laptop lid closed
        return out

    monkeypatch.setattr(sim, "step", boom)
    with pytest.raises(KeyboardInterrupt):
        sim.run()
    assert sim.store.last_round() == 19
    sim.close()

    run(crashy)                          # fresh process: reload from disk and finish
    assert dump(whole) == dump(crashy)


def test_scenario_change_blocks_resume(project):
    run(project, 3)
    p = project / "scenario.yaml"
    p.write_text(p.read_text().replace("seed: 42", "seed: 43"))
    sim = Simulation(project)
    with pytest.raises(RuntimeError, match="changed"):
        sim.prepare()
    sim.close()


def test_rejected_poll_blocks_announcement(tmp_path):
    p = make_project(tmp_path, "strict")
    import yaml
    d = yaml.safe_load((p / "scenario.yaml").read_text())
    for e in d["events"]:
        if e["type"] == "poll":
            e["threshold"] = 1.01        # impossible to pass
    (p / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    run(p)
    d = dump(p)
    assert all(r[4] == 0 for r in d["poll_results"])
    assert not d["conversions"]          # registration never opened
    assert any(r[1] == "skipped" for r in d["event_log"])

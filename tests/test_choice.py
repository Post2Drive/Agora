"""Elections and other multi-option choices."""
import sqlite3
from pathlib import Path

import pytest
import yaml

from agora import scenario as scenario_mod
from agora.report.analysis import Analysis
from agora.report.writer import write_report
from agora.sim.engine import Simulation

ELECTION = Path(__file__).resolve().parents[1] / "agora" / "examples" / "election" / "scenario.yaml"


def project(tmp, name="el", **over):
    d = yaml.safe_load(ELECTION.read_text())
    d["population"] = {"llm_agents": 10, "crowd_agents": 400}
    d["llm"] = {"backend": "mock"}
    for items in d["spaces"].values():
        for sp in items:
            sp["size"] = min(sp["size"], 120)
    d.update(over)
    p = tmp / name
    p.mkdir()
    (p / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    return p


def run(p):
    s = Simulation(p)
    s.prepare()
    s.run()
    s.close()


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    p = project(tmp_path_factory.mktemp("choice"))
    run(p)
    return p


def test_validation():
    d = yaml.safe_load(ELECTION.read_text())
    d["segments"][0]["leaning"]["Nobody"] = 0.3
    with pytest.raises(scenario_mod.ScenarioError, match="unknown option"):
        scenario_mod.from_dict(d)
    d = yaml.safe_load(ELECTION.read_text())
    d["choice"]["options"] = ["Only one"]
    for e in d["events"]:
        e.pop("shift", None)
    for x in d["segments"] + d["accounts"]:
        x.pop("leaning", None)
    with pytest.raises(scenario_mod.ScenarioError, match="two different options"):
        scenario_mod.from_dict(d)


def test_votes_once_and_only_in_window(ran):
    db = sqlite3.connect(ran / "agora.db")
    sc = scenario_mod.load(ran / "scenario.yaml")
    rows = db.execute("SELECT round, agent, option FROM choices").fetchall()
    assert rows
    assert all(sc.choice.open_round <= r <= sc.choice.close_round for r, _, _ in rows)
    assert len({a for _, a, _ in rows}) == len(rows)
    assert {o for _, _, o in rows} <= set(sc.choice.options)
    assert not db.execute("SELECT 1 FROM choices c JOIN agents a ON a.id=c.agent WHERE a.kind='account'").fetchall()
    # posts carry the option they are about
    assert db.execute("SELECT COUNT(*) FROM posts WHERE kind='post' AND option != ''").fetchone()[0] > 0


def test_analysis_weighting(ran):
    an = Analysis(ran)
    c = an.choice()
    an.close()
    assert c["status"] == "final" and c["basis"] == "votes"
    assert abs(sum(c["weighted_share"].values()) - 1) < 0.01 and abs(sum(c["raw_share"].values()) - 1) < 0.01
    assert c["leader"] == max(c["result"], key=c["result"].get)
    # weighting is by the real electorate: check by hand
    tw = {g: d["weight"] * d["turnout"] for g, d in c["by_segment"].items()}
    z = sum(tw.values())
    for o in c["options"]:
        manual = sum(tw[g] / z * d["shares"][o] for g, d in c["by_segment"].items())
        assert abs(manual - c["weighted_share"][o]) < 0.002
    assert len(c["trend"]) == 80


def test_turnout_habit_matters(tmp_path):
    d = yaml.safe_load(ELECTION.read_text())
    segs = d["segments"]
    for s in segs:
        s["turnout"] = 2.0 if s["name"] == "retirees" else -2.0
    p = project(tmp_path, "habit", segments=segs)
    run(p)
    an = Analysis(p)
    c = an.choice()
    an.close()
    assert c["by_segment"]["retirees"]["turnout"] > max(d["turnout"] for g, d in c["by_segment"].items() if g != "retirees")


def test_news_shock_moves_preferences(tmp_path):
    def final_share(shift):
        d = yaml.safe_load(ELECTION.read_text())
        for e in d["events"]:
            e.pop("shift", None)
        d["events"].append({"at_round": 5, "type": "news", "text": "Big scandal", "shift": shift})
        p = project(tmp_path, f"shock{len(list(tmp_path.iterdir()))}", events=d["events"], rounds=20,
                    choice={**d["choice"], "open_round": 10, "close_round": 19})
        run(p)
        an = Analysis(p)
        c = an.choice()
        an.close()
        return c["trend"][-1]["weighted"]["Daniel Okafor"]
    assert final_share({"Daniel Okafor": -0.6}) < final_share({"Daniel Okafor": 0.0})


def test_report_has_election_section(ran):
    from agora.llm import make_backend
    r = write_report(ran, make_backend({"backend": "mock"}))
    keys = [s["key"] for s in r["sections"]]
    assert "choice" in keys and "opinion" not in keys
    html = (ran / "report" / "report.html").read_text()
    assert "Vote intention over time" in html and "Meera Pillai" in html

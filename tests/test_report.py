"""Analysis, report agent (including its guard against invented numbers), interaction."""
import json
import sqlite3

import pytest

from agora.llm import LLMConfig, make_backend
from agora.llm.base import LLMBackend
from agora.report import interact
from agora.report.analysis import Analysis
from agora.report.writer import check, write_report
from agora.sim.engine import Simulation
from conftest import make_project


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    p = make_project(tmp_path_factory.mktemp("rep"), economics={
        "currency": "INR", "cost": {"register_lakeview": 56, "register_palmgrove": 56}, "value": {"buy": 483}})
    sim = Simulation(p)
    sim.prepare()
    sim.run()
    sim.close()
    return p


class Liar(LLMBackend):
    """Writes plausible prose with one made-up number and one made-up citation."""
    name = "liar"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        return ("Most residents warmed to the offer [p0]. Exactly 97.3% of seniors loved it [p999999]. "
                "Registration was strongest among parents.")


def test_analysis_numbers_are_consistent(ran):
    a = Analysis(ran)
    d = a.everything()
    a.close()
    db = sqlite3.connect(ran / "agora.db")
    for f in d["funnel"]:
        n = db.execute("SELECT COUNT(*) FROM conversions WHERE name=?", (f["name"],)).fetchone()[0]
        assert f["count"] == n
        assert f["outside_eligible"] == 0                 # nobody converted who could not
        assert sum(s["count"] for s in f["by_segment"].values()) == n
    lake = next(f for f in d["funnel"] if f["name"] == "register_lakeview")
    members = db.execute("SELECT COUNT(DISTINCT m.agent) FROM memberships m JOIN agents a ON a.id=m.agent "
                         "WHERE m.space='Lakeview Residency Residents' AND a.kind!='account'").fetchone()[0]
    assert lake["eligible"] == members
    buy = next(f for f in d["funnel"] if f["name"] == "buy")
    regs = db.execute("SELECT COUNT(DISTINCT agent) FROM conversions WHERE name LIKE 'register%'").fetchone()[0]
    assert buy["eligible"] == regs                        # buying needs a registration first
    e = d["economics"]
    assert e["total_cost"] == 56 * (lake["count"] + next(f for f in d["funnel"] if f["name"] == "register_palmgrove")["count"])
    assert e["total_value"] == 483 * buy["count"]
    o = d["opinion"]["start"]
    assert abs(o["for"] + o["undecided"] + o["against"] - 1) < 0.01


def test_checker_removes_invented_numbers_and_citations():
    facts = "register: 73 of 260 eligible = 28.1%"
    text = "About 28% registered [p5]. Some 41% of seniors refused [p6]. 73 flats signed up."
    out = check(text, facts, known_posts={5})
    assert "28%" in out and "[p5]" in out and "73 flats" in out
    assert "41%" not in out and "[p6]" not in out


def test_report_with_lying_model(ran):
    r = write_report(ran, Liar())
    for s in r["sections"]:
        assert "97.3" not in s["text"] and "p999999" not in s["text"]
    html = (ran / "report" / "report.html").read_text(encoding="utf-8")
    md = (ran / "report" / "report.md").read_text(encoding="utf-8")
    assert "<script" not in html and "Opinion by group" in html and "₹" in html
    assert md.startswith("# ") and "| Action |" in md


def test_report_without_model_states_numbers(ran):
    r = write_report(ran, None)
    a = r["analysis"]
    lake = next(f for f in a["funnel"] if f["name"] == "register_lakeview")
    assert f"{lake['count']} of {lake['eligible']}" in r["sections"][0]["text"]


def test_chat_interview_ask_history(ran):
    llm = make_backend({"backend": "mock"})
    ppl = interact.people(ran)
    assert ppl and {x["kind"] for x in ppl} <= {"llm", "account"}
    h = next(x["handle"] for x in ppl if x["kind"] == "llm")
    interact.chat(ran, llm, h, "Did you register?")
    r = interact.chat(ran, llm, h, "Why?")
    assert r["reply"]
    assert [c["role"] for c in interact.profile(ran, h)["chat"]] == ["user", "agent", "user", "agent"]
    seniors = [x for x in ppl if x["segment"] == "senior_residents" and x["kind"] == "llm"]
    iv = interact.interview(ran, llm, "Would you buy?", segment="senior_residents", n=3)
    assert len(iv["answers"]) == min(3, len(seniors)) > 0
    assert all(a["segment"] == "senior_residents" for a in iv["answers"])
    assert sum(iv["tally"][k] for k in ("yes", "unsure", "no")) == len(iv["answers"])
    ans = interact.ask(ran, llm, "Which group registered most?")
    assert ans["answer"] and all(f"[p{k}]" in ans["answer"] for k in ans["quotes"])
    assert len(interact.history(ran, "report")) == 2
    with pytest.raises(KeyError):
        interact.profile(ran, "nobody_here")


def test_inject_then_resume(tmp_path):
    p = make_project(tmp_path)
    sim = Simulation(p)
    sim.prepare()
    sim.run(rounds=10)
    sim.close()
    with pytest.raises(ValueError):
        interact.inject(p, {"type": "news", "text": "late"}, at_round=3)       # already happened
    with pytest.raises(ValueError):
        interact.inject(p, {"type": "post", "text": "hi", "account": "ghost"})
    r = interact.inject(p, {"type": "post", "text": "Doctor-reviewed facts", "account": "nutrivance",
                            "platform": "instagram"})
    assert r["round"] == 10
    interact.inject(p, {"type": "news", "text": "A doctor calls probiotics a waste of money."})
    sim = Simulation(p)
    sim.prepare()
    sim.run(rounds=2)
    sim.close()
    db = sqlite3.connect(p / "agora.db")
    log = db.execute("SELECT kind, detail FROM event_log WHERE round = 10").fetchall()
    assert ("news", json.dumps({"text": "A doctor calls probiotics a waste of money."})) in log
    assert db.execute("SELECT COUNT(*) FROM posts WHERE round=10 AND text='Doctor-reviewed facts' "
                      "AND platform='instagram'").fetchone()[0] == 1
    assert len(interact.injected(p)) == 2


def test_fork_and_compare(ran, tmp_path):
    new = interact.fork(ran, tmp_path / "variant", title="Cheaper")
    assert (new / "scenario.yaml").exists() and not (new / "agora.db").exists()
    c = interact.compare([ran, new])
    assert c["columns"][0]["run"] and not c["columns"][1]["run"]
    assert "register_lakeview" in c["actions"]


class Researcher(LLMBackend):
    """Plans a custom outline, uses tools, then writes (with one invented number)."""
    name = "researcher"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))
        self.steps = {}

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        p = messages[-1]["content"]
        if "Plan a prediction report" in p:
            return json.dumps({"sections": [
                {"key": "summary", "title": "Bottom line", "goal": "answer"},
                {"key": "custom", "title": "Why seniors hesitate", "goal": "explain senior doubts"},
                {"key": "voices", "title": "What people said", "goal": "quotes"}]})
        if "Split this research question" in p:
            return json.dumps({"queries": ["seniors doubt", "seniors trust doctor"]})
        if "Tool " in p and "result" in p:
            return json.dumps({"write": "Seniors held back [p0]. A full 63.7% of them distrusted it."})
        title = p.split("\n", 1)[0]
        n = self.steps.get(title, 0)
        self.steps[title] = n + 1
        return json.dumps({"tool": ["insight", "stats"][n % 2], "query": "why seniors hesitate", "name": "opinion"})


def test_report_agent_plans_and_uses_tools(ran):
    r = write_report(ran, Researcher())
    titles = [s["title"] for s in r["sections"]]
    assert titles[0] == "Bottom line" and "Why seniors hesitate" in titles
    assert titles[-1] == "How far to trust this"           # always added
    tools = {e["tool"] for e in r["research"]}
    assert {"insight"} <= tools
    for s in r["sections"]:
        assert "63.7" not in s["text"]
    html = (ran / "report" / "report.html").read_text(encoding="utf-8")
    assert "How this report was researched" in html and "Opinion by group" in html

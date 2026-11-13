"""The planner learns from real runs; retries are counted."""
import pytest
import yaml

from agora import capacity, scenario as scenario_mod
from agora.llm import LLMConfig
from agora.llm.base import LLMBackend
from agora.sim.engine import Simulation
from agora.store import Store

BENCH = {"model": "m", "backend": "local", "levels": {}, "best_parallel": 2, "best_throughput": 2.0,
         "avg_reply_tokens": 100, "measured": "now"}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))


def fake_run(path, rounds=10, calls=5, secs=50.0, hits=0, agents=4):
    st = Store(path / "agora.db")
    for i in range(agents):
        st.db.execute("INSERT INTO agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (i, f"h{i}", "llm", f"A{i}", "seg", "p", "[]", 0.0, 0.5, 0.5, 1.0, 0.5, "{}"))
    for r in range(rounds):
        st.db.execute("INSERT INTO rounds VALUES (?,?,?,?,?,?,datetime('now'))", (r, "t", 2, calls, hits, secs))
    st.db.commit()
    st.close()


def test_observed_speed(tmp_path):
    fake_run(tmp_path)
    o = capacity.observed(tmp_path)
    assert o["calls"] == 50 and abs(o["throughput"] - 0.1) < 1e-9
    assert abs(o["calls_per_person_round"] - 1.25) < 1e-9


def test_too_little_or_cached_runs_are_not_trusted(tmp_path):
    (tmp_path / "a").mkdir()
    fake_run(tmp_path / "a", rounds=2)
    assert capacity.observed(tmp_path / "a") is None
    (tmp_path / "b").mkdir()
    fake_run(tmp_path / "b", hits=40)
    assert capacity.observed(tmp_path / "b") is None
    assert capacity.observed(tmp_path / "nothing") is None


def test_plan_uses_the_study_own_numbers(project, tmp_path):
    fake_run(tmp_path)
    sc = scenario_mod.load(project / "scenario.yaml")
    o = capacity.observed(tmp_path)
    p = capacity.plan(sc, BENCH, observed=o)
    assert p["source"] == "observed"
    assert p["calls"] == int(p["people"] * p["rounds"] * 1.25)
    assert abs(p["seconds"] - p["calls"] / 0.1) < 1e-6


def test_learning_corrects_later_plans(project, tmp_path):
    fake_run(tmp_path)
    sc = scenario_mod.load(project / "scenario.yaml")
    capacity.save_bench("local", "m", dict(BENCH))
    b = capacity.learn("local", "m", capacity.observed(tmp_path))
    assert b["real_factor"] == 0.05                       # real speed was 1/20 of the benchmark
    p = capacity.plan(sc, capacity.load_bench("local", "m"))
    assert abs(p["seconds"] - p["calls"] / (2.0 * 0.05)) < 1e-6
    assert "scaled by" in capacity.describe_source(p, capacity.load_bench("local", "m"), None)


def test_learning_without_a_benchmark_still_works(tmp_path):
    fake_run(tmp_path)
    b = capacity.learn("local", "m2", capacity.observed(tmp_path))
    assert abs(b["best_throughput"] - 0.1) < 1e-6 and capacity.load_bench("local", "m2") is not None


class Flaky(LLMBackend):
    """The first decision reply for each person is garbage; asking again works."""
    name = "flaky"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))
        self.seen = set()

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        if meta.get("task") == "decide":
            key = messages[0]["content"]
            if key not in self.seen:
                self.seen.add(key)
                return "sorry, I cannot answer that"
            return '{"thoughts": "fine", "stance": 0.1, "actions": []}'
        if meta.get("task") == "poll":
            return '{"vote": "yes", "reason": "fine"}'
        return "ok"


def test_retries_are_counted(project):
    p = project / "scenario.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": 8, "crowd_agents": 0}
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    s = Simulation(project)
    s.prepare()
    s.llm = Flaky()
    s.run(rounds=6)
    assert s.retried_replies > 0 and s.bad_replies == 0
    s.close()

"""Benchmark and plan."""
from agora import capacity, scenario as scenario_mod
from agora.llm import make_backend


def test_benchmark_runs_on_the_mock_backend():
    r = capacity.benchmark(make_backend({"backend": "mock"}), levels=(1, 2), say=lambda m: None)
    assert r["best_parallel"] in (1, 2) and r["best_throughput"] > 0 and r["avg_reply_tokens"] >= 1


BENCH = {"best_throughput": 2.0, "best_parallel": 2, "avg_reply_tokens": 100, "measured": "now"}


def test_plan_math(project):
    sc = scenario_mod.load(project / "scenario.yaml")
    a = capacity.plan(sc, BENCH)
    b = capacity.plan(sc, BENCH, scenarios=2)
    assert a["calls"] > 0 and b["calls"] == 2 * a["calls"]
    assert abs(a["seconds"] - a["calls"] / 2.0) < 1e-6
    assert a["source"] == "measured"


def test_presets_grow_with_the_time_budget(project):
    sc = scenario_mod.load(project / "scenario.yaml")
    pr = capacity.plan(sc, BENCH)["presets"]
    assert pr["Quick"]["people"] <= pr["Overnight"]["people"] <= pr["Weekend"]["people"]
    assert pr["Quick"]["people"] >= 1


def test_cost_only_with_prices(project):
    sc = scenario_mod.load(project / "scenario.yaml")
    assert capacity.plan(sc, BENCH)["cost"] is None
    assert capacity.plan(sc, BENCH, price=(1.0, 2.0))["cost"] > 0


def test_rough_estimate_without_a_benchmark(project):
    sc = scenario_mod.load(project / "scenario.yaml")
    p = capacity.plan(sc, None)
    assert p["source"] == "rough" and p["seconds"] > 0

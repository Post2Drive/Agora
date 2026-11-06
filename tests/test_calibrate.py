"""Calibration recovers known parameters; backtest; forecast; data loading."""
import copy

import pytest
import yaml

from agora import scenario as scenario_mod
from agora.calibrate import data as data_mod
from agora.calibrate.fast import simulate
from agora.calibrate.fit import bass_fit, calibrate, known_polls
from agora.calibrate.forecast import monte_carlo, sensitivity
from conftest import DEMO


def small():
    d = yaml.safe_load(DEMO.read_text())
    d["population"] = {"llm_agents": 6, "crowd_agents": 300}
    d["rounds"] = 30
    for items in d["spaces"].values():
        for sp in items:
            sp["size"] = min(sp["size"], 90)
    return d


def test_observation_formats():
    sc = scenario_mod.from_dict(small())
    wide = data_mod.load_observations("day,register_lakeview,buy\n1,4,0\n2,9,1\n", sc)
    long = data_mod.load_observations("day,metric,value\n1,register_lakeview,4\n2,register_lakeview,9\n"
                                      "1,buy,0\n2,buy,1\n", sc)
    assert [(o.metric, o.value) for o in wide] == [(o.metric, o.value) for o in long]
    new = data_mod.load_observations("day,metric,value,kind\n1,buy,2,new\n2,buy,3,new\n", sc)
    assert [o.value for o in new] == [2, 5]                      # daily counts become totals
    dated = data_mod.load_observations("date,buy\n2026-11-17,3\n", sc)
    assert dated[0].day == 2
    op = data_mod.load_observations("day,opinion\n1,4\n", sc)
    assert op[0].value == 0.5                                     # 1-5 rating -> -1..+1
    with pytest.raises(data_mod.DataError):
        data_mod.load_observations("day,unknown\n1,3\n", sc)
    rv = data_mod.load_reviews("text,rating,segment\nloved it,5,senior_residents\nmeh,2,senior_residents\n", sc)
    assert rv["senior_residents"][0] == 0.25 and rv["senior_residents"][2] == 2
    assert data_mod.score_text("great, really helpful") > 0 > data_mod.score_text("waste of money, terrible")


def test_known_polls():
    d = small()
    obs = data_mod.load_observations("day,register_lakeview\n1,4\n", scenario_mod.from_dict(copy.deepcopy(d)))
    assert known_polls(d, obs) == {"lakeview_approval": True}


def test_calibration_recovers_a_known_likelihood():
    d = small()
    truth = copy.deepcopy(d)
    truth["fixed_polls"] = {"lakeview_approval": True, "palmgrove_approval": True}
    for c in truth["conversions"]:
        if c["name"] == "register_lakeview":
            c["base"] = -2.6
    t = simulate(truth, 99)
    rows = "\n".join(f"{day},{t.conversions['register_lakeview'][day * 6 - 1]}" for day in (1, 2, 3))
    obs = data_mod.load_observations("day,register_lakeview\n" + rows, scenario_mod.from_dict(copy.deepcopy(d)))
    res = calibrate(d, obs)
    fitted = next(c for c in res["scenario"]["conversions"] if c["name"] == "register_lakeview")["base"]
    assert abs(fitted - (-2.6)) < 0.6
    assert res["fit"]["score"]["register_lakeview"]["mape"] < 0.25


def test_bass_baseline():
    import numpy as np
    t = np.arange(1, 11, dtype=float)
    m, p, q = 500, 0.02, 0.5
    e = np.exp(-(p + q) * t)
    y = m * (1 - e) / (1 + (q / p) * e)
    pred, info = bass_fit(t[:7], y[:7])
    assert info["model"] == "bass"
    assert abs(float(pred(np.array([10.0]))[0]) - y[-1]) / y[-1] < 0.15


def test_forecast_and_sensitivity():
    d = small()
    d["targets"] = {"register_lakeview": 1}
    mc = monte_carlo(d, runs=4)
    s = mc["summary"]["action:register_lakeview"]
    assert s["p10"] <= s["p50"] <= s["p90"]
    assert 0 <= mc["targets"]["register_lakeview"]["probability"] <= 1
    sens = sensitivity(d, outcome="action:register_lakeview", seeds=(1,))
    assert sens["levers"] and sens["levers"][0]["swing"] >= sens["levers"][-1]["swing"]
    top = [r["lever"] for r in sens["levers"][:3]]
    assert any("register lakeview" in x for x in top)

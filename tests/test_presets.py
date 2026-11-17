import pytest
import yaml

from agora import presets
from agora import scenario as scenario_mod
from conftest import make_project


def test_ten_days_of_campaign_is_80_three_hour_rounds():
    assert presets.round_hours("election_campaign") == 3.0
    assert presets.rounds_for("election_campaign", 10) == 80


def test_apply_sets_pace_on_a_loaded_scenario(tmp_path):
    proj = make_project(tmp_path, "study")
    d = yaml.safe_load((proj / "scenario.yaml").read_text(encoding="utf-8"))
    d.pop("minutes_per_round", None)
    out = presets.apply(d, "market_day", 2)
    sc = scenario_mod.from_dict(out)
    assert sc.round_hours == 0.5
    assert sc.rounds == 96


def test_unknown_preset_and_bad_days_are_refused():
    with pytest.raises(ValueError, match="Unknown preset"):
        presets.round_hours("cricket")
    with pytest.raises(ValueError, match="more than zero"):
        presets.rounds_for("product_launch", 0)

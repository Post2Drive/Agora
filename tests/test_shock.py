import yaml
import pytest

from agora import scenario as scenario_mod
from agora.shock import shock_pair
from conftest import make_project


def test_shock_pair_gives_the_event_to_one_copy_only(tmp_path):
    proj = make_project(tmp_path, "study")
    before = (proj / "scenario.yaml").read_text(encoding="utf-8")
    pair = shock_pair(proj, tmp_path / "pair", text="Major corruption allegation breaks", at_round=3,
                      shift={"stance": -0.1})
    ctrl = scenario_mod.load(tmp_path / "pair" / "control" / "scenario.yaml")
    shock = scenario_mod.load(tmp_path / "pair" / "shock" / "scenario.yaml")
    assert not [e for e in ctrl.events if e.text.startswith("Major corruption")]
    got = [e for e in shock.events if e.text.startswith("Major corruption")]
    assert len(got) == 1 and got[0].round == 3 and got[0].shift == {"stance": -0.1}
    assert pair["round"] == 3
    assert (proj / "scenario.yaml").read_text(encoding="utf-8") == before   # original untouched


def test_shock_pair_refuses_a_round_outside_the_study(tmp_path):
    proj = make_project(tmp_path, "study")
    rounds = scenario_mod.load(proj / "scenario.yaml").rounds
    with pytest.raises(ValueError, match="Round must be"):
        shock_pair(proj, tmp_path / "pair", text="News", at_round=rounds)


def test_shock_pair_refuses_an_unknown_option_in_shift(tmp_path):
    proj = make_project(tmp_path, "study")
    with pytest.raises(ValueError, match="Unknown option"):
        shock_pair(proj, tmp_path / "pair", text="News", at_round=1, shift={"Candidate Z": -0.2})


def test_shock_pair_needs_text(tmp_path):
    proj = make_project(tmp_path, "study")
    with pytest.raises(ValueError, match="Write the news"):
        shock_pair(proj, tmp_path / "pair", text="  ", at_round=1)

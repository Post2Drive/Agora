"""A conversion's `requires` (also spelled `requires_any`) means ANY ONE of the listed conversions, not all."""
import copy
from pathlib import Path

import pytest
import yaml

from agora import scenario as scenario_mod
from agora.scenario import ScenarioError
from agora.sim.engine import Simulation
from conftest import make_project

PACKAGED = Path(scenario_mod.__file__).parent / "examples" / "nutrivance_sampling" / "scenario.yaml"


def _doc():
    return yaml.safe_load(PACKAGED.read_text(encoding="utf-8"))


def _buy(doc):
    return next(c for c in doc["conversions"] if c["name"] == "buy")


def test_demo_uses_the_any_of_spelling():
    buy = _buy(_doc())
    assert "requires_any" in buy and "requires" not in buy


def test_both_spellings_give_the_same_scenario():
    a, b = _doc(), _doc()
    _buy(b)["requires"] = _buy(b).pop("requires_any")
    conv = lambda d: next(c for c in scenario_mod.from_dict(copy.deepcopy(d)).conversions if c.name == "buy")
    assert conv(a).requires == conv(b).requires == ["register_lakeview", "register_palmgrove"]


def test_a_single_name_as_text_is_accepted():
    d = _doc()
    _buy(d)["requires_any"] = "register_lakeview"
    sc = scenario_mod.from_dict(copy.deepcopy(d))
    assert next(c for c in sc.conversions if c.name == "buy").requires == ["register_lakeview"]


def test_giving_both_spellings_is_refused():
    d = _doc()
    _buy(d)["requires"] = ["register_lakeview"]
    with pytest.raises(ScenarioError, match="not both"):
        scenario_mod.from_dict(d)


def test_unknown_name_in_requires_any_is_refused():
    d = _doc()
    _buy(d)["requires_any"] = ["register_lakeview", "nope"]
    with pytest.raises(ScenarioError, match="requires unknown 'nope'"):
        scenario_mod.from_dict(d)


def test_unknown_conversion_field_is_still_refused():
    d = _doc()
    _buy(d)["requires_all"] = ["register_lakeview"]
    with pytest.raises(ScenarioError, match="Unknown field 'requires_all'"):
        scenario_mod.from_dict(d)


@pytest.mark.parametrize("spelling", ["requires", "requires_any"])
def test_a_buyer_needs_only_one_of_the_registrations(tmp_path, spelling):
    project = make_project(tmp_path, "any", rounds=72, communication="platform")
    f = project / "scenario.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    buy = _buy(doc)
    buy[spelling] = buy.pop("requires_any", None) or buy.pop("requires")
    f.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    sim = Simulation(project)
    sim.prepare()
    sim.run()
    rows = sim.store.db.execute("SELECT agent, name FROM conversions").fetchall()
    sim.close()
    done = {}
    for agent, name in rows:
        done.setdefault(agent, set()).add(name)
    buyers = [names for names in done.values() if "buy" in names]
    registrations = {"register_lakeview", "register_palmgrove"}
    assert buyers, "the demo run should produce at least one purchase"
    assert all(names & registrations for names in buyers)            # always after some registration
    assert any(len(names & registrations) == 1 for names in buyers)   # and one is enough

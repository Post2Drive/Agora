import pytest
import yaml

from agora import scenario
from conftest import DEMO


def demo_dict():
    return yaml.safe_load(DEMO.read_text(encoding="utf-8"))


def test_demo_loads():
    sc = scenario.load(DEMO)
    assert sc.rounds == 72 and len(sc.segments) == 4
    assert {c.name for c in sc.conversions} == {"register_lakeview", "register_palmgrove", "buy"}
    assert sc.conversion("buy").requires == ["register_lakeview", "register_palmgrove"]


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d.update(segments=[]), "at least one segment"),
    (lambda d: d["segments"][0].update(platforms=["myspace"]), "unknown platforms"),
    (lambda d: d["events"].append({"at_round": 1, "type": "post", "account": "ghost",
                                   "platform": "x", "text": "hi"}), "unknown account"),
    (lambda d: d["events"].append({"at_round": 1, "type": "post", "account": "nutrivance",
                                   "platform": "x", "text": "hi",
                                   "when": {"poll": "lakeview_approval"}}), "has not happened"),
    (lambda d: d["conversions"][2].update(requires=["nope"]), "requires unknown"),
    (lambda d: d["conversions"][0].update(eligible_spaces=["Nowhere"]), "unknown space"),
    (lambda d: d["segments"][0].update(colour="blue"), "Unknown field"),
])
def test_validation(mutate, msg):
    d = demo_dict()
    mutate(d)
    with pytest.raises(scenario.ScenarioError, match=msg):
        scenario.from_dict(d)

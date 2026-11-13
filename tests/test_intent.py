"""Obvious intent is understood; opinion is read from words; unreadable answers are asked again."""
import dataclasses

import numpy as np

from agora.sim.engine import RoundOutput, Simulation
from agora.sim.llm_agent import parse_decision, score
from agora.sim.world import Agent


def _agent():
    return Agent(id=0, handle="h", kind="llm", name="N", segment="s", persona="p", platforms=["x"],
                 initial_stance=0.0, stubbornness=0.5, activity=0.5, influence=1.0, openness=0.6, stance=0.2)


def test_opinion_words_and_numbers():
    assert score("strongly against") == -0.8 and score("Unsure.") == 0.0 and score("strongly for") == 0.8
    assert score("doubtful, leaning against") == -0.4 and score(0.3) == 0.3 and score(5) == 1.0
    assert score("-0.5") == -0.5 and score("banana") is None and score(None) is None


def test_decision_with_words_is_usable():
    d = parse_decision('{"thoughts": "hm", "stance": "against", "actions": []}', _agent())
    assert d["ok"] and d["stance"] == -0.4


def test_unreadable_opinion_is_not_usable_so_it_is_asked_again():
    d = parse_decision('{"thoughts": "hm", "stance": "kind of maybe", "actions": []}', _agent())
    assert not d["ok"] and d["stance"] == 0.2


def test_missing_opinion_keeps_the_current_one():
    d = parse_decision('{"thoughts": "hm", "actions": []}', _agent())
    assert d["ok"] and d["stance"] == 0.2


def test_option_preferences_in_words():
    d = parse_decision('{"stance": "unsure", "prefs": {"Rao": "for", "Okafor": "strongly against"}, "actions": []}',
                       _agent())
    assert d["prefs"] == {"Rao": 0.4, "Okafor": -0.8}


def _apply(sim, a, x, opens):
    out = RoundOutput()
    res = sim._apply(a, x, 6, 24.0, opens, np.random.default_rng(0), out)
    return res, out


def test_action_name_written_as_the_type_is_understood(project):
    sim = Simulation(project)
    sim.prepare()
    a = next(x for x in sim.world.agents if x.kind == "llm")
    c = sim.sc.conversions[0]
    res, out = _apply(sim, a, {"type": c.name}, [c])
    assert res and out.conversions == [(a.id, c.name)]
    sim.close()


def test_a_clear_partial_name_is_understood_but_an_ambiguous_or_invented_one_is_not(project):
    sim = Simulation(project)
    sim.prepare()
    a = next(x for x in sim.world.agents if x.kind == "llm")
    c = sim.sc.conversions[0]
    twin = dataclasses.replace(c, name=c.name + "_b")
    res, out = _apply(sim, a, {"type": "convert", "name": c.name[:5]}, [c])
    assert res and out.conversions == [(a.id, c.name)]                       # one clear match
    res, out = _apply(sim, a, {"type": "convert", "name": c.name[:5]}, [c, twin])
    assert res is None and not out.conversions                                # ambiguous
    res, out = _apply(sim, a, {"type": "convert", "name": "freebies"}, [c])
    assert res is None and not out.conversions                                # invented
    sim.close()

import yaml

from agora import scenario as scenario_mod
from agora.sim import population


def test_initial_stance_comes_from_segment_or_account_fixture(tmp_path):
    source = __import__("pathlib").Path(__file__).parent / "fixtures" / "scenario.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))

    # A zero standard deviation makes the sampled segment stance deterministic.
    expected_segments = {}
    for index, segment in enumerate(data["segments"]):
        mean = round(-0.6 + index * 0.2, 2)
        segment["stance"] = {"mean": mean, "sd": 0.0}
        segment["leaning"] = {"Option A": -0.9, "Option B": 0.9}
        expected_segments[segment["name"]] = mean

    expected_accounts = {}
    for index, account in enumerate(data["accounts"]):
        stance = round(-0.8 + index * 0.25, 2)
        account["stance"] = stance
        account["leaning"] = {"Option A": -0.95, "Option B": 0.95}
        expected_accounts[account["id"]] = stance

    data["choice"] = {
        "name": "stance-regression-check",
        "question": "Which option do you prefer?",
        "options": ["Option A", "Option B"],
        "open_round": 0,
        "close_round": 1,
    }

    scenario = scenario_mod.from_dict(data)
    world, _, _ = population.build(scenario)

    for agent in world.agents:
        if agent.kind == "account":
            expected = expected_accounts[agent.handle]
        else:
            expected = expected_segments[agent.segment]
        assert agent.initial_stance == expected
        assert agent.initial_stance != agent.favourite()[1]

"""The decision log records what was offered, what the model said, and which actions were ignored."""
import json

import yaml

from agora.llm import LLMConfig
from agora.llm.base import LLMBackend
from agora.sim.engine import Simulation


class WrongName(LLMBackend):
    """Always tries a real-life action that does not exist."""
    name = "wrongname"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        if meta.get("task") == "decide":
            return json.dumps({"thoughts": "I might sign up", "stance": -0.9,
                               "actions": [{"type": "convert", "name": "no_such_action"}]})
        if meta.get("task") == "poll":
            return '{"vote": "yes", "reason": "fine"}'
        return "ok"


def test_ignored_actions_and_raw_stance_are_logged(project):
    p = project / "scenario.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": 8, "crowd_agents": 0}
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    s = Simulation(project)
    s.prepare()
    s.llm = WrongName()
    s.run(rounds=6)
    s.close()
    lines = [json.loads(x) for x in (project / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lines and {"round", "agent", "segment", "stance_before", "stance_reported", "stance_after",
                      "thoughts", "actions", "offered", "ignored"} <= set(lines[0])
    assert all(x["stance_reported"] == -0.9 for x in lines)
    assert any(x["ignored"] and x["ignored"][0]["name"] == "no_such_action" for x in lines)


def test_a_fresh_run_starts_a_fresh_log(project):
    (project / "decisions.jsonl").write_text('{"old": true}\n', encoding="utf-8")
    s = Simulation(project)
    s.prepare()
    s.close()
    assert not (project / "decisions.jsonl").exists()

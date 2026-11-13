"""All-AI mode: no crowd, every person decides with the model; unusable replies are retried and counted."""
import sqlite3

import yaml

from agora.llm import LLMConfig
from agora.llm.base import LLMBackend
from agora.sim.engine import Simulation


def _all_ai(project, voices=8):
    p = project / "scenario.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": voices, "crowd_agents": 0}
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")


class Flaky(LLMBackend):
    """The first decision reply for each person is garbage; asking again works."""
    name = "flaky"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))
        self.seen = set()
        self.garbage = 0

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        if meta.get("task") == "decide":
            key = messages[0]["content"]
            if key not in self.seen:
                self.seen.add(key)
                self.garbage += 1
                return "sorry, I cannot answer that"
            return '{"thoughts": "fine", "stance": 0.1, "actions": []}'
        if meta.get("task") == "poll":
            return '{"vote": "yes", "reason": "fine"}'
        return "ok"


class Garbage(LLMBackend):
    name = "garbage"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        return "nope"


def test_all_ai_run_has_no_crowd(project):
    _all_ai(project)
    s = Simulation(project)
    s.prepare()
    s.run(rounds=6)
    s.close()
    db = sqlite3.connect(project / "agora.db")
    kinds = dict(db.execute("SELECT kind, COUNT(*) FROM agents GROUP BY kind"))
    assert "crowd" not in kinds and kinds["llm"] == 8
    assert db.execute("SELECT COUNT(*) FROM rounds").fetchone()[0] == 6


def test_unusable_reply_is_retried(project):
    _all_ai(project)
    s = Simulation(project)
    s.prepare()
    s.llm = Flaky()
    s.run(rounds=6)
    assert s.llm.garbage > 0            # garbage really happened
    assert s.bad_replies == 0           # and every one was fixed by asking again
    s.close()


def test_still_unusable_replies_are_counted_not_hidden(project):
    _all_ai(project)
    s = Simulation(project)
    s.prepare()
    s.llm = Garbage()
    s.run(rounds=6)
    assert s.bad_replies > 0
    s.close()

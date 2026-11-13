"""No silent fallbacks: bad model output is retried, then fails with a clear error."""
import pytest

from agora.graph.build import DEFAULT_ONTOLOGY, extract_chunk
from agora.llm import LLMConfig
from agora.llm.base import LLMBackend, LLMError, StepFailed, ask_json

GOOD = '{"entities": [{"name": "Nutrivance", "type": "Organization", "description": "a brand", "aliases": []}], "relations": []}'


class Scripted(LLMBackend):
    name = "scripted"

    def __init__(self, replies):
        super().__init__(LLMConfig(backend="mock"))
        self.replies = list(replies)
        self.sent = []

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        self.sent.append((seed, messages[-1]["content"]))
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return r


def test_garbage_is_retried_then_fails_clearly():
    llm = Scripted(["not json at all"])
    with pytest.raises(StepFailed) as e:
        ask_json(llm, [{"role": "user", "content": "q"}], lambda d: bool(d), step="demo", seed=5)
    assert "demo" in str(e.value) and "Nothing was made up" in str(e.value)
    assert llm.calls == 3


def test_retry_changes_seed_and_adds_reminder_then_succeeds():
    llm = Scripted(["garbage", GOOD])
    d = ask_json(llm, [{"role": "user", "content": "q"}], lambda d: "entities" in d, step="demo", seed=5)
    assert d["entities"][0]["name"] == "Nutrivance" and llm.calls == 2
    assert llm.sent[0][0] != llm.sent[1][0]
    assert "could not be used" in llm.sent[1][1] and "could not be used" not in llm.sent[0][1]


def test_unreachable_model_fails_at_once():
    llm = Scripted([LLMError("Could not reach http://localhost:11434")])
    with pytest.raises(StepFailed) as e:
        ask_json(llm, [{"role": "user", "content": "q"}], lambda d: True, step="demo")
    assert "could not run" in str(e.value) and llm.calls == 1


def test_extraction_never_falls_back_to_rules():
    llm = Scripted(["garbage"])
    with pytest.raises(StepFailed):
        extract_chunk(llm, "Nutrivance offers a free sample in Guntur.", "goal", DEFAULT_ONTOLOGY, seed=1)


def test_extraction_uses_the_model_answer():
    llm = Scripted([GOOD])
    r = extract_chunk(llm, "Nutrivance offers a free sample in Guntur.", "goal", DEFAULT_ONTOLOGY, seed=1)
    assert [e["name"] for e in r["entities"]] == ["Nutrivance"]

"""Setup drafting: bad model output is retried, then fails clearly; no model means explicit defaults."""
import pytest

from agora.graph import draft
from agora.llm import LLMConfig
from agora.llm.base import LLMBackend, StepFailed


class Garbage(LLMBackend):
    name = "garbage"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        return "sorry, I cannot do that"


def test_bad_reply_fails_instead_of_using_defaults():
    llm = Garbage()
    with pytest.raises(StepFailed) as e:
        draft._ask(llm, "who reacts?", {"segments": draft.DEFAULT_SEGMENTS}, 1,
                   step="who reacts", check=draft._ok_segments)
    assert "who reacts" in str(e.value) and llm.calls == 3


def test_no_model_uses_defaults_by_request():
    d = draft._ask(None, "q", {"a": 1}, 1)
    assert d == {"a": 1}


def test_checks_reject_thin_answers():
    assert not draft._ok_segments({"segments": [{"name": "only_one"}]})
    assert draft._ok_segments({"segments": [{"name": "a"}, {"name": "b"}]})
    assert not draft._ok_persona({"name": "Asha", "persona": "too short"})
    assert draft._ok_persona({"name": "Asha", "persona": "A teacher who worries about prices."})
    assert not draft._ok_places({"actions": []})

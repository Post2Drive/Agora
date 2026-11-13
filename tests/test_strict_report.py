"""Report writer: an unreachable model stops it clearly; thin sections are labelled, never silently swapped."""
import pytest

from agora.llm import LLMConfig
from agora.llm.base import LLMBackend, LLMError, StepFailed
from agora.report.writer import RULES_NOTE, write_report
from agora.sim.engine import Simulation
from conftest import make_project


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    p = make_project(tmp_path_factory.mktemp("strictrep"))
    sim = Simulation(p)
    sim.prepare()
    sim.run()
    sim.close()
    return p


class Down(LLMBackend):
    name = "down"

    def __init__(self):
        super().__init__(LLMConfig(backend="mock"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        raise LLMError("Could not reach http://localhost:11434")


class Thin(LLMBackend):
    """A real-looking (non-mock) backend whose answers are always far too short."""
    name = "thin"

    def __init__(self):
        super().__init__(LLMConfig(backend="ollama"))

    def _complete(self, messages, *, max_tokens, temperature, json_mode, seed, meta):
        return "ok."


def test_unreachable_model_stops_the_report(ran):
    with pytest.raises(StepFailed) as e:
        write_report(ran, Down())
    assert "could not run" in str(e.value)


def test_thin_sections_are_labelled_and_announced(ran):
    said = []
    r = write_report(ran, Thin(), say=said.append)
    assert r["sections"][0]["text"].startswith(RULES_NOTE)
    assert any(m.startswith("WARNING") for m in said)

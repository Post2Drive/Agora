"""Each run records which provider and model it used, per stretch of rounds, never the key or full URL."""
import json

from agora.sim.engine import Simulation


def _segments(project):
    sim = Simulation(project)
    return sim.store.get_meta("llm_segments")


def test_first_run_records_provider_and_model(project):
    Simulation(project).run(rounds=2)
    segs = _segments(project)
    assert len(segs) == 1
    s = segs[0]
    assert s["from_round"] == 0
    assert s["backend"] == "mock" and s["host"] == "" and s["private_host"] is True
    assert s["model"]


def test_resume_with_same_model_adds_nothing(project):
    Simulation(project).run(rounds=2)
    Simulation(project).run(rounds=2)
    assert len(_segments(project)) == 1


def test_resume_with_other_model_adds_a_segment_from_that_round(project):
    Simulation(project).run(rounds=2)
    sim = Simulation(project, llm_override={"backend": "mock", "model": "other-model"})
    sim.run(rounds=1)
    segs = Simulation(project).store.get_meta("llm_segments")
    assert [x["model"] == "other-model" for x in segs] == [False, True]
    assert segs[1]["from_round"] == 2


def test_snapshot_has_host_only_never_key_or_path(project):
    sim = Simulation(project, llm_override={"backend": "ollama", "url": "http://192.168.1.5:11434/secret/path",
                                            "api_key": "sk-should-not-appear", "model": "llama3.2:3b"})
    snap = sim.llm_snapshot()
    text = json.dumps(snap)
    assert snap["host"] == "192.168.1.5" and snap["private_host"] is True
    assert "sk-should-not-appear" not in text and "secret" not in text

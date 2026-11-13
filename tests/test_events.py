import json

from agora import events
from agora.sim.engine import Simulation

from conftest import make_project


def test_add_dedupes_and_sync_queues_next_round(tmp_path):
    p = make_project(tmp_path, "ev")
    assert events.add(p, "Corruption allegations reported in state office")["duplicate"] is False
    assert events.add(p, "Corruption allegations reported in state office")["duplicate"] is True
    assert len(events.read(p)) == 1


def test_sync_before_run_says_so(tmp_path):
    p = make_project(tmp_path, "norun")
    events.add(p, "Some news")
    try:
        events.sync(p)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as e:
        assert "Run the study" in str(e)


def test_sync_applies_event_at_next_round_and_is_idempotent(tmp_path):
    p = make_project(tmp_path, "run")
    sim = Simulation(p)
    sim.prepare()
    sim.run(rounds=1)
    events.add(p, "Breaking: new report on the product")
    r1 = events.sync(p)
    assert len(r1["added"]) == 1
    assert r1["added"][0]["round"] == 2               # next round (1-based display)
    r2 = events.sync(p)
    assert r2["added"] == [] and r2["skipped"] == []
    assert json.loads((p / events.SYNCED).read_text())  # remembered

"""Native agent-to-agent messages in the engine: opt-in, delivered, recorded, and covered by snapshots."""
import dataclasses

import pytest

from agora import scenario as scenario_mod
from agora.sim import engine as engine_mod
from agora.sim.engine import Simulation
from conftest import make_project

POP = {"llm_agents": 10, "crowd_agents": 40}


def _run(tmp_path, name, mode, rounds=12, snapshot_rounds=(), **extra):
    project = make_project(tmp_path, name, rounds=rounds, population=POP, communication=mode, **extra)
    sim = Simulation(project, snapshot_rounds=snapshot_rounds)
    sim.prepare()
    sim.run()
    return project, sim


def _count(sim, table):
    return sim.store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _tables(sim):
    return {r[0] for r in sim.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_platform_default_creates_no_society_state(tmp_path):
    _, sim = _run(tmp_path, "platform", "platform")
    try:
        assert sim.society is None
        assert not any(t.startswith("society_") for t in _tables(sim))
        assert _count(sim, "posts WHERE kind='dm'") > 0
    finally:
        sim.close()


def test_native_mode_delivers_directly_and_creates_no_platform_dm_posts(tmp_path):
    _, sim = _run(tmp_path, "native", "native")
    try:
        assert _count(sim, "posts WHERE kind='dm'") == 0
        assert _count(sim, "society_messages") > 0
        row = sim.store.db.execute(
            "SELECT conversation_id, sender_id, round, reason FROM society_messages ORDER BY message_id").fetchone()
        assert row[3].startswith("@") and "chose to message" in row[3]
        # sending raised the sender's familiarity with the recipient, with the message as its cause
        changes = sim.store.db.execute(
            "SELECT reason, cause_message_id, familiarity_delta FROM society_relationship_changes").fetchall()
        assert any(c[0] == "sent a private message" and c[1] is not None and c[2] > 0 for c in changes)
    finally:
        sim.close()


def test_recipients_receive_messages_and_read_cursors_advance(tmp_path):
    _, sim = _run(tmp_path, "recv", "native", rounds=16)
    try:
        received = sim.store.db.execute(
            "SELECT COUNT(*) FROM society_relationship_changes WHERE reason='received a private message'"
        ).fetchone()[0]
        assert received > 0
        assert _count(sim, "society_read_cursors") > 0
    finally:
        sim.close()


def test_both_mode_uses_platform_and_native(tmp_path):
    _, sim = _run(tmp_path, "both", "both")
    try:
        assert _count(sim, "society_messages") > 0
        assert _count(sim, "posts WHERE kind='dm'") > 0
    finally:
        sim.close()


def test_native_message_reaches_the_decision_prompt_next_round(tmp_path):
    project = make_project(tmp_path, "prompt", rounds=16, population=POP, communication="native")
    sim = Simulation(project)
    sim.prepare()
    seen = []
    original = sim.llm.generate

    def spy(messages, **kw):
        seen.append(messages[-1]["content"])
        return original(messages, **kw)

    sim.llm.generate = spy
    try:
        sim.run()
        assert any("Private messages to you (sent directly, not on any app)" in text for text in seen)
        assert any("wrote to you privately" in text for text in seen)
    finally:
        sim.close()


def test_native_runs_are_deterministic(tmp_path):
    _, a = _run(tmp_path, "d1", "native")
    _, b = _run(tmp_path, "d2", "native")
    try:
        assert a.state_digest() == b.state_digest()
    finally:
        a.close()
        b.close()


def test_native_state_is_part_of_the_state_digest(tmp_path):
    _, sim = _run(tmp_path, "digest", "native")
    try:
        before = sim.state_digest()
        sim.store.db.execute("DROP TRIGGER society_messages_no_update")
        sim.store.db.execute("UPDATE society_messages SET text='tampered' WHERE message_id=1")
        assert sim.state_digest() != before
    finally:
        sim.close()


def test_native_delivery_works_when_no_shared_platform_has_direct_messages(tmp_path, monkeypatch):
    no_dm = {k: dataclasses.replace(v, dms=False) for k, v in engine_mod.REGISTRY.items()}
    monkeypatch.setattr(engine_mod, "REGISTRY", no_dm)
    _, platform_sim = _run(tmp_path, "nodm-platform", "platform")
    _, native_sim = _run(tmp_path, "nodm-native", "native")
    try:
        assert _count(platform_sim, "posts WHERE kind='dm'") == 0
        assert _count(native_sim, "society_messages") > 0
    finally:
        platform_sim.close()
        native_sim.close()


def test_snapshot_and_fork_cover_native_state(tmp_path):
    source, sim = _run(tmp_path, "src", "native", rounds=10, snapshot_rounds=(4,))
    expected = sim.state_digest()
    sim.close()
    fork = tmp_path / "fork"
    Simulation.fork_from(source, 4, fork)
    forked = Simulation(fork)
    try:
        forked.prepare()
        assert forked.society is not None
        forked.run()
        assert forked.state_digest() == expected
        assert _count(forked, "society_messages") > 0
    finally:
        forked.close()


def test_invalid_communication_mode_is_refused(tmp_path):
    project = make_project(tmp_path, "bad", rounds=2, population=POP, communication="telepathy")
    with pytest.raises(scenario_mod.ScenarioError, match="communication must be"):
        scenario_mod.load(project / "scenario.yaml")


def test_governed_runs_refuse_native_communication(tmp_path, monkeypatch):
    project = make_project(tmp_path, "gov", rounds=2, population=POP, communication="native")
    sc = scenario_mod.load(project / "scenario.yaml")
    monkeypatch.setattr(Simulation, "_verify_governed",
                        lambda self, governed_input, scenario, name: {"scenario": scenario})
    with pytest.raises(ValueError, match="not supported for governed runs"):
        Simulation(project, governed_input={"package": {}, "mapping": {}})


def _two_voices(sim):
    voices = [a for a in sim.world.agents if a.is_llm]
    return voices[0], voices[1]


@pytest.mark.parametrize("mode,expect_native,expect_platform_dm", [
    ("both", True, False), ("native", True, False), ("platform", None, False)])
def test_dm_without_a_shared_dm_platform(tmp_path, monkeypatch, mode, expect_native, expect_platform_dm):
    no_dm = {k: dataclasses.replace(v, dms=False) for k, v in engine_mod.REGISTRY.items()}
    monkeypatch.setattr(engine_mod, "REGISTRY", no_dm)
    project = make_project(tmp_path, f"unit-{mode}", rounds=3, population=POP, communication=mode)
    sim = Simulation(project)
    try:
        sim.prepare()
        a, b = _two_voices(sim)
        result = sim._dm(a, {"to": f"@{b.handle}", "text": "hello there"}, 0, 0.0, engine_mod.RoundOutput())
        if expect_native:
            assert result is not None and "privately" in result
            assert sim.society.thread(1)[0]["text"] == "hello there"
        else:
            assert result is None
        assert not any(p.kind == "dm" for p in sim.world.posts)
    finally:
        sim.close()

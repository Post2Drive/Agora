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
        assert any("Messages to you (sent directly, not on any app)" in text for text in seen)
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


# --------------------------------------------------------------------- groups and open discussions
import json  # noqa: E402


def _native_sim(tmp_path, name, mode="native", **extra):
    project = make_project(tmp_path, name, rounds=12, population=POP, communication=mode, **extra)
    sim = Simulation(project)
    sim.prepare()
    return sim


def _act(sim, agent, action, r=0):
    return sim._apply(agent, action, r, 0.0, [], None, engine_mod.RoundOutput())


def _voices(sim, n=4):
    return [a for a in sim.world.agents if a.is_llm][:n]


def test_group_create_adds_owner_members_and_opening_message(tmp_path):
    sim = _native_sim(tmp_path, "g1")
    try:
        a, b, c, _ = _voices(sim)
        result = _act(sim, a, {"type": "group_create", "topic": "Street watch",
                               "invite": [f"@{b.handle}", c.handle, "@nobody", f"@{a.handle}", f"@{b.handle}"],
                               "text": "Let's coordinate"})
        assert result.startswith('you started the group g1 "Street watch" with ')
        assert sim.society.members(1) == [(a.id, "owner"), (b.id, "member"), (c.id, "member")]
        assert [m["text"] for m in sim.society.thread(1)] == ["Let's coordinate"]
        assert "opened the group" in sim.society.thread(1)[0]["reason"]
    finally:
        sim.close()


@pytest.mark.parametrize("action", [
    {"type": "group_create", "invite": ["@x"], "text": "no topic"},
    {"type": "group_create", "topic": "t", "invite": []},
    {"type": "group_create", "topic": "t", "invite": "not a list"},
    {"type": "group_create", "topic": "t", "invite": ["@nobody"]},
    {"type": "group_create", "topic": "t"},
])
def test_group_create_refuses_unusable_requests(tmp_path, action):
    sim = _native_sim(tmp_path, "g2")
    try:
        a = _voices(sim)[0]
        assert _act(sim, a, action) is None
        assert sim.society.count("group") == 0
    finally:
        sim.close()


def test_group_create_refuses_inviting_only_yourself(tmp_path):
    sim = _native_sim(tmp_path, "g3")
    try:
        a = _voices(sim)[0]
        assert _act(sim, a, {"type": "group_create", "topic": "t", "invite": [f"@{a.handle}"]}) is None
    finally:
        sim.close()


def test_groups_per_agent_are_capped(tmp_path):
    sim = _native_sim(tmp_path, "g4")
    try:
        a, b, *_ = _voices(sim)
        for i in range(engine_mod.MAX_GROUPS_PER_AGENT):
            assert _act(sim, a, {"type": "group_create", "topic": f"t{i}", "invite": [b.handle]})
        assert _act(sim, a, {"type": "group_create", "topic": "one too many", "invite": [b.handle]}) is None
        assert _act(sim, b, {"type": "group_create", "topic": "b's own", "invite": [a.handle]})
    finally:
        sim.close()


def test_invitations_are_limited(tmp_path):
    sim = _native_sim(tmp_path, "g5")
    try:
        a = _voices(sim)[0]
        others = [x for x in sim.world.agents if x.id != a.id][:engine_mod.MAX_GROUP_INVITES + 3]
        assert _act(sim, a, {"type": "group_create", "topic": "big", "invite": [o.handle for o in others]})
        assert len(sim.society.members(1)) == 1 + engine_mod.MAX_GROUP_INVITES
    finally:
        sim.close()


def test_group_say_requires_membership_a_real_group_and_text(tmp_path):
    sim = _native_sim(tmp_path, "g6")
    try:
        a, b, c, d = _voices(sim)
        _act(sim, a, {"type": "group_create", "topic": "t", "invite": [b.handle]})
        assert _act(sim, b, {"type": "group_say", "group": "g1", "text": "hello all"}).startswith("you wrote in group g1")
        assert _act(sim, c, {"type": "group_say", "group": "g1", "text": "intruder"}) is None
        assert _act(sim, b, {"type": "group_say", "group": "g1", "text": " "}) is None
        assert _act(sim, b, {"type": "group_say", "group": "g99", "text": "x"}) is None
        assert _act(sim, b, {"type": "group_say", "group": "nonsense", "text": "x"}) is None
        sim.society.direct(c.id, d.id, round=0)  # conversation 2 is a direct one: not a group
        assert _act(sim, c, {"type": "group_say", "group": "g2", "text": "x"}) is None
        assert [m["text"] for m in sim.society.thread(1)] == ["hello all"]
    finally:
        sim.close()


def test_open_discussion_is_created_once_per_topic_and_shared(tmp_path):
    sim = _native_sim(tmp_path, "o1")
    try:
        a, b, *_ = _voices(sim)
        assert "open discussion d1" in _act(sim, a, {"type": "discuss", "topic": "Fuel price rise", "text": "Awful"})
        assert "d1" in _act(sim, b, {"type": "discuss", "topic": "  fuel PRICE rise ", "text": "Agreed"})
        assert sim.society.count("open") == 1
        assert [m["sender_id"] for m in sim.society.thread(1)] == [a.id, b.id]
        assert "d1" in _act(sim, b, {"type": "discuss", "topic": "d1", "text": "again"})
        assert _act(sim, a, {"type": "discuss", "topic": "d77", "text": "x"}) is None
    finally:
        sim.close()


def test_discuss_refuses_group_refs_empty_fields_and_caps(tmp_path):
    sim = _native_sim(tmp_path, "o2")
    try:
        a, b, *_ = _voices(sim)
        _act(sim, a, {"type": "group_create", "topic": "g", "invite": [b.handle]})
        assert _act(sim, a, {"type": "discuss", "topic": "d1", "text": "x"}) is None  # d1 is a group
        assert _act(sim, a, {"type": "discuss", "topic": "", "text": "x"}) is None
        assert _act(sim, a, {"type": "discuss", "topic": "t", "text": ""}) is None
        for i in range(engine_mod.MAX_OPEN_DISCUSSIONS):
            assert _act(sim, a, {"type": "discuss", "topic": f"topic {i}", "text": "x"})
        assert _act(sim, a, {"type": "discuss", "topic": "one more topic", "text": "x"}) is None
        assert _act(sim, a, {"type": "discuss", "topic": "topic 3", "text": "still allowed"})
    finally:
        sim.close()


@pytest.mark.parametrize("action", [
    {"type": "group_create", "topic": "t", "invite": ["@a"]},
    {"type": "group_say", "group": "g1", "text": "x"},
    {"type": "discuss", "topic": "t", "text": "x"},
])
def test_group_actions_are_ignored_outside_native_modes(tmp_path, action):
    sim = _native_sim(tmp_path, "plat", mode="platform")
    try:
        assert _act(sim, _voices(sim)[0], action) is None
        assert sim.society is None
    finally:
        sim.close()


def _scripted(sim, prompts):
    """Wrap the model so the first voice opens a group and every voice joins one open discussion."""
    voices = sorted((a for a in sim.world.agents if a.is_llm and a.kind != "account"), key=lambda a: a.id)
    first, second = voices[0], voices[1]
    original = sim.llm.generate

    def script(messages, **kw):
        raw = original(messages, **kw)
        user = messages[-1]["content"]
        if "at most" not in user or "Reply with JSON only" not in user:
            return raw                                   # polls and other prompts are untouched
        prompts.append(user)
        data = json.loads(raw)
        acts = [{"type": "discuss", "topic": "Metro fare hike", "text": "my view"}]
        if messages[0]["content"].startswith(f"You are {first.name}") and "Your groups:" not in user:
            acts.insert(0, {"type": "group_create", "topic": "Lane 4 residents", "invite": [second.handle],
                            "text": "Shall we talk?"})
        data["actions"] = acts + list(data.get("actions") or [])
        return json.dumps(data)

    sim.llm.generate = script


def test_group_and_discussion_messages_reach_prompts_end_to_end(tmp_path):
    project = make_project(tmp_path, "e2e", rounds=12, population=POP, communication="native")
    sim = Simulation(project, snapshot_rounds=(3,))
    sim.prepare()
    prompts = []
    _scripted(sim, prompts)
    try:
        sim.run()
        assert any("You can also talk without any app" in p for p in prompts)
        assert sim.society.count("open") == 1 and sim.society.count("group") == 1
        group = next(c for c in range(1, 10) if sim.society.conversation(c)["kind"] == "group")
        assert len(sim.society.members(group)) == 2
        assert any(f'[group g{group} "Lane 4 residents"]' in p for p in prompts)
        assert any(f'Your groups: g{group} "Lane 4 residents"' in p for p in prompts)
        assert any("[discussion d" in p and "Metro fare hike" in p for p in prompts)
        assert any("Open discussions: d" in p for p in prompts)
        expected = sim.state_digest()
    finally:
        sim.close()
    fork = tmp_path / "e2e-fork"
    Simulation.fork_from(project, 3, fork)
    forked = Simulation(fork)
    forked.prepare()
    _scripted(forked, [])
    try:
        forked.run()
        assert forked.state_digest() == expected
    finally:
        forked.close()


def test_group_create_needs_a_topic_even_with_a_valid_invitee(tmp_path):
    sim = _native_sim(tmp_path, "g7")
    try:
        a, b, *_ = _voices(sim)
        for topic in ("", "   ", None):
            assert _act(sim, a, {"type": "group_create", "topic": topic, "invite": [b.handle]}) is None
        assert _act(sim, a, {"type": "group_create", "name": "named instead", "invite": [b.handle]})
        assert sim.society.count("group") == 1
    finally:
        sim.close()


def test_receiving_group_and_discussion_messages_is_recorded_with_its_own_reason(tmp_path):
    project = make_project(tmp_path, "reasons", rounds=12, population=POP, communication="native")
    sim = Simulation(project)
    sim.prepare()
    _scripted(sim, [])
    try:
        sim.run()
        reasons = {r[0] for r in sim.store.db.execute(
            "SELECT reason FROM society_relationship_changes")}
        assert {"received a group message", "read an open discussion message"} <= reasons
    finally:
        sim.close()

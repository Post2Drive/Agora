"""Contact permissions and the scored word-of-mouth model for crowd people."""
import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest

from agora import scenario as scenario_mod
from agora.scenario import ScenarioError
from agora.sim.engine import Simulation
from agora.society import SocietyStore, contact
from conftest import make_project

POP = {"llm_agents": 6, "crowd_agents": 60}


def _agent(i, segment="a", stance=0.0, influence=0.5):
    return SimpleNamespace(id=i, segment=segment, stance=stance, influence=influence)


def _world(*agents, member_of=None):
    return SimpleNamespace(agents=list(agents), member_of=member_of or {})


def _run(tmp_path, name, rounds=10, snapshot_rounds=(), **extra):
    extra.setdefault("communication", "native")
    project = make_project(tmp_path, name, rounds=rounds, population=POP, **extra)
    sim = Simulation(project, snapshot_rounds=snapshot_rounds)
    sim.prepare()
    sim.run()
    return project, sim


def _behaviour(sim):
    """What the run did, without the stored scenario hash (which names the contact settings)."""
    db = sim.store.db
    return (sim.society.digest() if sim.society is not None else None,
            db.execute("SELECT * FROM posts ORDER BY id").fetchall(),
            [(a.id, round(a.stance, 12)) for a in sim.world.agents])


def _contacts(sim):
    return sim.store.db.execute(
        "SELECT message_id, conversation_id, sender_id, round, reason FROM society_messages "
        "WHERE reason LIKE 'crowd contact%' ORDER BY message_id").fetchall()


# --- the permission matrix -------------------------------------------------------------
def test_open_allows_anyone_but_oneself():
    soc = SocietyStore(":memory:")
    a, b = _agent(1), _agent(2)
    w = _world(a, b)
    assert contact.may_contact("open", w, soc, a, b)
    assert not contact.may_contact("open", w, soc, a, a)


def test_relationship_mode_needs_an_edge_a_group_or_a_shared_space():
    soc = SocietyStore(":memory:")
    a, b, c, d = _agent(1), _agent(2), _agent(3), _agent(4)
    w = _world(a, b, c, d, member_of={1: {"x": ["s1"]}, 4: {"x": ["s1"]}})
    assert not contact.may_contact("relationship", w, soc, a, b)
    assert contact.may_contact("relationship", w, soc, a, d)              # shared space
    soc.adjust_relationship(2, 1, round=0, familiarity_delta=0.1, cause_message_id=None, reason="met")
    assert contact.may_contact("relationship", w, soc, a, b)              # an edge in either direction
    assert contact.may_contact("relationship", w, soc, b, a)
    assert not contact.may_contact("relationship", w, soc, a, c)
    gid = soc.create("group", 3, round=0, topic="club")
    soc.join(gid, 1, round=0)
    assert contact.may_contact("relationship", w, soc, a, c)              # a shared group


def test_group_only_mode_needs_a_shared_group():
    soc = SocietyStore(":memory:")
    a, b, c = _agent(1), _agent(2), _agent(3)
    w = _world(a, b, c, member_of={1: {"x": ["s1"]}, 2: {"x": ["s1"]}})
    assert not contact.may_contact("group_only", w, soc, a, b)            # a shared space is not enough
    gid = soc.create("group", 1, round=0, topic="club")
    soc.join(gid, 2, round=0)
    assert contact.may_contact("group_only", w, soc, a, b)
    assert not contact.may_contact("group_only", w, soc, a, c)


def test_unknown_mode_is_an_error():
    with pytest.raises(ValueError):
        contact.may_contact("everyone", _world(), SocietyStore(":memory:"), _agent(1), _agent(2))


# --- scoring and choice ----------------------------------------------------------------
def test_components_use_trust_familiarity_similarity_and_influence():
    soc = SocietyStore(":memory:")
    a = _agent(1, "a", 0.2)
    b = _agent(2, "a", 0.2, influence=0.5)
    assert contact.components(soc, a, b, 1.0) == {
        "trust": 0.5, "familiarity": 0.0, "similarity": 1.0, "influence": 0.5}
    far = _agent(3, "b", -0.8, influence=2.0)
    parts = contact.components(soc, a, far, 1.0)
    assert parts["similarity"] == pytest.approx(0.25) and parts["influence"] == 1.0
    soc.adjust_relationship(1, 2, round=0, trust_delta=0.3, familiarity_delta=0.2, cause_message_id=None, reason="x")
    parts = contact.components(soc, a, b, 0.0)
    assert parts["trust"] == pytest.approx(0.8) and parts["familiarity"] == pytest.approx(0.2)
    assert parts["influence"] == 0.0                                       # no influence anywhere


def test_score_is_a_weighted_sum_and_unknown_weights_fall_back_to_defaults():
    parts = {"trust": 1.0, "familiarity": 0.5, "similarity": 0.25, "influence": 1.0}
    assert contact.score(parts, {}) == pytest.approx(1.0 + 0.5 + 0.25 + 0.5)
    assert contact.score(parts, {"influence": 2.0, "trust": 0.0}) == pytest.approx(0 + 0.5 + 0.25 + 2.0)


def test_choice_is_deterministic_and_never_repeats_or_picks_oneself():
    soc = SocietyStore(":memory:")
    agents = [_agent(i, stance=i / 10) for i in range(8)]
    w = _world(*agents)
    first = [contact.choose(w, soc, agents[0], "open", 5, {}, np.random.default_rng([1, 2, 3]), 1.0, set())
             for _ in range(1)]
    again = contact.choose(w, soc, agents[0], "open", 5, {}, np.random.default_rng([1, 2, 3]), 1.0, set())
    assert first[0][0].id == again[0].id and first[0][2] == again[2]
    assert first[0][0].id != 0
    taken = {b.id for b in agents[1:7]}
    assert contact.choose(w, soc, agents[0], "open", 5, {}, np.random.default_rng(1), 1.0, taken)[0].id == 7
    assert contact.choose(w, soc, agents[0], "open", 5, {}, np.random.default_rng(1), 1.0,
                          {b.id for b in agents[1:]}) is None


def test_higher_score_is_chosen_more_often():
    soc = SocietyStore(":memory:")
    me = _agent(0, "a", 0.0)
    near, far = _agent(1, "a", 0.0), _agent(2, "b", 1.0)
    w = _world(me, near, far)
    picks = [contact.choose(w, soc, me, "open", 5, {}, np.random.default_rng([7, i]), 1.0, set())[0].id
             for i in range(200)]
    assert picks.count(1) > picks.count(2) * 3 and picks.count(2) > 0


def test_pool_limits_how_many_candidates_are_weighed():
    soc = SocietyStore(":memory:")
    agents = [_agent(i) for i in range(30)]
    w = _world(*agents)
    seen = set()
    for i in range(60):
        seen.add(contact.choose(w, soc, agents[0], "open", 3, {}, np.random.default_rng([5, i]), 1.0, set())[0].id)
    assert len(seen) > 3                                                   # different draws weigh different people
    one = contact.choose(w, soc, agents[0], "open", 1, {}, np.random.default_rng(9), 1.0, set())
    assert one is not None


# --- scenario validation ---------------------------------------------------------------
@pytest.mark.parametrize("field,value,text", [
    ("contact", "everyone", "contact must be"),
    ("contact_budget", 6, "contact_budget"),
    ("contact_budget", -1, "contact_budget"),
    ("contact_budget", True, "contact_budget"),
    ("contact_budget", 1.5, "contact_budget"),
    ("contact_pool", 0, "contact_pool"),
    ("contact_pool", 501, "contact_pool"),
    ("contact_weights", {"charm": 1}, "contact_weights may only"),
    ("contact_weights", {"trust": -1}, "numbers from 0 to 10"),
    ("contact_weights", {"trust": True}, "numbers from 0 to 10"),
    ("contact_weights", {"trust": 11}, "numbers from 0 to 10"),
])
def test_scenario_rejects_bad_contact_settings(tmp_path, field, value, text):
    project = make_project(tmp_path, "bad", population=POP, communication="native")
    sc = dataclasses.replace(scenario_mod.load(project / "scenario.yaml"), **{field: value})
    with pytest.raises(ScenarioError, match=text):
        scenario_mod.validate(sc)


def test_contact_budget_needs_native_messaging(tmp_path):
    project = make_project(tmp_path, "plat", population=POP)
    sc = dataclasses.replace(scenario_mod.load(project / "scenario.yaml"), contact_budget=1)
    with pytest.raises(ScenarioError, match="needs communication native or both"):
        scenario_mod.validate(sc)


# --- in the engine ---------------------------------------------------------------------
def test_budget_zero_changes_nothing(tmp_path):
    _, base = _run(tmp_path, "base")
    _, explicit = _run(tmp_path, "explicit", contact="open", contact_budget=0, contact_pool=7,
                       contact_weights={"trust": 2})
    try:
        assert _behaviour(base) == _behaviour(explicit)
        assert _contacts(base) == [] and _contacts(explicit) == []
    finally:
        base.close(); explicit.close()


def test_platform_mode_is_untouched(tmp_path):
    _, plat = _run(tmp_path, "p1", communication="platform")
    _, again = _run(tmp_path, "p2", communication="platform", contact="group_only")
    try:
        assert plat.society is None and again.society is None and _behaviour(plat) == _behaviour(again)
    finally:
        plat.close(); again.close()


def test_crowd_people_talk_and_each_conversation_records_why(tmp_path):
    _, sim = _run(tmp_path, "talk", contact_budget=2)
    try:
        rows = _contacts(sim)
        assert len(rows) > 20
        _, _, sender, _, reason = rows[0]
        assert "score" in reason and "trust" in reason and "similarity" in reason and "stance change" in reason
        senders = {r[2] for r in rows}
        crowd = {a.id for a in sim.world.agents if not a.is_llm and a.kind != "account"}
        assert senders <= crowd                                            # only crowd people, never LLM voices
        # the sender's familiarity rose with the message as its cause
        ids = {r[0] for r in rows}
        got = sim.store.db.execute(
            "SELECT cause_message_id, reason FROM society_relationship_changes "
            "WHERE reason='sent a private message'").fetchall()
        assert ids & {g[0] for g in got}
        # a recipient's trust moved with a stated reason
        moved = sim.store.db.execute(
            "SELECT reason, trust_delta FROM society_relationship_changes WHERE reason LIKE 'heard a view%'").fetchall()
        assert {m[0] for m in moved} <= {"heard a view that agreed", "heard a view that differed"}
        assert any(m[1] > 0 for m in moved)
    finally:
        sim.close()


def test_a_contact_moves_the_listener_toward_the_speaker_by_the_recorded_amount(tmp_path):
    project = make_project(tmp_path, "effect", rounds=3, population=POP, communication="native", contact_budget=1)
    sim = Simulation(project)
    sim.prepare()
    try:
        w = sim.world
        crowd = [a for a in w.agents if not a.is_llm and a.kind != "account"]
        a, b = crowd[0], crowd[1]
        a.stance, b.stance, a.influence, b.stubbornness = 0.8, -0.2, 1.0, 0.0
        sim._contact(a, b, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.4, "influence": 0.3}, 1.2, 0)
        expected = -0.2 + sim.sc.persuasion * 1.0 * (0.5 * 1.0) * (0.8 + 0.2)
        assert b.stance == pytest.approx(expected)
        row = sim.store.db.execute("SELECT text, reason FROM society_messages").fetchone()
        assert row[0].startswith("I lean towards supporting")
        assert f"stance change {expected + 0.2:+.3f}" in row[1]
        # the listener held a different view (gap 1.0 > 0.5): trust fell
        assert sim.society.relationship(b.id, a.id)["trust"] == pytest.approx(0.47)
        # a stubborn listener does not move
        c = crowd[2]
        c.stance, c.stubbornness = -0.9, 1.0
        sim._contact(a, c, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.1, "influence": 0.3}, 0.9, 0)
        assert c.stance == -0.9
        # someone who is undecided speaks differently
        a.stance = 0.0
        sim._contact(a, b, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.1, "influence": 0.3}, 0.9, 0)
        a.stance = -0.8
        sim._contact(a, b, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.1, "influence": 0.3}, 0.9, 0)
        texts = [r[0] for r in sim.store.db.execute("SELECT text FROM society_messages ORDER BY message_id")]
        assert texts[-2].startswith("I am undecided about") and texts[-1].startswith("I lean against")
    finally:
        sim.close()


def test_a_contact_with_a_voice_is_delivered_but_does_not_change_the_voice(tmp_path):
    project = make_project(tmp_path, "voice", rounds=3, population=POP, communication="native", contact_budget=1)
    sim = Simulation(project)
    sim.prepare()
    try:
        voice = next(a for a in sim.world.agents if a.is_llm and a.kind != "account")
        crowd = next(a for a in sim.world.agents if not a.is_llm and a.kind != "account")
        crowd.stance, voice.stance = 0.9, -0.5
        sim._contact(crowd, voice, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.1, "influence": 0.3}, 1.0, 0)
        assert voice.stance == -0.5
        assert "(not applied)" in sim.store.db.execute("SELECT reason FROM society_messages").fetchone()[0]
        unread = sim.society.inbox(voice.id)
        assert len(unread) == 1 and unread[0]["sender_id"] == crowd.id    # the voice will read it next round
        assert sim.society.relationship(voice.id, crowd.id) is None       # received only when it reads
    finally:
        sim.close()


def test_a_contact_does_not_change_stance_in_choice_mode(tmp_path):
    project = make_project(tmp_path, "choice", rounds=3, population=POP, communication="native", contact_budget=1)
    sim = Simulation(project)
    sim.prepare()
    try:
        sim.sc.choice = {"a": "x"} if not sim.sc.choice else sim.sc.choice
        crowd = [a for a in sim.world.agents if not a.is_llm and a.kind != "account"]
        a, b = crowd[0], crowd[1]
        a.stance, b.stance = 0.9, -0.5
        sim._contact(a, b, {"trust": 0.5, "familiarity": 0.0, "similarity": 0.1, "influence": 0.3}, 1.0, 0)
        assert b.stance == -0.5
    finally:
        sim.close()


def test_group_only_blocks_crowd_contact_until_a_group_exists(tmp_path):
    _, sim = _run(tmp_path, "grp", contact_budget=2, contact="group_only")
    try:
        assert _contacts(sim) == []
    finally:
        sim.close()


def test_relationship_mode_only_connects_acquainted_people(tmp_path):
    _, sim = _run(tmp_path, "rel", contact_budget=2, contact="relationship")
    try:
        spaces = {a.id: {s for sp in sim.world.member_of.get(a.id, {}).values() for s in sp} for a in sim.world.agents}
        # the first contact between two people needs a shared space; later ones may rest on the edge it made
        first = {}
        for mid, sender, recipient in sim.store.db.execute(
                "SELECT m.message_id, m.sender_id, x.agent_id FROM society_messages m "
                "JOIN society_memberships x ON x.conversation_id=m.conversation_id AND x.agent_id<>m.sender_id "
                "WHERE m.reason LIKE 'crowd contact%' ORDER BY m.message_id"):
            first.setdefault(frozenset((sender, recipient)), (sender, recipient))
        assert any(spaces[s] & spaces[r] for s, r in first.values())
    finally:
        sim.close()


def test_llm_direct_messages_respect_the_matrix(tmp_path):
    project = make_project(tmp_path, "dm", rounds=3, population=POP, communication="native", contact="group_only")
    sim = Simulation(project)
    sim.prepare()
    try:
        voices = [a for a in sim.world.agents if a.is_llm and a.kind != "account"]
        a, b = voices[0], voices[1]
        x = {"type": "dm", "to": "@" + b.handle, "text": "hello"}
        assert sim._dm(a, x, 0, 0.0, None) is None
        assert sim.store.db.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 0
        gid = sim.society.create("group", a.id, round=0, topic="club")
        sim.society.join(gid, b.id, round=0)
        assert sim._dm(a, x, 0, 0.0, None) is not None
        assert sim.store.db.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 1
    finally:
        sim.close()


def test_the_run_is_reproducible_and_survives_snapshot_and_fork(tmp_path):
    source, one = _run(tmp_path, "r1", contact_budget=2, snapshot_rounds=(4,))
    _, two = _run(tmp_path, "r2", contact_budget=2)
    try:
        expected = one.state_digest()
        assert expected == two.state_digest() and _contacts(one)
    finally:
        one.close(); two.close()
    fork = tmp_path / "fork"
    Simulation.fork_from(source, 4, fork)
    forked = Simulation(fork)
    try:
        forked.prepare()
        forked.run()
        assert forked.state_digest() == expected
    finally:
        forked.close()


def test_a_different_seed_gives_different_contacts(tmp_path):
    _, one = _run(tmp_path, "s1", contact_budget=2, seed=11)
    _, two = _run(tmp_path, "s2", contact_budget=2, seed=12)
    try:
        assert one.state_digest() != two.state_digest()
    finally:
        one.close(); two.close()


def _fresh(tmp_path, name):
    project = make_project(tmp_path, name, rounds=3, population=POP, communication="native", contact_budget=1)
    sim = Simulation(project)
    sim.prepare()
    crowd = [a for a in sim.world.agents if not a.is_llm and a.kind != "account"]
    return sim, crowd


PARTS = {"trust": 0.5, "familiarity": 0.0, "similarity": 0.4, "influence": 0.3}


def test_agreement_thresholds_and_exact_relationship_changes(tmp_path):
    sim, crowd = _fresh(tmp_path, "thr")
    try:
        a, b = crowd[0], crowd[1]
        b.stubbornness, a.influence = 0.0, 1.0
        a.stance, b.stance = 0.5, 0.0                      # a gap of exactly 0.5 still agrees
        sim._contact(a, b, PARTS, 1.0, 0)
        assert sim.society.relationship(a.id, b.id) == {"trust": 0.5, "familiarity": 0.05, "last_contact_round": 0}
        rel = sim.society.relationship(b.id, a.id)
        assert rel["trust"] == pytest.approx(0.53) and rel["familiarity"] == pytest.approx(0.05)
        c = crowd[2]
        c.stubbornness = 0.0
        a.stance, c.stance = 0.51, 0.0                     # just over: differs
        sim._contact(a, c, PARTS, 1.0, 0)
        assert sim.society.relationship(c.id, a.id)["trust"] == pytest.approx(0.47)
        # the listener has read it
        assert sim.society.inbox(b.id) == [] and sim.society.inbox(c.id) == []
    finally:
        sim.close()


@pytest.mark.parametrize("stance,start", [(0.31, "I lean towards supporting"), (0.3, "I am undecided about"),
                                          (-0.3, "I am undecided about"), (-0.31, "I lean against")])
def test_the_view_a_person_states_follows_their_stance(tmp_path, stance, start):
    sim, crowd = _fresh(tmp_path, "view")
    try:
        crowd[0].stance = stance
        sim._contact(crowd[0], crowd[1], PARTS, 1.0, 0)
        assert sim.store.db.execute("SELECT text FROM society_messages").fetchone()[0].startswith(start)
    finally:
        sim.close()


def test_an_organisation_account_hears_but_does_not_change(tmp_path):
    sim, crowd = _fresh(tmp_path, "acct")
    try:
        account = next((a for a in sim.world.agents if a.kind == "account"), None)
        if account is None:
            pytest.skip("demo scenario has no organisation account")
        crowd[0].stance, account.stance = 0.9, -0.9
        sim._contact(crowd[0], account, PARTS, 1.0, 0)
        assert account.stance == -0.9
    finally:
        sim.close()


def test_trust_in_the_speaker_and_influence_scale_the_move(tmp_path):
    sim, crowd = _fresh(tmp_path, "scale")
    try:
        a, b = crowd[0], crowd[1]
        b.stubbornness, a.influence, a.stance, b.stance = 0.0, 0.25, 1.0, 0.0
        sim.society.adjust_relationship(b.id, a.id, round=0, trust_delta=0.3, cause_message_id=None, reason="t")
        sim._contact(a, b, PARTS, 1.0, 0)
        assert b.stance == pytest.approx(sim.sc.persuasion * 0.8 * 0.5 * 1.0)   # trust 0.8, sqrt(0.25) = 0.5
    finally:
        sim.close()


def test_each_person_and_round_has_their_own_random_stream(tmp_path, monkeypatch):
    seen = {}
    real = contact.choose

    def spy(world, soc, a, mode, pool, weights, rng, top, taken):
        seen.setdefault(a.id, []).append(rng.bit_generator.state["state"]["state"])
        return real(world, soc, a, mode, pool, weights, rng, top, taken)

    monkeypatch.setattr(contact, "choose", spy)
    sim, crowd = _fresh(tmp_path, "rng")
    try:
        active = crowd[:6]
        sim._contacts(active, 1)
        sim._contacts(active, 2)
        firsts = [seen[a.id][0] for a in active]
        assert len(set(firsts)) == len(active)             # not the same stream for everyone
        assert all(seen[a.id][0] != seen[a.id][1] for a in active)   # nor for every round
        np_state = np.random.default_rng([sim.sc.seed, 1, 2, active[0].id]).bit_generator.state["state"]["state"]
        assert seen[active[0].id][0] == np_state
    finally:
        sim.close()


def test_contacts_skip_voices_and_organisations_and_stop_when_nobody_is_permitted(tmp_path):
    sim, crowd = _fresh(tmp_path, "who")
    try:
        sim.sc.contact = "group_only"
        voices = [a for a in sim.world.agents if a.is_llm or a.kind == "account"]
        sim._contacts(voices + crowd[:3], 0)
        assert sim.store.db.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 0
        sim.sc.contact, sim.sc.contact_budget = "open", 3
        sim._contacts(voices + crowd[:3], 0)
        rows = sim.store.db.execute("SELECT DISTINCT sender_id FROM society_messages").fetchall()
        assert {r[0] for r in rows} == {a.id for a in crowd[:3]}
        # three distinct people each: the same person is never picked twice in one round
        per = sim.store.db.execute("SELECT sender_id, COUNT(*) FROM society_messages GROUP BY sender_id").fetchall()
        assert all(n == 3 for _, n in per)
        dup = sim.store.db.execute(
            "SELECT COUNT(*) FROM (SELECT sender_id, conversation_id, COUNT(*) c FROM society_messages "
            "GROUP BY sender_id, conversation_id HAVING c > 1)").fetchone()[0]
        assert dup == 0
    finally:
        sim.close()


def test_the_pool_decides_how_many_people_are_weighed():
    soc = SocietyStore(":memory:")
    me = _agent(0, "a", 0.0, influence=1.0)
    others = [_agent(i, "b", 1.0, influence=0.0) for i in range(1, 20)]
    star = _agent(20, "a", 0.0, influence=1.0)
    w = _world(me, *others, star)
    heavy = {"influence": 10.0, "similarity": 10.0}

    def share(pool):
        wins = sum(contact.choose(w, soc, me, "open", pool, heavy, np.random.default_rng([3, i]), 1.0, set())[0].id == 20
                   for i in range(300))
        return wins / 300

    assert share(20) > 0.9          # everyone is weighed: the clear best almost always wins
    assert share(1) < 0.3           # one random person is weighed: the best is rarely the one
    assert 0.35 < share(10) < 0.65  # half of them are weighed: the best is among them about half the time


def test_nobody_is_contacted_twice_in_a_round_and_the_loop_ends_when_people_run_out(tmp_path):
    sim, crowd = _fresh(tmp_path, "run-out")
    try:
        sim.sc.contact, sim.sc.contact_budget = "group_only", 5
        gid = sim.society.create("group", crowd[0].id, round=0, topic="club")
        sim.society.join(gid, crowd[1].id, round=0)
        sim.society.join(gid, crowd[2].id, round=0)
        sim._contacts(crowd[:3], 0)
        per = dict(sim.store.db.execute(
            "SELECT sender_id, COUNT(*) FROM society_messages GROUP BY sender_id").fetchall())
        assert per == {crowd[0].id: 2, crowd[1].id: 2, crowd[2].id: 2}     # each of the two others, once
    finally:
        sim.close()


def test_an_account_that_is_not_a_voice_neither_talks_nor_listens(tmp_path):
    sim, crowd = _fresh(tmp_path, "account")
    try:
        account = next(a for a in sim.world.agents if a.kind == "account")
        account.attrs["llm"] = False
        assert not account.is_llm
        account.stance, crowd[0].stance = -0.9, 0.9
        sim._contacts([account], 0)
        assert sim.store.db.execute("SELECT COUNT(*) FROM society_messages").fetchone()[0] == 0
        sim._contact(crowd[0], account, PARTS, 1.0, 0)
        assert account.stance == -0.9
    finally:
        sim.close()


def test_the_reason_names_the_score_and_only_groups_count_as_shared_groups(tmp_path):
    sim, crowd = _fresh(tmp_path, "reason")
    try:
        a, b = crowd[0], crowd[1]
        sim._contact(a, b, PARTS, 1.2, 0)
        reason = sim.store.db.execute("SELECT reason FROM society_messages").fetchone()[0]
        assert reason.startswith("crowd contact, score 1.200 (trust 0.50, familiarity 0.00, similarity 0.40, influence 0.30)")
        soc = sim.society
        soc.direct(crowd[2].id, crowd[3].id, round=0)                      # a private chat is not a group
        oid = soc.create("open", crowd[2].id, round=0, topic="news")
        soc.join(oid, crowd[3].id, round=0)                                # nor is an open discussion
        assert not soc.share_group(crowd[2].id, crowd[3].id)
    finally:
        sim.close()

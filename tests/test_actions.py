"""Bad or out-of-place actions from a model must be ignored, never crash a run."""
import numpy as np
import pytest

from agora.sim.engine import RoundOutput, Simulation


@pytest.fixture
def sim(project):
    s = Simulation(project)
    s.prepare()
    s.run(rounds=6)
    yield s
    s.close()


def _agent(sim, platform, member=True):
    w = sim.world
    for a in w.agents:
        if a.kind == "llm" and platform in a.platforms:
            if not member or platform == "x" or w.member_of[a.id].get(platform):
                return a
    pytest.skip(f"no llm agent on {platform}")


def _apply(sim, a, action):
    out = RoundOutput()
    res = sim._apply(a, action, 6, 24.0, [], np.random.default_rng(0), out)
    return res, out


def test_garbage_actions_ignored(sim):
    a = _agent(sim, "x")
    for bad in [{}, {"type": "dance"}, {"type": "like", "target": "p999999"},
                {"type": "like", "target": "banana"}, {"type": "post", "where": "x", "text": ""},
                {"type": "post", "where": "whatsapp:Not My Group", "text": "hi"},
                {"type": "convert", "name": "buy"}, {"type": "follow", "target": "@nobody"}]:
        res, out = _apply(sim, a, bad)
        assert res is None and not out.posts and not out.engagements


def test_reddit_like_becomes_upvote(sim):
    w = sim.world
    a = _agent(sim, "reddit")
    space = w.member_of[a.id]["reddit"][0]
    target = next((w.posts[p] for p in w.space_posts.get(("reddit", space), [])
                   if w.posts[p].author != a.id), None)
    if target is None:
        other = next(x for x in w.agents if space in w.member_of[x.id].get("reddit", []) and x.id != a.id)
        target = sim._new_post(other, 6, 24.0, "reddit", space, "post", "test thread", 0.2)
    res, out = _apply(sim, a, {"type": "like", "target": f"p{target.id}"})
    assert res and out.engagements[0][2] == "upvote"


def test_cannot_touch_groups_you_are_not_in(sim):
    w = sim.world
    wa_posts = [p for p in w.posts if p.platform == "whatsapp"]
    assert wa_posts
    p = wa_posts[0]
    outsider = next(a for a in w.agents if a.kind == "llm"
                    and p.space not in w.member_of[a.id].get("whatsapp", []))
    res, out = _apply(sim, outsider, {"type": "reply", "target": f"p{p.id}", "text": "hello"})
    assert res is None and not out.posts


def test_post_reply_and_follow_work(sim):
    a = _agent(sim, "x")
    res, out = _apply(sim, a, {"type": "post", "where": "x", "text": "hello world"})
    assert res and out.posts[0].platform == "x"
    other = next(x for x in sim.world.agents if "x" in x.platforms and x.id != a.id
                 and x.id not in sim.world.following[a.id])
    res, out = _apply(sim, a, {"type": "follow", "target": f"@{other.handle}"})
    assert res and out.follows == [(a.id, other.id)]

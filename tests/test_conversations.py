"""Agents talk to each other: inbox, threads, private messages, mentions, mute, search."""
import sqlite3

import numpy as np
import pytest

from agora.sim.engine import RoundOutput, Simulation
from agora.sim.llm_agent import render_post


@pytest.fixture(scope="module")
def done(tmp_path_factory):
    from conftest import make_project
    p = make_project(tmp_path_factory.mktemp("conv"))
    s = Simulation(p)
    s.prepare()
    s.run()
    s.close()
    return p


def test_back_and_forth_threads_and_dms(done):
    db = sqlite3.connect(done / "agora.db")
    posts = {r[0]: r for r in db.execute("SELECT id, author, parent, kind FROM posts")}

    def chain(pid):
        authors = []
        while pid is not None:
            authors.append(posts[pid][1])
            pid = posts[pid][2]
        return authors

    longest = max((chain(p) for p in posts if posts[p][3] == "reply"), key=len)
    assert len(longest) >= 3
    # a real exchange: the same two people alternate
    assert any(len(c) >= 3 and len(set(c[:3])) == 2 and c[0] == c[2]
               for c in (chain(p) for p in posts if posts[p][3] == "reply"))
    pairs = db.execute("SELECT space, COUNT(DISTINCT author) FROM posts WHERE kind='dm' GROUP BY space").fetchall()
    assert any(n == 2 for _, n in pairs)              # both people wrote in a private chat


@pytest.fixture
def sim(project):
    s = Simulation(project)
    s.prepare()
    s.run(rounds=8)
    yield s
    s.close()


def _llm_agents(sim, plat):
    return [a for a in sim.world.agents if a.kind == "llm" and plat in a.platforms]


def _apply(sim, a, x, out=None):
    out = out or RoundOutput()
    return sim._apply(a, x, 8, 32.0, [], np.random.default_rng(0), out), out


def test_inbox_reply_mention_and_dm(sim):
    w = sim.world
    a, b = _llm_agents(sim, "x")[:2]
    post = sim._new_post(a, 8, 32.0, "x", "", "post", "Anyone tried the sample?", 0.1)
    res, out = _apply(sim, b, {"type": "reply", "target": f"p{post.id}", "text": f"Yes @{a.handle}, it was fine"})
    assert res
    reply = out.posts[0]
    since = 31.0
    assert reply.id in w.inbox(a.id, since)
    line = render_post(w, reply, a)
    assert line.startswith("[reply to you]") and "Anyone tried the sample?" in line
    res, out = _apply(sim, b, {"type": "dm", "to": f"@{a.handle}", "text": "Did you register?"})
    assert res and out.posts[0].kind == "dm"
    assert out.posts[0].id in w.inbox(a.id, since)
    assert "private message" in render_post(w, out.posts[0], a)
    # replying to a DM answers privately
    res, out = _apply(sim, a, {"type": "reply", "target": f"p{out.posts[0].id}", "text": "Yes!"})
    assert res and out.posts[0].kind == "dm" and out.posts[0].space == w.posts[out.posts[0].id].space


def test_dm_needs_a_shared_app(sim):
    w = sim.world
    seniors_only_wa = [a for a in w.agents if a.kind == "llm" and a.platforms == ["whatsapp", "facebook", "youtube"]]
    redditors = [a for a in w.agents if a.kind == "llm" and "reddit" in a.platforms and "facebook" not in a.platforms
                 and "whatsapp" not in a.platforms]
    if seniors_only_wa and redditors:
        a, b = seniors_only_wa[0], redditors[0]
    else:
        # this small test world has no such pair, so make one: two people with no app in common
        a, b = [x for x in w.agents if x.kind == "llm"][:2]
        a.platforms = ["whatsapp"]
        b.platforms = ["reddit"]
    res, _ = _apply(sim, a, {"type": "dm", "to": f"@{b.handle}", "text": "hi"})
    assert res is None


def test_quote_mute_unfollow_search(sim):
    w = sim.world
    a, b = _llm_agents(sim, "x")[:2]
    post = sim._new_post(b, 8, 32.0, "x", "", "post", "Free probiotic samples in Guntur", 0.4)
    res, out = _apply(sim, a, {"type": "quote", "target": f"p{post.id}", "text": "Interesting"})
    assert res and out.posts[0].kind == "quote" and out.posts[0].parent == post.id
    ig = _llm_agents(sim, "instagram")[0]
    ig_post = sim._new_post(b, 8, 32.0, "instagram", "", "post", "pic", 0.4) if "instagram" in b.platforms else None
    if ig_post:
        assert _apply(sim, ig, {"type": "quote", "target": f"p{ig_post.id}", "text": "x"})[0] is None
    w.add_follow("x", a.id, b.id)
    res, out = _apply(sim, a, {"type": "unfollow", "target": f"@{b.handle}"})
    assert res and out.unfollows == [("x", a.id, b.id)] and b.id not in w.following["x"][a.id]
    res, out = _apply(sim, a, {"type": "mute", "target": f"@{b.handle}"})
    assert res and b.id in w.muted[a.id]
    res, _ = _apply(sim, a, {"type": "search", "query": "probiotic samples Guntur"})
    assert res and "found" in res


def test_mutes_and_unfollows_survive_resume(project):
    s = Simulation(project)
    s.prepare()
    s.run(rounds=4)
    w = s.world
    a, b = [x for x in w.agents if x.kind == "llm" and "x" in x.platforms][:2]
    out = RoundOutput()
    w.add_follow("x", a.id, b.id)
    out.follows.append(("x", a.id, b.id))
    s._apply(a, {"type": "unfollow", "target": f"@{b.handle}", "platform": "x"}, 4, 16.0, [], np.random.default_rng(0), out)
    s._apply(a, {"type": "mute", "target": f"@{b.handle}"}, 4, 16.0, [], np.random.default_rng(0), out)
    s.store.commit_round(99, sim_time="x", agents=[], posts=[], engagements=[], follows=out.follows,
                         conversions=[], thoughts=[], polls=[], poll_results=[], events=[],
                         stats={"active": 0, "llm_calls": 0, "cache_hits": 0, "seconds": 0},
                         unfollows=out.unfollows, mutes=out.mutes)
    s.close()
    from agora.sim.world import World
    from agora.store import Store
    st = Store(project / "agora.db")
    w2 = World.load(st)
    st.close()
    assert b.id not in w2.following["x"][a.id] and b.id in w2.muted[a.id]

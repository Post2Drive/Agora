"""In-memory state of a running simulation: agents, posts and the indexes the
platforms need to build feeds quickly. Everything here can be rebuilt from the store."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: int
    handle: str
    kind: str                 # llm | crowd | account
    name: str
    segment: str
    persona: str
    platforms: list[str]
    initial_stance: float
    stubbornness: float
    activity: float
    influence: float
    openness: float
    attrs: dict = field(default_factory=dict)
    stance: float = 0.0
    memory: list[str] = field(default_factory=list)
    converted: set[str] = field(default_factory=set)
    last_seen: float = -1e9   # sim hours; WhatsApp shows messages newer than this

    @property
    def is_llm(self) -> bool:
        return self.kind in ("llm", "account") and self.attrs.get("llm", True)


@dataclass
class Post:
    id: int
    round: int
    t: float
    platform: str
    space: str
    author: int
    parent: int | None
    root: int
    kind: str                 # post | reply | repost | forward
    text: str
    stance: float
    likes: int = 0
    ups: int = 0
    downs: int = 0
    reposts: int = 0
    replies: int = 0

    @property
    def engagement(self) -> int:
        return self.likes + self.ups - self.downs + 2 * self.reposts + 2 * self.replies


class World:
    def __init__(self):
        self.agents: list[Agent] = []
        self.by_handle: dict[str, Agent] = {}
        self.posts: list[Post] = []
        # follow graphs are per feed platform: following[platform][agent] -> {agents}
        self.following: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        self.followers: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        self.member_of: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.members: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.space_posts: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.author_posts: dict[int, list[int]] = defaultdict(list)
        self.feed_posts: dict[str, list[int]] = defaultdict(list)
        self.engaged: set[tuple[int, int, str]] = set()
        self.news: list[str] = []
        self.poll_results: dict[str, bool] = {}

    # ---------------------------------------------------------------- building
    def add_agent(self, a: Agent) -> None:
        assert a.id == len(self.agents)
        self.agents.append(a)
        self.by_handle[a.handle] = a

    def add_follow(self, platform: str, src: int, dst: int) -> bool:
        if src == dst or dst in self.following[platform][src]:
            return False
        self.following[platform][src].add(dst)
        self.followers[platform][dst].add(src)
        return True

    def add_member(self, agent: int, platform: str, space: str) -> None:
        if space not in self.member_of[agent][platform]:
            self.member_of[agent][platform].append(space)
            self.members[(platform, space)].append(agent)

    def add_post(self, p: Post) -> Post:
        assert p.id == len(self.posts)
        self.posts.append(p)
        self.author_posts[p.author].append(p.id)
        if not p.space:
            self.feed_posts[p.platform].append(p.id)
        else:
            self.space_posts[(p.platform, p.space)].append(p.id)
        if p.parent is not None:
            parent = self.posts[p.parent]
            if p.kind == "reply":
                parent.replies += 1
            elif p.kind in ("repost", "forward"):
                self.posts[p.root].reposts += 1
        return p

    def engage(self, agent: int, post: int, kind: str) -> bool:
        key = (agent, post, kind)
        if key in self.engaged:
            return False
        self.engaged.add(key)
        p = self.posts[post]
        if kind == "like":
            p.likes += 1
        elif kind == "upvote":
            p.ups += 1
        elif kind == "downvote":
            p.downs += 1
        return True

    @property
    def next_post_id(self) -> int:
        return len(self.posts)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, store) -> "World":
        w = cls()
        state = {r[0]: r[1:] for r in store.rows(
            "SELECT id, stance, memory, converted, last_seen FROM agent_state")}
        for row in store.rows("SELECT * FROM agents ORDER BY id"):
            (aid, handle, kind, name, seg, persona, plats, s0, stub, act, infl, opn, attrs) = row
            st = state[aid]
            w.add_agent(Agent(id=aid, handle=handle, kind=kind, name=name, segment=seg,
                              persona=persona, platforms=json.loads(plats), initial_stance=s0,
                              stubbornness=stub, activity=act, influence=infl, openness=opn,
                              attrs=json.loads(attrs), stance=st[0], memory=json.loads(st[1]),
                              converted=set(json.loads(st[2])), last_seen=st[3]))
        for plat, s, d in store.rows("SELECT platform, src, dst FROM follows ORDER BY rowid"):
            w.add_follow(plat, s, d)
        for a, p, sp in store.rows("SELECT agent, platform, space FROM memberships ORDER BY rowid"):
            w.add_member(a, p, sp)
        for row in store.rows("SELECT * FROM posts ORDER BY id"):
            w.add_post(Post(*row))
        for a, p, t in store.rows("SELECT agent, post, type FROM engagements ORDER BY rowid"):
            w.engage(a, p, t)
        for kind, detail in store.rows("SELECT kind, detail FROM event_log ORDER BY rowid"):
            if kind == "news":
                w.news.append(json.loads(detail)["text"])
        for name, passed in store.rows("SELECT name, passed FROM poll_results"):
            w.poll_results[name] = bool(passed)
        return w

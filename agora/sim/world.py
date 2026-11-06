"""In-memory state of a running simulation: agents, posts and the indexes the
platforms need to build feeds quickly. Everything here can be rebuilt from the store."""
from __future__ import annotations

import json
import re

MENTION = re.compile(r"@([A-Za-z0-9_]{2,40})")
DM_PREFIX = "@dm:"


def dm_space(a: int, b: int) -> str:
    x, y = sorted((a, b))
    return f"{DM_PREFIX}{x}-{y}"


def dm_people(space: str) -> tuple[int, int] | None:
    if not space.startswith(DM_PREFIX):
        return None
    x, _, y = space[len(DM_PREFIX):].partition("-")
    return int(x), int(y)
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
    prefs: dict = field(default_factory=dict)   # choice mode: option -> -1..1
    choice: str = ""                            # option voted for ("" = not yet)

    def favourite(self) -> tuple[str, float]:
        if not self.prefs:
            return "", 0.0
        o = max(sorted(self.prefs), key=lambda k: self.prefs[k])
        return o, self.prefs[o]

    def view_of(self, option: str) -> float:
        """This agent's opinion relevant to a post about `option` (or the topic)."""
        if option and self.prefs:
            return self.prefs.get(option, 0.0)
        return self.stance

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
    kind: str                 # post | reply | repost | forward | quote | dm
    text: str
    stance: float
    option: str = ""          # choice mode: the option this post is about (stance = for/against it)
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
        # inbox indexes: what is addressed to an agent
        self.replies_to: dict[int, list[int]] = defaultdict(list)    # replies/quotes of my posts
        self.mentions: dict[int, list[int]] = defaultdict(list)      # posts that @mention me
        self.dms: dict[int, list[int]] = defaultdict(list)           # private messages to me
        self.muted: dict[int, set[int]] = defaultdict(set)
        self.news: list[str] = []
        self.poll_results: dict[str, bool] = {}

    # ---------------------------------------------------------------- building
    def add_agent(self, a: Agent) -> None:
        assert a.id == len(self.agents)
        self.agents.append(a)
        self.by_handle[a.handle] = a

    def remove_follow(self, platform: str, src: int, dst: int) -> bool:
        if dst not in self.following[platform][src]:
            return False
        self.following[platform][src].discard(dst)
        self.followers[platform][dst].discard(src)
        return True

    def mute(self, src: int, dst: int) -> bool:
        if src == dst or dst in self.muted[src]:
            return False
        self.muted[src].add(dst)
        return True

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
            if p.kind in ("reply", "quote") and parent.author != p.author:
                self.replies_to[parent.author].append(p.id)
        if p.kind == "dm":
            pair = dm_people(p.space)
            if pair:
                other = pair[1] if pair[0] == p.author else pair[0]
                self.dms[other].append(p.id)
        elif p.text and "@" in p.text:
            for h in set(MENTION.findall(p.text)):
                a = self.by_handle.get(h)
                if a is not None and a.id != p.author:
                    self.mentions[a.id].append(p.id)
        return p

    def inbox(self, agent: int, since: float, limit: int = 4) -> list[int]:
        """Newest things addressed to this agent since they last looked."""
        out = []
        for src in (self.dms, self.replies_to, self.mentions):
            for pid in reversed(src.get(agent, [])):
                if self.posts[pid].t <= since:
                    break
                if self.posts[pid].author not in self.muted.get(agent, ()):
                    out.append(pid)
        out = sorted(set(out), key=lambda q: self.posts[q].t, reverse=True)
        return out[:limit]

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
            "SELECT id, stance, memory, converted, last_seen, prefs, choice FROM agent_state")}
        for row in store.rows("SELECT * FROM agents ORDER BY id"):
            (aid, handle, kind, name, seg, persona, plats, s0, stub, act, infl, opn, attrs) = row
            st = state[aid]
            w.add_agent(Agent(id=aid, handle=handle, kind=kind, name=name, segment=seg,
                              persona=persona, platforms=json.loads(plats), initial_stance=s0,
                              stubbornness=stub, activity=act, influence=infl, openness=opn,
                              attrs=json.loads(attrs), stance=st[0], memory=json.loads(st[1]),
                              converted=set(json.loads(st[2])), last_seen=st[3],
                              prefs=json.loads(st[4] or "{}"), choice=st[5] or ""))
        for plat, s, d in store.rows("SELECT platform, src, dst FROM follows ORDER BY rowid"):
            w.add_follow(plat, s, d)
        for a, p, sp in store.rows("SELECT agent, platform, space FROM memberships ORDER BY rowid"):
            w.add_member(a, p, sp)
        for row in store.rows("SELECT * FROM posts ORDER BY id"):
            w.add_post(Post(*row))
        for a, p, t in store.rows("SELECT agent, post, type FROM engagements ORDER BY rowid"):
            w.engage(a, p, t)
        for src, dst in store.rows("SELECT src, dst FROM mutes ORDER BY rowid"):
            w.mute(src, dst)
        for kind, detail in store.rows("SELECT kind, detail FROM event_log ORDER BY rowid"):
            if kind == "news":
                w.news.append(json.loads(detail)["text"])
        for name, passed in store.rows("SELECT name, passed FROM poll_results"):
            w.poll_results[name] = bool(passed)
        return w

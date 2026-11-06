"""Scenario definition: who is in the world, where they talk, what happens when,
and which real-world actions (conversions) we want to predict.

A scenario is a YAML file inside a project folder. Phase 2 generates it from your
documents; it can always be edited by hand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .platforms import REGISTRY, is_spaced, resolve

PLATFORMS = tuple(REGISTRY)
DEFAULT_PLATFORMS = ("whatsapp", "instagram", "x")


class ScenarioError(ValueError):
    pass


@dataclass
class Segment:
    name: str
    share: float
    persona: str
    stance_mean: float = 0.0
    stance_sd: float = 0.3
    stubbornness: float = 0.4        # 0 = blown by every opinion, 1 = never changes
    activity: float = 0.4            # chance of being active in a waking round
    influence: float = 1.0           # how much others weigh this segment's posts
    openness: float = 0.6            # bounded-confidence width: how different an opinion can be and still persuade
    platforms: list[str] = field(default_factory=lambda: list(DEFAULT_PLATFORMS))
    occupations: list[str] = field(default_factory=list)
    age: tuple[int, int] = (25, 60)
    names: list[str] = field(default_factory=list)
    llm_share: float | None = None   # share of LLM voices (defaults to `share`)


@dataclass
class Account:
    """A named agent: a brand, an official, a committee member, a journalist..."""
    id: str
    name: str
    persona: str
    segment: str = "accounts"
    stance: float = 0.0
    stubbornness: float = 0.9
    activity: float = 0.3
    influence: float = 3.0
    platforms: list[str] = field(default_factory=lambda: list(DEFAULT_PLATFORMS))
    llm: bool = True                 # acts on its own each round
    spaces: list[str] = field(default_factory=list)   # groups/communities it joins


@dataclass
class Space:
    """A WhatsApp group or Reddit community."""
    platform: str
    name: str
    size: int = 100
    segments: dict[str, float] = field(default_factory=dict)   # segment -> weight
    description: str = ""
    exclusive: str = ""   # spaces sharing this tag never share members (e.g. "home": one apartment each)


@dataclass
class Event:
    round: int
    type: str                         # post | news | poll
    text: str = ""
    account: str = ""
    platform: str = ""
    spaces: list[str] = field(default_factory=list)   # [] or ["*"] = all spaces on platform
    when: dict[str, Any] = field(default_factory=dict)  # {poll: name, result: yes}
    # poll fields
    name: str = ""
    question: str = ""
    voters: list[str] = field(default_factory=list)   # segment names or account ids
    threshold: float = 0.5


@dataclass
class Conversion:
    """A real-world action agents can take: register, buy, sign up, vote..."""
    name: str
    label: str
    open_round: int = 0
    close_round: int = 10**9
    requires: list[str] = field(default_factory=list)  # any one of these must come first
    when: dict[str, Any] = field(default_factory=dict)  # {poll: name, result: yes}; or {any: [...]}
    base: float = -4.0                # crowd logistic: base log-odds per active round
    stance_weight: float = 3.0
    exposure_weight: float = 0.6      # per log(1 + relevant posts seen)
    eligible_segments: list[str] = field(default_factory=list)  # [] = everyone
    eligible_spaces: list[str] = field(default_factory=list)    # members of these groups only
    # What happens to people who converted, e.g. they receive and try the product:
    # {at_round: 18 | after: 6, note: "...", stance_mean: 0.1, stance_sd: 0.3}
    experience: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scenario:
    name: str
    topic: str
    question: str
    context: str
    seed: int = 42
    rounds: int = 40
    round_hours: float = 3.0
    start: datetime = field(default_factory=lambda: datetime(2026, 1, 5, 8, 0))
    llm_agents: int = 40
    crowd_agents: int = 2000
    feed_size: int = 8
    memory_size: int = 10
    avg_follows: int = 15
    homophily: float = 0.6
    segments: list[Segment] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    spaces: list[Space] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    conversions: list[Conversion] = field(default_factory=list)
    voices: list[dict[str, Any]] = field(default_factory=list)  # hand-written/drafted LLM personas
    # optional money view for the report: {currency, cost: {conversion: per person},
    # value: {conversion: per person}, fixed_cost}
    economics: dict[str, Any] = field(default_factory=dict)
    persuasion: float = 0.35          # how far one round of exposure moves an open-minded person
    targets: dict[str, float] = field(default_factory=dict)  # goals for forecasts, e.g. {buy: 50}
    # force decision outcomes that are already known (votes are still simulated)
    fixed_polls: dict[str, bool] = field(default_factory=dict)
    llm: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ helpers
    def segment(self, name: str) -> Segment:
        for s in self.segments:
            if s.name == name:
                return s
        raise ScenarioError(f"Unknown segment '{name}'")

    def conversion(self, name: str) -> Conversion:
        for c in self.conversions:
            if c.name == name:
                return c
        raise ScenarioError(f"Unknown conversion '{name}'")

    def spaces_on(self, platform: str) -> list[Space]:
        return [s for s in self.spaces if s.platform == platform]


# ---------------------------------------------------------------------- loading
def _pick(d: dict, cls, rename: dict | None = None):
    rename = rename or {}
    fields = cls.__dataclass_fields__
    kw = {}
    for k, v in d.items():
        k2 = rename.get(k, k)
        if k2 not in fields:
            raise ScenarioError(f"Unknown field '{k}' in {cls.__name__}")
        kw[k2] = v
    return kw


def _segment(d: dict) -> Segment:
    d = dict(d)
    st = d.pop("stance", None)
    kw = _pick(d, Segment)
    if isinstance(st, dict):
        kw["stance_mean"] = float(st.get("mean", 0.0))
        kw["stance_sd"] = float(st.get("sd", 0.3))
    elif st is not None:
        kw["stance_mean"] = float(st)
    if "age" in kw:
        kw["age"] = tuple(kw["age"])
    return Segment(**kw)


def _plat(p) -> str:
    """'Twitter' -> 'x', 'IG' -> 'instagram'; unknown names pass through to fail validation."""
    return resolve(p) or str(p)


def from_dict(d: dict) -> Scenario:
    d = dict(d)
    raw = dict(d)
    pop = d.pop("population", {}) or {}
    segs = [_segment(s) for s in d.pop("segments", [])]
    for s in segs:
        s.platforms = list(dict.fromkeys(_plat(p) for p in s.platforms))
    accts = [Account(**_pick(a, Account)) for a in d.pop("accounts", [])]
    for a in accts:
        a.platforms = list(dict.fromkeys(_plat(p) for p in a.platforms))
    spaces = []
    for p, items in (d.pop("spaces", {}) or {}).items():
        for s in items:
            spaces.append(Space(platform=_plat(p), **_pick(s, Space)))
    events = [Event(**_pick(e, Event, {"at_round": "round"})) for e in d.pop("events", [])]
    for e in events:
        if e.platform:
            e.platform = _plat(e.platform)
    convs = []
    for c in d.pop("conversions", []):
        c = dict(c)
        if isinstance(c.get("requires"), str):
            c["requires"] = [c["requires"]] if c["requires"] else []
        convs.append(Conversion(**_pick(c, Conversion)))
    if "start" in d and not isinstance(d["start"], datetime):
        d["start"] = datetime.fromisoformat(str(d["start"]))
    sc = Scenario(**_pick(d, Scenario), segments=segs, accounts=accts, spaces=spaces,
                  events=events, conversions=convs, raw=raw,
                  **{k: pop[k] for k in ("llm_agents", "crowd_agents") if k in pop})
    validate(sc)
    return sc


def load(path: str | Path) -> Scenario:
    with open(path, encoding="utf-8") as f:
        return from_dict(yaml.safe_load(f))


def validate(sc: Scenario) -> None:
    if not sc.segments:
        raise ScenarioError("A scenario needs at least one segment.")
    total = sum(s.share for s in sc.segments)
    if total <= 0:
        raise ScenarioError("Segment shares must add up to more than 0.")
    names = {s.name for s in sc.segments}
    ids = {a.id for a in sc.accounts}
    for s in sc.segments:
        bad = set(s.platforms) - set(PLATFORMS)
        if bad:
            raise ScenarioError(f"Segment {s.name}: unknown platforms {bad}. "
                                f"Available: {', '.join(PLATFORMS)}")
        if not -1 <= s.stance_mean <= 1:
            raise ScenarioError(f"Segment {s.name}: stance mean must be between -1 and 1")
    for sp in sc.spaces:
        if sp.platform not in REGISTRY or not is_spaced(sp.platform):
            spaced = [k for k in PLATFORMS if is_spaced(k)]
            raise ScenarioError(f"Space {sp.name}: groups/communities exist on {', '.join(spaced)} only")
        for seg in sp.segments:
            if seg not in names:
                raise ScenarioError(f"Space {sp.name}: unknown segment '{seg}'")
    for a in sc.accounts:
        bad = set(a.platforms) - set(PLATFORMS)
        if bad:
            raise ScenarioError(f"Account {a.id}: unknown platforms {bad}")
    space_names = {sp.name for sp in sc.spaces}
    polls = set()
    conv_names = {c.name for c in sc.conversions}
    for e in sorted(sc.events, key=lambda e: e.round):
        if e.type not in ("post", "news", "poll"):
            raise ScenarioError(f"Event at round {e.round}: unknown type '{e.type}'")
        if e.account and e.account not in ids:
            raise ScenarioError(f"Event at round {e.round}: unknown account '{e.account}'")
        if e.type == "post" and e.platform not in REGISTRY:
            raise ScenarioError(f"Event at round {e.round}: unknown platform '{e.platform}'")
        for s in e.spaces:
            if s != "*" and s not in space_names:
                raise ScenarioError(f"Event at round {e.round}: unknown space '{s}'")
        if e.type == "poll":
            if not e.name or not e.question:
                raise ScenarioError(f"Poll at round {e.round} needs a name and a question")
            for v in e.voters:
                if v not in names and v not in ids:
                    raise ScenarioError(f"Poll {e.name}: unknown voter group '{v}'")
            polls.add(e.name)
        for p in _cond_polls(e.when):
            if p not in polls:
                raise ScenarioError(f"Event at round {e.round} depends on poll "
                                    f"'{p}' which has not happened before it")
    for c in sc.conversions:
        for req in c.requires:
            if req not in conv_names:
                raise ScenarioError(f"Conversion {c.name}: requires unknown '{req}'")
        for p in _cond_polls(c.when):
            if p not in polls:
                raise ScenarioError(f"Conversion {c.name}: depends on unknown poll '{p}'")
        for s in c.eligible_spaces:
            if s not in space_names:
                raise ScenarioError(f"Conversion {c.name}: unknown space '{s}'")
        for s in c.eligible_segments:
            if s not in names:
                raise ScenarioError(f"Conversion {c.name}: unknown segment '{s}'")
    if sc.economics:
        for k in ("cost", "value"):
            for name, amt in (sc.economics.get(k) or {}).items():
                if name not in conv_names:
                    raise ScenarioError(f"economics.{k}: unknown conversion '{name}'")
                if not isinstance(amt, (int, float)):
                    raise ScenarioError(f"economics.{k}.{name} must be a number")
    for v in sc.voices:
        if not isinstance(v, dict) or v.get("segment") not in names or not v.get("persona"):
            raise ScenarioError("Each voice needs a known 'segment' and a 'persona'")
    for name in sc.fixed_polls:
        if name not in polls:
            raise ScenarioError(f"fixed_polls: unknown decision '{name}'")
    for name in sc.targets:
        if name not in conv_names:
            raise ScenarioError(f"targets: unknown action '{name}'")
    if not 0 <= sc.persuasion <= 1:
        raise ScenarioError("persuasion must be between 0 and 1")
    if sc.rounds < 1 or sc.round_hours <= 0:
        raise ScenarioError("rounds must be >= 1 and round_hours > 0")


def _cond_polls(cond: dict) -> list[str]:
    """Poll names a condition refers to. Forms: {poll, result} or {any: [cond, ...]}."""
    if not cond:
        return []
    if "any" in cond:
        return [p for c in cond["any"] for p in _cond_polls(c)]
    return [cond.get("poll")]


def dump_template() -> str:
    return yaml.safe_dump({"name": "my-scenario", "topic": "...", "question": "...",
                           "context": "...", "segments": [], "accounts": [], "spaces": {},
                           "events": [], "conversions": []}, sort_keys=False)

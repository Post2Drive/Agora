"""Prompts and parsing for agents that think and write with the language model."""
from __future__ import annotations

from datetime import datetime

from ..llm import parse_json
from ..platforms import REGISTRY
from .platforms import actions_for, where_options
from .world import Agent, Post, World

MAX_ACTIONS = 3


def label(platform: str) -> str:
    return REGISTRY[platform].label


def stance_words(x: float) -> str:
    if x <= -0.6:
        return "strongly against it"
    if x <= -0.2:
        return "doubtful, leaning against"
    if x < 0.2:
        return "undecided"
    if x < 0.6:
        return "fairly positive"
    return "very positive, keen"


def _snip(t: str, n: int = 140) -> str:
    t = t.replace("\n", " ").strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def render_post(world: World, p: Post, me: Agent | None = None) -> str:
    author = world.agents[p.author]
    src = world.posts[p.root] if p.kind in ("repost", "forward") else p
    text = _snip(src.text, 300)
    if p.kind == "dm":
        return f"[p{p.id}] (private message on {label(p.platform)}) {author.name} (@{author.handle}) to you: \"{text}\""
    where = label(p.platform) + (f" · {p.space}" if p.space else "")
    tag = ""
    if me is not None and p.author != me.id:
        if p.parent is not None and world.posts[p.parent].author == me.id:
            tag = "[reply to you] " if p.kind == "reply" else "[quoted you] "
        elif f"@{me.handle}" in (p.text or ""):
            tag = "[mentions you] "
    if p.kind == "repost":
        head = f"@{author.handle} reposted @{world.agents[src.author].handle}"
    elif p.kind == "forward":
        head = f"{author.name} forwarded a message"
    elif p.kind in ("reply", "quote") and p.parent is not None:
        par = world.posts[p.parent]
        verb = "replying to" if p.kind == "reply" else "quoting"
        who = "you" if me is not None and par.author == me.id else f"{world.agents[par.author].name} (@{world.agents[par.author].handle})"
        head = f"{author.name} (@{author.handle}) {verb} {who} who said \"{_snip(par.text, 120)}\" —"
    else:
        head = f"{author.name} (@{author.handle})"
    spec = REGISTRY[p.platform]
    if spec.kind == "forum":
        counts = f"[{src.ups - src.downs} points, {src.replies} comments]"
    elif spec.kind == "feed":
        share = spec.words.get("repost", "repost")
        counts = f"[{src.likes} likes, {src.reposts} {share}s, {src.replies} comments]"
    else:
        counts = f"[{src.likes} reactions]" if src.likes else ""
    return f"{tag}[p{p.id}] ({where}) {head}: \"{text}\" {counts}".rstrip()


def decision_messages(world: World, sc, a: Agent, feed: list[Post], now: datetime,
                      conversions: list, facts: list[str] | None = None,
                      trending: dict | None = None, recalled: list[str] | None = None) -> list[dict]:
    styles = "\n".join(f"- {label(p)}: {REGISTRY[p].style}" for p in a.platforms)
    system = (
        f"You are {a.name}, a real person. {a.persona}\n"
        f"You use these apps, and write the way people do on each:\n{styles}\n"
        "Stay fully in character: your own interests, budget, doubts and habits. Plain "
        "everyday English, no marketing language. You are not an assistant and never mention "
        "AI. Most people scroll without posting; only act when you genuinely would.")
    lines = [f"Background you know:\n{sc.context.strip()}"]
    if facts:
        lines.append("Details you may have come across:\n" + "\n".join(f"- {f}" for f in facts))
    if world.news:
        lines.append("What has happened so far:\n" + "\n".join(f"- {n}" for n in world.news[-6:]))
    lines.append(f"It is {now:%A %d %B, %I:%M %p}.")
    if a.memory:
        mem = [m for m in a.memory if m.startswith("Looking back:")][:1] + \
              [m for m in a.memory if not m.startswith("Looking back:")][-sc.memory_size:]
        lines.append("Your memory:\n" + "\n".join(f"- {m}" for m in mem))
    if recalled:
        lines.append("You also remember hearing:\n" + "\n".join(f"- {m}" for m in recalled))
    lines.append(f"Your current feeling about {sc.topic}: {stance_words(a.stance)}.")
    if trending:
        lines.append("Trending: " + "; ".join(f"{label(k)}: {', '.join(v)}" for k, v in trending.items() if v))
    if feed:
        lines.append("On your screen now (things addressed to you first):\n"
                     + "\n".join(render_post(world, p, a) for p in feed))
    else:
        lines.append("Nothing new on your screen right now.")
    where = where_options(world, a)
    acts = sorted({x for p in a.platforms for x in actions_for(p)})
    vocab = sorted({f"{v} = {k}" for p in a.platforms for k, v in REGISTRY[p].words.items()
                    if v != k})
    lines.append(
        "You may: " + ", ".join(acts) + ", or do nothing."
        + (f" (On these apps: {'; '.join(vocab)}.)" if vocab else "") + "\n"
        f"Places you can post (\"where\"): {', '.join(where) if where else 'none'}.\n"
        "like/upvote/downvote/repost/forward/reply/quote need a target like \"p12\" (quote and reply "
        "need \"text\"); follow/unfollow/mute need a target post or @handle; forward may add \"to\": a "
        "group you are in. You can also send a private message {\"type\": \"dm\", \"to\": \"@handle\", "
        "\"text\": \"...\"}, mention someone with @handle in any text, or {\"type\": \"search\", "
        "\"query\": \"...\"} to look something up. If someone replied to you or messaged you, it is "
        "natural to answer.")
    if conversions:
        lines.append("Real-life actions open to you right now (only if you truly would):\n" +
                     "\n".join(f"- {c.name}: {c.label}" for c in conversions))
    lines.append(
        f"Reply with JSON only, at most {MAX_ACTIONS} actions (an empty list is normal):\n"
        '{"thoughts": "one short sentence of what you privately think", '
        '"stance": <number from -1 (strongly against) to 1 (strongly for) on ' + sc.topic + '>, '
        '"actions": [{"type": "post", "where": "<a place from the list>", "text": "..."}, '
        '{"type": "reply", "target": "p12", "text": "..."}, {"type": "like", "target": "p7"}, '
        '{"type": "convert", "name": "..."}]}')
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(lines)}]


def decision_meta(world: World, sc, a: Agent, feed: list[Post], conversions: list) -> dict:
    """Extra info only the mock backend uses."""
    return {"task": "decide", "stance": a.stance, "topic": sc.topic,
            "feed": [{"id": f"p{p.id}", "stance": world.posts[p.root].stance if p.kind in
                      ("repost", "forward") else p.stance, "dm": p.kind == "dm",
                      "author": f"@{world.agents[p.author].handle}",
                      "to_me": p.kind == "dm" or (p.parent is not None and world.posts[p.parent].author == a.id)
                      or f"@{a.handle}" in (p.text or "")} for p in feed],
            "actions": sorted({x for p in a.platforms for x in actions_for(p)}),
            "where": where_options(world, a),
            "conversions": [{"name": c.name, "mock_threshold": 0.25} for c in conversions]}


def parse_decision(raw: str, a: Agent) -> dict:
    d = parse_json(raw)
    try:
        stance = float(d.get("stance", a.stance))
    except (TypeError, ValueError):
        stance = a.stance
    stance = max(-1.0, min(1.0, stance))
    acts = d.get("actions") or []
    if not isinstance(acts, list):
        acts = []
    clean = []
    for x in acts[:MAX_ACTIONS]:
        if isinstance(x, dict) and isinstance(x.get("type"), str):
            clean.append(x)
    thoughts = str(d.get("thoughts", ""))[:300]
    return {"stance": stance, "actions": clean, "thoughts": thoughts, "ok": bool(d)}


def poll_messages(world: World, sc, a: Agent, question: str, now: datetime) -> list[dict]:
    system = (f"You are {a.name}. {a.persona}\nAnswer as this person would, honestly and in "
              "character. You are not an assistant.")
    news = ("\nWhat has happened so far:\n" + "\n".join(f"- {n}" for n in world.news[-6:])) if world.news else ""
    mem = ("\nYour recent memory:\n" + "\n".join(f"- {m}" for m in a.memory[-6:])) if a.memory else ""
    user = (f"Background:\n{sc.context.strip()}{news}{mem}\n\nIt is {now:%A %d %B}.\n"
            f"Your current feeling about {sc.topic}: {stance_words(a.stance)}.\n\n"
            f"Decision you must make: {question}\n"
            'Reply with JSON only: {"vote": "yes" or "no", "reason": "one sentence"}')
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

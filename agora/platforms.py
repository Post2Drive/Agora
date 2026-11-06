"""Every simulated platform, described as data.

Three kinds cover how social platforms actually work:
  feed  - public posts ranked by an algorithm from who you follow + what is trending
          (X, Threads, Instagram, Facebook, LinkedIn, YouTube, TikTok)
  forum - topic communities with threads and votes (Reddit, Facebook Groups)
  chat  - private groups, newest first, forwarding (WhatsApp, Telegram)

Adding a platform is one entry here. Action names inside the engine are always the
canonical ones (post, reply, like, upvote, downvote, repost, forward, follow); `words`
gives the platform's own vocabulary for prompts and the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    label: str
    kind: str                         # feed | forum | chat
    actions: tuple[str, ...]
    style: str                        # how people write here (goes into prompts)
    words: dict = field(default_factory=dict)   # canonical action -> platform word
    max_len: int = 500
    half_life_h: float = 10.0         # feed: how fast posts fade
    window_h: float = 48.0            # how far back feeds look
    dms: bool = True                  # private messages between two people
    aliases: tuple[str, ...] = ()


FEED = ("post", "reply", "like", "repost", "quote", "follow", "unfollow", "mute")
FEED_NO_QUOTE = ("post", "reply", "like", "repost", "follow", "unfollow", "mute")
FORUM = ("post", "reply", "upvote", "downvote", "mute")
CHAT = ("post", "reply", "like", "forward", "mute")

REGISTRY: dict[str, PlatformSpec] = {p.key: p for p in [
    PlatformSpec("x", "X", "feed", FEED,
                 "short public posts under 280 characters, blunt opinions, occasional hashtag",
                 {"repost": "repost", "reply": "reply"}, 280, aliases=("twitter", "x.com", "tweet")),
    PlatformSpec("threads", "Threads", "feed", FEED,
                 "casual conversational posts, friendlier than X",
                 {"repost": "repost", "reply": "reply"}, 500, aliases=("meta threads",)),
    PlatformSpec("instagram", "Instagram", "feed", FEED_NO_QUOTE,
                 "a post is a photo or reel caption: describe the picture in [brackets], then a "
                 "short caption with emojis and a few hashtags; comments are short",
                 {"repost": "share to story", "reply": "comment"}, 400, half_life_h=14,
                 aliases=("insta", "ig", "instagram reels", "reels")),
    PlatformSpec("facebook", "Facebook", "feed", FEED,
                 "longer personal posts to friends and family, comments under posts, sharing news",
                 {"repost": "share", "reply": "comment", "follow": "add friend"}, 800,
                 half_life_h=18, aliases=("fb", "facebook feed")),
    PlatformSpec("linkedin", "LinkedIn", "feed", FEED,
                 "professional tone, work and industry angle, measured opinions",
                 {"repost": "repost", "reply": "comment", "follow": "connect"}, 900,
                 half_life_h=24, aliases=("linked in",)),
    PlatformSpec("youtube", "YouTube", "feed", FEED_NO_QUOTE,
                 "a post is a video: give a title and a one-line description; most people only "
                 "watch, like and comment",
                 {"post": "upload video", "repost": "share", "reply": "comment",
                  "follow": "subscribe"}, 400, half_life_h=36, window_h=120, dms=False,
                 aliases=("yt", "youtube shorts")),
    PlatformSpec("tiktok", "TikTok", "feed", FEED_NO_QUOTE,
                 "a post is a short video: describe it in [brackets] plus a punchy caption; "
                 "comments are very short and informal",
                 {"post": "post video", "repost": "repost", "reply": "comment"}, 300,
                 half_life_h=12, aliases=("tik tok",)),
    PlatformSpec("reddit", "Reddit", "forum", FORUM,
                 "anonymous, detailed and skeptical; threads have a title-like first line",
                 {"post": "start thread", "reply": "comment"}, 1500, window_h=120, dms=False,
                 aliases=("subreddit",)),
    PlatformSpec("facebook_groups", "Facebook Groups", "forum", FORUM,
                 "community group posts asking for recommendations and experiences",
                 {"post": "post in group", "reply": "comment", "upvote": "like",
                  "downvote": "hide"}, 1000, window_h=120, dms=False,
                 aliases=("facebook group", "fb group", "fb groups")),
    PlatformSpec("whatsapp", "WhatsApp", "chat", CHAT,
                 "group chat messages: short, informal, sometimes mixed with emojis",
                 {"like": "react", "forward": "forward"}, 600,
                 aliases=("wa", "whats app", "whatsapp group", "whatsapp groups")),
    PlatformSpec("telegram", "Telegram", "chat", CHAT,
                 "group or channel messages, links and forwards are common",
                 {"like": "react", "forward": "forward"}, 800, aliases=("tg",)),
]}

KINDS = ("feed", "forum", "chat")


def resolve(name: str) -> str | None:
    """Map what people (or models) write - 'Twitter', 'IG', 'fb group' - to a key."""
    n = str(name or "").strip().lower().replace("-", " ").replace("_", " ")
    for key, spec in REGISTRY.items():
        if n == key.replace("_", " ") or n == spec.label.lower() or n in spec.aliases:
            return key
    return None


def spec(key: str) -> PlatformSpec:
    return REGISTRY[key]


def is_spaced(key: str) -> bool:
    """Forums and chats are organised into spaces (communities / groups)."""
    return REGISTRY[key].kind in ("forum", "chat")


def describe_all() -> str:
    return ", ".join(f'"{k}" ({s.label}, {s.kind})' for k, s in REGISTRY.items())

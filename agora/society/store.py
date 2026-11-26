"""Durable store for native agent-to-agent communication (phase 1: data model only).

Nothing here is wired into the simulation engine yet. The store holds conversations
(direct, group, open, broadcast), memberships, an append-only message log, directed
relationships with a change log, and per-agent read cursors. Messages and relationship
changes cannot be updated or deleted (enforced by triggers), and `digest()` returns a
deterministic SHA-256 over all state so snapshots and replays can be compared exactly.
Agent identity is the engine's integer agent ID.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from ..pathsafe import UnsafePathError, require_safe_path

CONVERSATION_KINDS = ("direct", "group", "open", "broadcast")
_ROLES = ("member", "moderator", "owner")
_MAX_TEXT = 8000
_MAX_REASON = 2000

_SCHEMA = (
    """CREATE TABLE conversations (
        conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK (kind IN ('direct','group','open','broadcast')),
        topic TEXT NOT NULL,
        created_round INTEGER NOT NULL CHECK (created_round >= 0),
        pair_key TEXT UNIQUE
    )""",
    """CREATE TABLE memberships (
        conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id),
        agent_id INTEGER NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('member','moderator','owner')),
        joined_round INTEGER NOT NULL CHECK (joined_round >= 0),
        PRIMARY KEY (conversation_id, agent_id)
    )""",
    """CREATE TABLE messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id),
        sender_id INTEGER NOT NULL,
        round INTEGER NOT NULL CHECK (round >= 0),
        text TEXT NOT NULL,
        reason TEXT NOT NULL
    )""",
    """CREATE TABLE relationships (
        source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        trust REAL NOT NULL CHECK (trust >= 0 AND trust <= 1),
        familiarity REAL NOT NULL CHECK (familiarity >= 0 AND familiarity <= 1),
        last_contact_round INTEGER NOT NULL CHECK (last_contact_round >= -1),
        PRIMARY KEY (source_id, target_id),
        CHECK (source_id <> target_id)
    )""",
    """CREATE TABLE relationship_changes (
        change_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        round INTEGER NOT NULL,
        trust_delta REAL NOT NULL,
        familiarity_delta REAL NOT NULL,
        cause_message_id INTEGER REFERENCES messages(message_id),
        reason TEXT NOT NULL
    )""",
    """CREATE TABLE read_cursors (
        agent_id INTEGER PRIMARY KEY,
        last_read_message_id INTEGER NOT NULL
    )""",
    """CREATE TRIGGER messages_no_update BEFORE UPDATE ON messages
       BEGIN SELECT RAISE(ABORT, 'messages are append-only'); END""",
    """CREATE TRIGGER messages_no_delete BEFORE DELETE ON messages
       BEGIN SELECT RAISE(ABORT, 'messages are append-only'); END""",
    """CREATE TRIGGER changes_no_update BEFORE UPDATE ON relationship_changes
       BEGIN SELECT RAISE(ABORT, 'relationship changes are append-only'); END""",
    """CREATE TRIGGER changes_no_delete BEFORE DELETE ON relationship_changes
       BEGIN SELECT RAISE(ABORT, 'relationship changes are append-only'); END""",
)


class SocietyError(ValueError):
    """A native-society operation was refused."""


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SocietyError(f"{name} must be an integer >= {minimum}")
    return value


def _unit(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise SocietyError(f"{name} must be a number between 0 and 1")
    return float(value)


def _text(value: object, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SocietyError(f"{name} must be non-empty text of at most {limit} characters")
    return value


class SocietyStore:
    """SQLite-backed native conversation store. Use ``":memory:"`` for an ephemeral store."""

    def __init__(self, path: str | Path) -> None:
        self._memory = str(path) == ":memory:"
        self.path = Path(path)
        if not self._memory:
            try:
                require_safe_path(self.path)
            except UnsafePathError as exc:
                raise SocietyError("society store path is unsafe") from exc
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(":memory:" if self._memory else str(self.path), timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        have = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not have:
            with self._conn:
                for statement in _SCHEMA:
                    self._conn.execute(statement)
        elif not {"conversations", "messages", "memberships", "relationships"} <= have:
            raise SocietyError("society store schema is incomplete")

    def close(self) -> None:
        self._conn.close()

    # --- conversations ---------------------------------------------------------------
    def direct(self, a: int, b: int, *, round: int, topic: str = "direct") -> int:
        """Return the one direct conversation between two agents, creating it if needed."""
        a, b = _int(a, "agent"), _int(b, "agent")
        if a == b:
            raise SocietyError("a direct conversation needs two different agents")
        key = f"{min(a, b)}:{max(a, b)}"
        row = self._conn.execute("SELECT conversation_id FROM conversations WHERE pair_key=?", (key,)).fetchone()
        if row:
            return int(row[0])
        with self._conn:
            cid = self._conn.execute(
                "INSERT INTO conversations(kind, topic, created_round, pair_key) VALUES('direct',?,?,?)",
                (_text(topic, "topic", 200), _int(round, "round"), key),
            ).lastrowid
            for agent in sorted((a, b)):
                self._conn.execute(
                    "INSERT INTO memberships VALUES(?,?, 'member', ?)", (cid, agent, round))
        return int(cid)

    def create(self, kind: str, owner: int, *, round: int, topic: str) -> int:
        """Create a group, open discussion or broadcast channel owned by ``owner``."""
        if kind not in CONVERSATION_KINDS or kind == "direct":
            raise SocietyError("kind must be group, open or broadcast (use direct() for direct)")
        owner = _int(owner, "owner")
        with self._conn:
            cid = self._conn.execute(
                "INSERT INTO conversations(kind, topic, created_round) VALUES(?,?,?)",
                (kind, _text(topic, "topic", 200), _int(round, "round")),
            ).lastrowid
            self._conn.execute("INSERT INTO memberships VALUES(?,?, 'owner', ?)", (cid, owner, round))
        return int(cid)

    def join(self, conversation_id: int, agent: int, *, round: int, role: str = "member") -> None:
        kind = self._kind(conversation_id)
        if kind == "direct":
            raise SocietyError("direct conversations have exactly two fixed members")
        if role not in _ROLES:
            raise SocietyError("role must be member, moderator or owner")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO memberships VALUES(?,?,?,?)",
                    (conversation_id, _int(agent, "agent"), role, _int(round, "round")))
        except sqlite3.IntegrityError as exc:
            raise SocietyError("agent is already a member") from exc

    def members(self, conversation_id: int) -> list[tuple[int, str]]:
        self._kind(conversation_id)
        return [(int(r[0]), r[1]) for r in self._conn.execute(
            "SELECT agent_id, role FROM memberships WHERE conversation_id=? ORDER BY agent_id",
            (conversation_id,))]

    def _kind(self, conversation_id: int) -> str:
        row = self._conn.execute(
            "SELECT kind FROM conversations WHERE conversation_id=?", (conversation_id,)).fetchone()
        if row is None:
            raise SocietyError("unknown conversation")
        return row[0]

    # --- messages --------------------------------------------------------------------
    def post(self, conversation_id: int, sender: int, *, round: int, text: str, reason: str) -> int:
        """Append a message. Every message records why it was sent."""
        kind = self._kind(conversation_id)
        sender = _int(sender, "sender")
        round = _int(round, "round")
        role = self._conn.execute(
            "SELECT role FROM memberships WHERE conversation_id=? AND agent_id=?",
            (conversation_id, sender)).fetchone()
        if kind == "open":
            if role is None:  # open discussions admit any agent on first post
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO memberships VALUES(?,?, 'member', ?)",
                        (conversation_id, sender, _int(round, "round")))
        elif role is None:
            raise SocietyError("sender is not a member of this conversation")
        elif kind == "broadcast" and role[0] == "member":
            raise SocietyError("only an owner or moderator may post to a broadcast channel")
        last = self._conn.execute(
            "SELECT MAX(round) FROM messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if last is not None and round < last:
            raise SocietyError("messages must not go back in time within a conversation")
        with self._conn:
            mid = self._conn.execute(
                "INSERT INTO messages(conversation_id, sender_id, round, text, reason) VALUES(?,?,?,?,?)",
                (conversation_id, sender, _int(round, "round"),
                 _text(text, "text", _MAX_TEXT), _text(reason, "reason", _MAX_REASON)),
            ).lastrowid
        return int(mid)

    def thread(self, conversation_id: int) -> list[dict]:
        self._kind(conversation_id)
        return [dict(r) for r in self._conn.execute(
            "SELECT message_id, sender_id, round, text, reason FROM messages "
            "WHERE conversation_id=? ORDER BY message_id", (conversation_id,))]

    def inbox(self, agent: int, *, unread_only: bool = True) -> list[dict]:
        """Messages in conversations the agent belongs to, sent by others, oldest first."""
        agent = _int(agent, "agent")
        cursor = self._conn.execute(
            "SELECT last_read_message_id FROM read_cursors WHERE agent_id=?", (agent,)).fetchone()
        floor = int(cursor[0]) if (cursor and unread_only) else 0
        return [dict(r) for r in self._conn.execute(
            "SELECT m.message_id, m.conversation_id, c.kind, m.sender_id, m.round, m.text "
            "FROM messages m JOIN conversations c USING(conversation_id) "
            "JOIN memberships ms ON ms.conversation_id=m.conversation_id AND ms.agent_id=? "
            "WHERE m.sender_id<>? AND m.message_id>? ORDER BY m.message_id", (agent, agent, floor))]

    def mark_read(self, agent: int, up_to_message_id: int) -> None:
        agent = _int(agent, "agent")
        up_to = _int(up_to_message_id, "message id")
        top = self._conn.execute("SELECT COALESCE(MAX(message_id),0) FROM messages").fetchone()[0]
        if up_to > top:
            raise SocietyError("cannot mark a message that does not exist as read")
        with self._conn:
            self._conn.execute(
                "INSERT INTO read_cursors VALUES(?,?) ON CONFLICT(agent_id) DO UPDATE SET "
                "last_read_message_id=MAX(last_read_message_id, excluded.last_read_message_id)",
                (agent, up_to))

    # --- relationships ---------------------------------------------------------------
    def relationship(self, source: int, target: int) -> dict | None:
        row = self._conn.execute(
            "SELECT trust, familiarity, last_contact_round FROM relationships "
            "WHERE source_id=? AND target_id=?", (source, target)).fetchone()
        return dict(row) if row else None

    def adjust_relationship(
        self, source: int, target: int, *, round: int, trust_delta: float = 0.0,
        familiarity_delta: float = 0.0, cause_message_id: int | None, reason: str,
        initial_trust: float = 0.5, initial_familiarity: float = 0.0,
    ) -> dict:
        """Move a directed relationship, clamped to [0, 1], and log the change and its cause."""
        source, target = _int(source, "source"), _int(target, "target")
        if source == target:
            raise SocietyError("an agent has no relationship with itself")
        round = _int(round, "round")
        for name, value in (("trust_delta", trust_delta), ("familiarity_delta", familiarity_delta)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1.0 <= value <= 1.0:
                raise SocietyError(f"{name} must be a number between -1 and 1")
        if cause_message_id is not None and not self._conn.execute(
                "SELECT 1 FROM messages WHERE message_id=?", (cause_message_id,)).fetchone():
            raise SocietyError("cause message does not exist")
        current = self.relationship(source, target) or {
            "trust": _unit(initial_trust, "initial_trust"),
            "familiarity": _unit(initial_familiarity, "initial_familiarity"),
        }
        trust = min(1.0, max(0.0, current["trust"] + trust_delta))
        familiarity = min(1.0, max(0.0, current["familiarity"] + familiarity_delta))
        with self._conn:
            self._conn.execute(
                "INSERT INTO relationships VALUES(?,?,?,?,?) ON CONFLICT(source_id, target_id) DO UPDATE SET "
                "trust=excluded.trust, familiarity=excluded.familiarity, "
                "last_contact_round=MAX(last_contact_round, excluded.last_contact_round)",
                (source, target, trust, familiarity, round))
            self._conn.execute(
                "INSERT INTO relationship_changes(source_id, target_id, round, trust_delta, "
                "familiarity_delta, cause_message_id, reason) VALUES(?,?,?,?,?,?,?)",
                (source, target, round, trust - current["trust"], familiarity - current["familiarity"],
                 cause_message_id, _text(reason, "reason", _MAX_REASON)))
        return self.relationship(source, target)

    def relationship_history(self, source: int, target: int) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT change_id, round, trust_delta, familiarity_delta, cause_message_id, reason "
            "FROM relationship_changes WHERE source_id=? AND target_id=? ORDER BY change_id",
            (source, target))]

    # --- integrity -------------------------------------------------------------------
    def digest(self) -> str:
        """Deterministic SHA-256 over every table, independent of SQLite file bytes."""
        h = hashlib.sha256(b"agora.society.v1\0")
        for table, order in (
            ("conversations", "conversation_id"), ("memberships", "conversation_id, agent_id"),
            ("messages", "message_id"), ("relationships", "source_id, target_id"),
            ("relationship_changes", "change_id"), ("read_cursors", "agent_id"),
        ):
            h.update(table.encode() + b"\0")
            for row in self._conn.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                raw = json.dumps(list(row), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                h.update(len(raw).to_bytes(8, "big"))
                h.update(raw)
        return h.hexdigest()

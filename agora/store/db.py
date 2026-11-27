"""SQLite store for one project. Everything a run produces lives here, so a project
folder can be zipped, moved to another machine and resumed or analysed there.

Each round is written in a single transaction: if the machine sleeps or crashes
mid-round, the half-finished round simply never happened and is replayed on resume.
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Mapping

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY, handle TEXT UNIQUE, kind TEXT, name TEXT, segment TEXT,
    persona TEXT, platforms TEXT, initial_stance REAL, stubbornness REAL,
    activity REAL, influence REAL, openness REAL, attrs TEXT);
CREATE TABLE IF NOT EXISTS agent_state (
    id INTEGER PRIMARY KEY, stance REAL, memory TEXT, converted TEXT,
    last_seen REAL, round INTEGER, prefs TEXT, choice TEXT);
CREATE TABLE IF NOT EXISTS follows (platform TEXT, src INTEGER, dst INTEGER, round INTEGER,
    PRIMARY KEY (platform, src, dst));
CREATE TABLE IF NOT EXISTS memberships (agent INTEGER, platform TEXT, space TEXT,
    PRIMARY KEY (agent, platform, space));
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY, round INTEGER, t REAL, platform TEXT, space TEXT,
    author INTEGER, parent INTEGER, root INTEGER, kind TEXT, text TEXT, stance REAL, option TEXT);
CREATE INDEX IF NOT EXISTS posts_round ON posts(round);
CREATE TABLE IF NOT EXISTS engagements (round INTEGER, agent INTEGER, post INTEGER,
    type TEXT, PRIMARY KEY (agent, post, type));
CREATE TABLE IF NOT EXISTS conversions (round INTEGER, agent INTEGER, name TEXT,
    PRIMARY KEY (agent, name));
CREATE TABLE IF NOT EXISTS opinions (round INTEGER, agent INTEGER, stance REAL,
    PRIMARY KEY (round, agent));
CREATE TABLE IF NOT EXISTS thoughts (round INTEGER, agent INTEGER, text TEXT,
    PRIMARY KEY (round, agent));
CREATE TABLE IF NOT EXISTS polls (round INTEGER, name TEXT, agent INTEGER, vote INTEGER,
    reason TEXT, PRIMARY KEY (name, agent));
CREATE TABLE IF NOT EXISTS poll_results (name TEXT PRIMARY KEY, round INTEGER,
    yes INTEGER, no INTEGER, passed INTEGER);
CREATE TABLE IF NOT EXISTS rounds (round INTEGER PRIMARY KEY, sim_time TEXT,
    active INTEGER, llm_calls INTEGER, cache_hits INTEGER, seconds REAL, finished_at TEXT);
CREATE TABLE IF NOT EXISTS event_log (round INTEGER, kind TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS choices (round INTEGER, agent INTEGER PRIMARY KEY, option TEXT);
CREATE TABLE IF NOT EXISTS intentions (round INTEGER, segment TEXT, option TEXT, n INTEGER,
    PRIMARY KEY (round, segment, option));
CREATE TABLE IF NOT EXISTS mutes (src INTEGER, dst INTEGER, round INTEGER, PRIMARY KEY (src, dst));
CREATE TABLE IF NOT EXISTS injected (id INTEGER PRIMARY KEY AUTOINCREMENT, round INTEGER, event TEXT,
    added_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, thread TEXT, role TEXT,
    text TEXT, at TEXT DEFAULT (datetime('now')));
"""


SCHEMA_VERSION = 2


class Store:
    def __init__(self, path: str | Path, check_same_thread: bool = True):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path), check_same_thread=check_same_thread)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        cols = [r[1] for r in self.db.execute("PRAGMA table_info(follows)")]
        pcols = [r[1] for r in self.db.execute("PRAGMA table_info(posts)")]
        if (cols and "platform" not in cols) or (pcols and "option" not in pcols):
            raise RuntimeError(f"{self.path} was made by an older Agora version. "
                               "Delete agora.db to start the run again.")
        self.db.executescript(SCHEMA)
        self.db.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS protect_input_provenance_update
            BEFORE UPDATE OF value ON meta
            WHEN OLD.key = 'input_provenance'
            BEGIN SELECT RAISE(ABORT, 'input provenance is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS protect_input_provenance_delete
            BEFORE DELETE ON meta
            WHEN OLD.key = 'input_provenance'
            BEGIN SELECT RAISE(ABORT, 'input provenance is append-only'); END;
            """
        )
        self.db.commit()

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key: str, value) -> None:
        if key == "input_provenance":
            raise ValueError("input_provenance is reserved; use set_input_provenance")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

    # ------------------------------------------------------ input provenance
    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    @classmethod
    def _manifest_hash(cls, manifest: Mapping[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(cls._canonical(dict(manifest)).encode("utf-8")).hexdigest()

    def set_input_provenance(self, manifest: Mapping[str, Any], *, scenario_hash: str | None = None) -> dict[str, Any]:
        """Append an immutable scenario-input provenance envelope to this run store."""
        if not isinstance(manifest, Mapping) or not manifest:
            raise ValueError("input provenance manifest must be a non-empty mapping")
        payload = dict(manifest)
        declared_hash = scenario_hash or payload.get("scenario_hash")
        if not isinstance(declared_hash, str) or not declared_hash.strip():
            raise ValueError("input provenance requires a scenario_hash")
        if payload.get("scenario_hash") not in (None, declared_hash):
            raise ValueError("manifest scenario_hash does not match the envelope")
        payload["scenario_hash"] = declared_hash
        envelope = {
            "provenance_version": 1,
            "scenario_hash": declared_hash,
            "input_manifest": payload,
            "manifest_hash": self._manifest_hash(payload),
        }
        existing = self.get_meta("input_provenance")
        if existing is not None:
            if existing != envelope:
                raise RuntimeError("input provenance is append-once and cannot be replaced")
            return existing
        self.db.execute("INSERT INTO meta(key,value) VALUES (?,?)", ("input_provenance", self._canonical(envelope)))
        self.db.commit()
        return envelope

    def get_input_provenance(self) -> dict[str, Any]:
        """Return verified provenance, or mark pre-contract runs as legacy."""
        envelope = self.get_meta("input_provenance")
        if envelope is None:
            return {"provenance_status": "legacy_missing"}
        if not isinstance(envelope, Mapping):
            raise RuntimeError("input provenance envelope is malformed")
        manifest = envelope.get("input_manifest")
        if not isinstance(manifest, Mapping):
            raise RuntimeError("input provenance manifest is malformed")
        if envelope.get("manifest_hash") != self._manifest_hash(manifest):
            raise RuntimeError("input provenance manifest hash mismatch")
        if envelope.get("scenario_hash") != manifest.get("scenario_hash"):
            raise RuntimeError("input provenance scenario hash mismatch")
        return {**dict(envelope), "provenance_status": "verified"}

    def assert_resume_input(self, scenario_hash: str) -> None:
        """Fail closed unless the stored run has the exact same scenario hash."""
        provenance = self.get_input_provenance()
        if provenance.get("provenance_status") == "legacy_missing":
            raise RuntimeError("legacy run has no input provenance and cannot resume this path")
        if provenance.get("scenario_hash") != scenario_hash:
            raise RuntimeError("scenario hash changed; resume requires a new run")

    def last_round(self) -> int:
        """Last fully completed round, or -1 if the run has not started."""
        row = self.db.execute("SELECT MAX(round) FROM rounds").fetchone()
        return -1 if row[0] is None else int(row[0])

    def is_initialised(self) -> bool:
        return self.db.execute("SELECT COUNT(*) FROM agents").fetchone()[0] > 0

    # ------------------------------------------------------------------ writes
    def write_population(self, agents, follows, memberships) -> None:
        with self.db:
            self.db.executemany(
                "INSERT INTO agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(a.id, a.handle, a.kind, a.name, a.segment, a.persona, json.dumps(a.platforms),
                  a.initial_stance, a.stubbornness, a.activity, a.influence, a.openness,
                  json.dumps(a.attrs)) for a in agents])
            self.db.executemany(
                "INSERT INTO agent_state VALUES (?,?,?,?,?,?,?,?)",
                [(a.id, a.stance, json.dumps(a.memory), json.dumps(sorted(a.converted)),
                  a.last_seen, -1, json.dumps(a.prefs), a.choice) for a in agents])
            self.db.executemany("INSERT INTO follows VALUES (?,?,?,?)",
                                [(p, s, d, -1) for p, s, d in follows])
            self.db.executemany("INSERT INTO memberships VALUES (?,?,?)", memberships)
            self.db.executemany("INSERT INTO opinions VALUES (?,?,?)",
                                [(-1, a.id, a.stance) for a in agents])

    def commit_round(self, r: int, *, sim_time: str, agents, posts, engagements, follows,
                     conversions, thoughts, polls, poll_results, events, stats,
                     unfollows=(), mutes=(), choices=(), intentions=()) -> None:
        """Write everything a round produced atomically."""
        with self.db:
            self.db.executemany(
                "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(p.id, p.round, p.t, p.platform, p.space, p.author, p.parent, p.root,
                  p.kind, p.text, p.stance, p.option) for p in posts])
            self.db.executemany("INSERT OR IGNORE INTO engagements VALUES (?,?,?,?)",
                                [(r, a, p, t) for a, p, t in engagements])
            self.db.executemany("INSERT OR IGNORE INTO follows VALUES (?,?,?,?)",
                                [(p, s, d, r) for p, s, d in follows])
            self.db.executemany("DELETE FROM follows WHERE platform=? AND src=? AND dst=?", list(unfollows))
            self.db.executemany("INSERT OR IGNORE INTO mutes VALUES (?,?,?)", [(s, d, r) for s, d in mutes])
            self.db.executemany("INSERT OR IGNORE INTO choices VALUES (?,?,?)", [(r, a, o) for a, o in choices])
            self.db.executemany("INSERT OR REPLACE INTO intentions VALUES (?,?,?,?)",
                                [(r, g, o, n) for g, o, n in intentions])
            self.db.executemany("INSERT OR IGNORE INTO conversions VALUES (?,?,?)",
                                [(r, a, n) for a, n in conversions])
            self.db.executemany("INSERT OR REPLACE INTO thoughts VALUES (?,?,?)",
                                [(r, a, t) for a, t in thoughts])
            self.db.executemany("INSERT OR REPLACE INTO polls VALUES (?,?,?,?,?)",
                                [(r, n, a, v, why) for n, a, v, why in polls])
            self.db.executemany("INSERT OR REPLACE INTO poll_results VALUES (?,?,?,?,?)",
                                [(n, r, y, no, int(ok)) for n, y, no, ok in poll_results])
            self.db.executemany("INSERT INTO event_log VALUES (?,?,?)",
                                [(r, k, json.dumps(d)) for k, d in events])
            self.db.executemany(
                "INSERT OR REPLACE INTO agent_state VALUES (?,?,?,?,?,?,?,?)",
                [(a.id, a.stance, json.dumps(a.memory), json.dumps(sorted(a.converted)),
                  a.last_seen, r, json.dumps(a.prefs), a.choice)
                 for a in agents])
            self.db.executemany("INSERT OR REPLACE INTO opinions VALUES (?,?,?)",
                                [(r, a.id, round(a.stance, 4)) for a in agents])
            self.db.execute("INSERT OR REPLACE INTO rounds VALUES (?,?,?,?,?,?,datetime('now'))",
                            (r, sim_time, stats["active"], stats["llm_calls"],
                             stats["cache_hits"], stats["seconds"]))

    # ------------------------------------------------------------------ reads
    def rows(self, sql: str, args=()) -> list[tuple]:
        return self.db.execute(sql, args).fetchall()

    def close(self) -> None:
        self.db.close()

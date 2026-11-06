"""SQLite store for one project. Everything a run produces lives here, so a project
folder can be zipped, moved to another machine and resumed or analysed there.

Each round is written in a single transaction: if the machine sleeps or crashes
mid-round, the half-finished round simply never happened and is replayed on resume.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY, handle TEXT UNIQUE, kind TEXT, name TEXT, segment TEXT,
    persona TEXT, platforms TEXT, initial_stance REAL, stubbornness REAL,
    activity REAL, influence REAL, openness REAL, attrs TEXT);
CREATE TABLE IF NOT EXISTS agent_state (
    id INTEGER PRIMARY KEY, stance REAL, memory TEXT, converted TEXT,
    last_seen REAL, round INTEGER);
CREATE TABLE IF NOT EXISTS follows (src INTEGER, dst INTEGER, round INTEGER,
    PRIMARY KEY (src, dst));
CREATE TABLE IF NOT EXISTS memberships (agent INTEGER, platform TEXT, space TEXT,
    PRIMARY KEY (agent, platform, space));
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY, round INTEGER, t REAL, platform TEXT, space TEXT,
    author INTEGER, parent INTEGER, root INTEGER, kind TEXT, text TEXT, stance REAL);
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
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ------------------------------------------------------------------ meta
    def get_meta(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

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
                "INSERT INTO agent_state VALUES (?,?,?,?,?,?)",
                [(a.id, a.stance, json.dumps(a.memory), json.dumps(sorted(a.converted)),
                  a.last_seen, -1) for a in agents])
            self.db.executemany("INSERT INTO follows VALUES (?,?,?)",
                                [(s, d, -1) for s, d in follows])
            self.db.executemany("INSERT INTO memberships VALUES (?,?,?)", memberships)
            self.db.executemany("INSERT INTO opinions VALUES (?,?,?)",
                                [(-1, a.id, a.stance) for a in agents])

    def commit_round(self, r: int, *, sim_time: str, agents, posts, engagements, follows,
                     conversions, thoughts, polls, poll_results, events, stats) -> None:
        """Write everything a round produced atomically."""
        with self.db:
            self.db.executemany(
                "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(p.id, p.round, p.t, p.platform, p.space, p.author, p.parent, p.root,
                  p.kind, p.text, p.stance) for p in posts])
            self.db.executemany("INSERT OR IGNORE INTO engagements VALUES (?,?,?,?)",
                                [(r, a, p, t) for a, p, t in engagements])
            self.db.executemany("INSERT OR IGNORE INTO follows VALUES (?,?,?)",
                                [(s, d, r) for s, d in follows])
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
                "INSERT OR REPLACE INTO agent_state VALUES (?,?,?,?,?,?)",
                [(a.id, a.stance, json.dumps(a.memory), json.dumps(sorted(a.converted)),
                  a.last_seen, r) for a in agents])
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

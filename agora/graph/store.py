"""Knowledge-graph store (graph.db in the project folder), kept separate from the run
database so you can re-run simulations without rebuilding the graph."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, name TEXT, chars INTEGER, chunks INTEGER);
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, doc TEXT, idx INTEGER,
    text TEXT, status TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT, type TEXT,
    description TEXT, aliases TEXT, mentions INTEGER);
CREATE TABLE IF NOT EXISTS edges (id INTEGER PRIMARY KEY AUTOINCREMENT, src INTEGER, dst INTEGER,
    type TEXT, fact TEXT, chunk INTEGER);
CREATE TABLE IF NOT EXISTS node_chunks (node INTEGER, chunk INTEGER, PRIMARY KEY (node, chunk));
"""


class GraphStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

    def rows(self, sql, args=()):
        return self.db.execute(sql, args).fetchall()

    def close(self):
        self.db.close()

"""Response cache. Same prompt + settings = same answer, instantly.

Makes resumed runs exact (the round that was interrupted replays from cache) and lets
you re-run analysis without paying the model cost again. Stored inside the project
folder so it travels with the project.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path

from .base import LLMBackend


class CachedBackend(LLMBackend):
    def __init__(self, inner: LLMBackend, path: str | Path):
        self.inner = inner
        self.cfg = inner.cfg
        self.name = inner.name
        self.calls = 0
        self.hits = 0
        self.tokens_out = 0
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT)")
        self._db.commit()

    def _key(self, messages, max_tokens, temperature, json_mode, seed) -> str:
        blob = json.dumps([self.cfg.backend, self.cfg.model, messages, max_tokens,
                           round(temperature, 3), json_mode, seed], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def generate(self, messages, *, max_tokens=300, temperature=0.8, json_mode=False,
                 seed=None, meta=None) -> str:
        k = self._key(messages, max_tokens, temperature, json_mode, seed)
        with self._lock:
            row = self._db.execute("SELECT v FROM cache WHERE k=?", (k,)).fetchone()
        if row is not None:
            self.hits += 1
            return row[0]
        out = self.inner.generate(messages, max_tokens=max_tokens, temperature=temperature,
                                  json_mode=json_mode, seed=seed, meta=meta)
        self.calls += 1
        self.tokens_out += max(1, len(out) // 4)
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)", (k, out))
            self._db.commit()
        return out

    def status(self):
        return self.inner.status()

    def close(self):
        self._db.close()

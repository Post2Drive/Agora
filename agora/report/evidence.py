"""Search over what agents actually said, so the report agent can quote real posts."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..graph.retrieve import FactIndex
from ..platforms import REGISTRY


class PostIndex:
    def __init__(self, project: str | Path):
        path = Path(project) / "agora.db"
        db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        self.rows = db.execute(
            "SELECT p.id, p.platform, p.space, p.round, p.text, p.stance, a.name, a.handle, a.segment, a.kind "
            "FROM posts p JOIN agents a ON a.id = p.author WHERE p.kind IN ('post','reply') AND p.text != '' "
            "ORDER BY p.id").fetchall()
        db.close()
        self.by_id = {r[0]: r for r in self.rows}
        self.lines = [self.render(r) for r in self.rows]
        self.index = FactIndex(self.lines)
        self._line_id = {line: r[0] for line, r in zip(self.lines, self.rows)}

    @staticmethod
    def render(r) -> str:
        pid, plat, space, rnd, text, st, name, handle, seg, kind = r
        where = REGISTRY[plat].label + (f" / {space}" if space else "")
        who = f"{name} ({seg.replace('_', ' ')})" if kind != "account" else f"{name} (official)"
        return f"[p{pid}] {who} on {where}: \"{text.strip()[:300]}\""

    def search(self, query: str, k: int = 6) -> list[str]:
        return self.index.search(query, k=k)

    def line(self, pid: int) -> str | None:
        r = self.by_id.get(pid)
        return self.render(r) if r else None

    def ids_in(self, lines: list[str]) -> set[int]:
        return {self._line_id[x] for x in lines if x in self._line_id}

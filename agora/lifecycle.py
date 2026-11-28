"""Where a study stands: draft, ready, running, paused, complete or archived.

Nothing here is a stored state machine that could drift from the facts. Five of the six states are read from
what is on disk (is there a scenario, has the run started, how many rounds are done) plus whether a job is
running right now. Only `archived` is written, as a flag in the project's agora.json, and it hides the study
without deleting anything. Un-archiving restores the state the facts give.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

STATES = ("draft", "ready", "running", "paused", "complete", "archived")
META_FILE = "agora.json"


class LifecycleError(ValueError):
    pass


def _meta(proj: Path) -> dict:
    try:
        d = json.loads((proj / META_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def is_archived(proj: Path) -> bool:
    return _meta(proj).get("archived") is True


def _rounds_total(proj: Path) -> int | None:
    try:
        n = yaml.safe_load((proj / "scenario.yaml").read_text(encoding="utf-8")).get("rounds")
        return n if isinstance(n, int) and not isinstance(n, bool) else None
    except Exception:  # noqa: BLE001 - an unreadable scenario means the study is not ready
        return None


def _rounds_done(proj: Path) -> int:
    db = proj / "agora.db"
    if not db.exists():
        return 0
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return int(con.execute("SELECT COUNT(*) FROM rounds").fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def study_state(proj: Path, *, job_running: bool = False) -> str:
    """The study's state. A running job wins over everything except archived."""
    proj = Path(proj)
    if is_archived(proj):
        return "archived"
    if job_running:
        return "running"
    total = _rounds_total(proj)
    if total is None:
        return "draft"
    done = _rounds_done(proj)
    if done <= 0:
        return "ready"
    return "complete" if done >= total else "paused"


def archive(proj: Path, *, job_running: bool = False) -> None:
    proj = Path(proj)
    if job_running:
        raise LifecycleError("stop the running job before archiving this study")
    _write(proj, True)


def unarchive(proj: Path) -> None:
    _write(Path(proj), False)


def _write(proj: Path, archived: bool) -> None:
    if not proj.is_dir():
        raise LifecycleError("no such study")
    meta = _meta(proj)
    if archived:
        meta["archived"] = True
    else:
        meta.pop("archived", None)
    (proj / META_FILE).write_text(json.dumps(meta), encoding="utf-8")


__all__ = ["LifecycleError", "STATES", "archive", "is_archived", "study_state", "unarchive"]

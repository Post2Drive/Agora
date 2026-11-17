"""Information cutoff: a study may only use real-world news published on or before the cutoff day.

The cutoff is stored in cutoff.json next to the study. Once it is set:
  - an event with no publish date is refused (its date cannot be checked);
  - an event published after the cutoff day is refused.
The cutoff day itself is allowed.

This guards the real-world feed (events queue, RSS candidates). A scheduled event written
straight into scenario.yaml is not checked here; keep those to dates before the cutoff.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

FILE = "cutoff.json"


def parse_day(text) -> date:
    s = str(text or "").strip()
    if not s:
        raise ValueError("Give a date like 2024-10-26.")
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        raise ValueError(f"Cannot read the date '{s}'. Use YYYY-MM-DD.") from None


def set_cutoff(project: str | Path, day) -> dict:
    d = parse_day(day)
    Path(project).joinpath(FILE).write_text(json.dumps({"cutoff": d.isoformat()}), encoding="utf-8")
    return {"cutoff": d.isoformat()}


def get_cutoff(project: str | Path) -> date | None:
    f = Path(project) / FILE
    if not f.exists():
        return None
    return parse_day(json.loads(f.read_text(encoding="utf-8")).get("cutoff"))


def check(project: str | Path, published) -> str | None:
    """None if an item dated `published` may be used; otherwise the reason it may not."""
    cut = get_cutoff(project)
    if cut is None:
        return None
    if not str(published or "").strip():
        return f"no publish date; with a cutoff of {cut} every item must say when it was published"
    try:
        when = parse_day(published)
    except ValueError as e:
        return str(e)
    if when > cut:
        return f"published {when} is after the cutoff {cut}"
    return None

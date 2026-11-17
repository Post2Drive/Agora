"""Real-world events fed into a running study.

Events go in a file next to the study (events.jsonl), one JSON object per line:
  {"id": "...", "text": "...", "type": "news", "source": "...", "url": "...",
   "round": 12 (optional, 0-based), "published": "2026-11-13T08:00"}

`sync` moves new lines into the simulation's injection table, using the same
path as `agora inject`. The engine is not changed, so a study with no queued events
runs exactly as before. Events already synced are remembered in events.synced.json;
an event that is due for a round that has already happened is skipped and reported.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

QUEUE = "events.jsonl"
SYNCED = "events.synced.json"


def _id(text: str, source: str) -> str:
    return hashlib.sha256(f"{source}\n{text.strip()}".encode("utf-8")).hexdigest()[:16]


def add(project: str | Path, text: str, *, source: str = "manual", url: str = "", kind: str = "news",
        at_round: int | None = None, published: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Write what happened.")
    from .cutoff import check
    reason = check(project, published)
    if reason:
        raise ValueError(f"Not used: {reason}.")
    ev = {"id": _id(text, source), "text": text[:1500], "type": kind, "source": source,
          "url": url, "published": published}
    if at_round is not None:
        ev["round"] = int(at_round)
    f = Path(project) / QUEUE
    known = {e["id"] for e in read(project)}
    if ev["id"] in known:
        return {"ok": True, "duplicate": True, "id": ev["id"]}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return {"ok": True, "duplicate": False, "id": ev["id"]}


def read(project: str | Path) -> list[dict]:
    f = Path(project) / QUEUE
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _synced(project: Path) -> dict:
    f = project / SYNCED
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sync(project: str | Path) -> dict:
    """Queue every new event for the next round (or its chosen round). Safe to run again."""
    from .report.interact import inject
    project = Path(project)
    done = _synced(project)
    added, skipped = [], []
    from .cutoff import check
    for ev in read(project):
        if ev["id"] in done:
            continue
        reason = check(project, ev.get("published", ""))
        if reason:
            skipped.append({"id": ev["id"], "reason": reason})
            continue
        try:
            r = inject(project, {"type": ev.get("type", "news"), "text": ev["text"]}, ev.get("round"))
        except FileNotFoundError:
            raise FileNotFoundError("Run the study at least once before adding events.")
        except ValueError as e:
            skipped.append({"id": ev["id"], "reason": str(e)})
            continue
        done[ev["id"]] = {"round": r["round"], "source": ev.get("source", ""),
                          "published": ev.get("published", "")}
        added.append({"id": ev["id"], "round": r["round"] + 1, "text": ev["text"][:80]})
    (project / SYNCED).write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"added": added, "skipped": skipped}

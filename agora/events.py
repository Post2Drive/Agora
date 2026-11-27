"""Real-world events fed into a running study.

Events go in a file next to the study (events.jsonl), one JSON object per line:
  {"id": "...", "text": "...", "type": "news", "source": "...", "url": "...",
   "round": 12 (optional, 0-based), "published": "2026-11-13T08:00"}

`sync` moves new lines into the simulation's injection table, using the same
path as `agora inject`. The engine is not changed, so a study with no queued events
runs exactly as before. Events already synced are remembered in events.synced.json;
an event that is due for a round that has already happened is skipped and reported.

The queue is written under a lock, and one `sync` runs at a time. The synced record is saved
after each event; a process killed between adding an event to the run and saving that record
can still add it again.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .jsonl_journal import append_line, reader_lock, writer_lock
from .pathsafe import require_safe_path

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
    with writer_lock(f):
        known = {e["id"] for e in _read_queue(f)}
        if ev["id"] in known:
            return {"ok": True, "duplicate": True, "id": ev["id"]}
        from .governance import begin_operation, finish_operation, record_source, audit_event
        source_id = "event-" + ev["id"]
        operation = begin_operation(project, "event_queue", source_ids=[source_id],
                                    details={"event_id": ev["id"]})
        try:
            record_source(project, source_id=source_id, content=ev["text"].encode("utf-8"),
                          data_role="scenario_input", source_url=url, publisher=source)
            append_line(f, json.dumps(ev, ensure_ascii=False))
            audit_event(project, "event_queued", event_id=ev["id"], source=source,
                        published=published, data_role="scenario_input")
        except Exception as exc:
            finish_operation(project, operation["operation_id"], "failed",
                             error=f"{type(exc).__name__}: {exc}")
            raise
        finish_operation(project, operation["operation_id"], "committed",
                         details={"event_id": ev["id"]})
        return {"ok": True, "duplicate": False, "id": ev["id"]}


def read(project: str | Path) -> list[dict]:
    f = Path(project) / QUEUE
    with reader_lock(f):
        return _read_queue(f)


def _read_queue(f: Path) -> list[dict]:
    """Parse the queue. The caller holds a reader or writer lock."""
    if not f.exists():
        return []
    out = []
    # split on "\n" only: splitlines() also breaks on U+2028 and U+0085, which JSON leaves unescaped
    for line in f.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _synced(project: Path) -> dict:
    f = project / SYNCED
    if not f.exists():
        return {}
    try:
        done = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(done, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        # treating it as empty would add every queued event to the run a second time
        raise ValueError(f"{SYNCED} is unreadable, so nothing was synced. Restore or repair it first.") from exc
    return done


def _save_synced(project: Path, done: dict) -> None:
    """Replace the synced record in one step, so a crash cannot leave it half written."""
    temporary = require_safe_path(project / (SYNCED + ".tmp"))
    with open(temporary, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(done, indent=1, ensure_ascii=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temporary, project / SYNCED)


def sync(project: str | Path) -> dict:
    """Queue every new event for the next round (or its chosen round). Safe to run again."""
    project = Path(project)
    with writer_lock(project / SYNCED):
        return _sync_locked(project)


def _sync_locked(project: Path) -> dict:
    from .report.interact import inject
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
        _save_synced(project, done)
        added.append({"id": ev["id"], "round": r["round"] + 1, "text": ev["text"][:80]})
    _save_synced(project, done)
    return {"added": added, "skipped": skipped}

"""Pull real-world news from RSS or Atom feeds as candidate events for a study.

Nothing enters a study straight from a feed. Matching items are saved to
events_candidates.jsonl, and a person approves each one (`approve`), which adds it to the
events queue. Items dated after the information cutoff are never offered.
"""
from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from . import cutoff as cutoff_mod
from . import events as events_mod

CANDIDATES = "events_candidates.jsonl"
ATOM = "{http://www.w3.org/2005/Atom}"


def _clean(s) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def _day(s) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:                                    # RSS: "Wed, 13 Nov 2026 08:00:00 GMT"
        return parsedate_to_datetime(s).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:                                    # Atom: "2026-11-13T08:00:00Z"
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _item(title, link, when, summary) -> dict:
    day = _day(when)
    return {"title": _clean(title), "url": (link or "").strip(),
            "published": day.isoformat() if day else "", "summary": _clean(summary)[:600]}


def _all_text(parent, tag: str) -> str:
    """All text inside a child element, including text that sits inside inline markup like <b>."""
    el = parent.find(tag)
    return "".join(el.itertext()) if el is not None else ""


def parse_feed(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    items = [_item(_all_text(it, "title"), _all_text(it, "link"), _all_text(it, "pubDate"),
                   _all_text(it, "description")) for it in root.iter("item")]
    for en in root.iter(ATOM + "entry"):
        link = en.find(ATOM + "link")
        items.append(_item(_all_text(en, ATOM + "title"), link.get("href") if link is not None else "",
                           _all_text(en, ATOM + "published") or _all_text(en, ATOM + "updated"),
                           _all_text(en, ATOM + "summary") or _all_text(en, ATOM + "content")))
    return items


def select(items: list[dict], keywords: list[str], *, since: date | None = None,
           until: date | None = None, cutoff: date | None = None) -> list[dict]:
    """Items that mention a keyword, have a date inside the window, and are not after the cutoff."""
    kws = [k.strip().lower() for k in keywords if k.strip()]
    out = []
    for it in items:
        if not it["published"]:
            continue                        # cannot place it in time, so do not use it
        hay = f"{it['title']} {it['summary']}".lower()
        if kws and not any(k in hay for k in kws):
            continue
        day = date.fromisoformat(it["published"])
        if (since and day < since) or (until and day > until) or (cutoff and day > cutoff):
            continue
        out.append(it)
    return out


def fetch(url: str, timeout: float = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "agora-news/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def read_candidates(project: str | Path) -> list[dict]:
    f = Path(project) / CANDIDATES
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def pull(project: str | Path, feeds: list[str], keywords: list[str], *, since: date | None = None,
         until: date | None = None, get=fetch) -> dict:
    project = Path(project)
    if not [k for k in keywords if k.strip()]:
        raise ValueError("Give at least one keyword to watch for.")
    cut = cutoff_mod.get_cutoff(project)
    known = {c["id"] for c in read_candidates(project)} | {e["id"] for e in events_mod.read(project)}
    added, errors = [], []
    for url in feeds:
        if urlparse(url).scheme not in ("http", "https"):
            errors.append({"feed": url, "reason": "only http and https feeds"})
            continue
        try:
            items = parse_feed(get(url))
        except Exception as e:              # network or bad XML: report it and carry on
            errors.append({"feed": url, "reason": str(e)[:200]})
            continue
        source = urlparse(url).netloc
        for it in select(items, keywords, since=since, until=until, cutoff=cut):
            text = it["title"] + (". " + it["summary"] if it["summary"] else "")
            cid = events_mod._id(text, source)
            if cid in known:
                continue
            known.add(cid)
            cand = {"id": cid, "text": text[:1500], "source": source, "url": it["url"],
                    "published": it["published"], "feed": url}
            with (project / CANDIDATES).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(cand, ensure_ascii=False) + "\n")
            added.append({"id": cid, "published": it["published"], "text": text[:120]})
    return {"added": added, "errors": errors}


def approve(project: str | Path, cid: str) -> dict:
    cands = {c["id"]: c for c in read_candidates(project)}
    c = cands.get(cid)
    if c is None:
        raise ValueError("No candidate with that id.")
    return events_mod.add(project, c["text"], source=c["source"], url=c["url"], kind="news",
                          published=c["published"])

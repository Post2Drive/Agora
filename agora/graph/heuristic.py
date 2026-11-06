"""Model-free entity/relation extraction. Used for `--fast` builds, as the fallback when a
model returns nothing usable, and by the mock backend in tests. Rough but fast."""
from __future__ import annotations

import re
from collections import Counter

STOP = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "Its", "We", "Our", "You", "Your",
    "They", "Their", "He", "She", "If", "In", "On", "At", "For", "To", "Of", "And", "Or", "But",
    "No", "Not", "Each", "Every", "One", "Stage", "With", "By", "From", "As", "All", "Any",
    "Is", "Are", "Be", "Will", "Can", "May", "After", "Before", "Based", "Keep", "Submit",
    "Record", "Distribute", "Calculate", "Table", "Page", "Yes", "Information", "Product",
    "Usage", "Brand", "Campaign", "Registration", "Registered", "Sample", "Seven", "Once",
}
ORG_HINTS = ("ltd", "limited", "pvt", "inc", "llc", "association", "company", "corp",
             "council", "ministry", "department", "authority", "bank", "university", "board",
             "committee", "foundation", "agency", "group")
PLACE_HINTS = ("city", "road", "street", "nagar", "towers", "residency", "apartments",
               "district", "state", "colony", "village", "pradesh", "park")
PRODUCT_HINTS = ("probiotic", "app", "service", "pack", "sachet", "product", "plan", "model")

_NAME = re.compile(r"\b(?:[A-Z][a-zA-Z&'\-]+|[A-Z]{2,6})(?:\s+(?:of\s+|and\s+|&\s+)?"
                   r"(?:[A-Z][a-zA-Z&'\-]+|[A-Z]{2,6}))*")
_ACRONYM_DEF = re.compile(r"((?:[A-Z][a-z]+\s+){1,6}[A-Z][a-z]+)\s*\(([A-Z]{2,8})\)")
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def guess_type(name: str) -> str:
    low = name.lower()
    if any(h in low for h in ORG_HINTS):
        return "Organization"
    if any(h in low for h in PLACE_HINTS):
        return "Place"
    if any(h in low for h in PRODUCT_HINTS):
        return "Product"
    return "Concept"


def extract(text: str, min_count: int = 1) -> dict:
    aliases: dict[str, str] = {}
    for full, short in _ACRONYM_DEF.findall(text):
        aliases[short] = full.strip()
    counts: Counter[str] = Counter()
    sentences = [re.sub(r"^[\s|#*\-\d.)]+", "", s).strip() for s in _SENT.split(text)]
    sentences = [s for s in sentences if len(s) > 20]
    # Pass 1: names seen mid-sentence are trustworthy; sentence-initial capitals are often
    # just ordinary words ("Evaluate", "Allow") and need confirmation from pass 1.
    found: list[list[tuple[str, bool]]] = []
    mid: set[str] = set()
    for s in sentences:
        row = []
        for m in _NAME.finditer(s):
            words = m.group(0).strip().split()
            at_start = m.start() == 0
            while words and words[0] in STOP:
                words, at_start = words[1:], False
            n = " ".join(words)
            if len(n) < 3 or n in STOP:
                continue
            row.append((n, at_start))
            if not at_start:
                mid.add(n)
                mid.update(w for w in words if w.isupper())
        found.append(row)
    sent_names: list[list[str]] = []
    for row in found:
        names = []
        for n, at_start in row:
            if at_start and n not in mid and not n.isupper():
                rest = n.split()[1:]           # "Introduce NPP" -> "NPP"
                n = " ".join(rest)
                if not n or (len(rest) == 1 and n not in mid and not n.isupper()):
                    continue
            n = aliases.get(n, n)
            counts[n] += 1
            names.append(n)
        sent_names.append(list(dict.fromkeys(names)))
    keep = {n for n, c in counts.items() if c >= min_count}
    entities = []
    for n in sorted(keep, key=lambda x: -counts[x])[:40]:
        al = [k for k, v in aliases.items() if v == n]
        desc = next((s for s in sentences if n in s), "")[:200]
        entities.append({"name": n, "type": guess_type(n), "description": desc, "aliases": al})
    kept = {e["name"] for e in entities}
    relations, seen = [], set()
    for s, names in zip(sentences, sent_names):
        names = [n for n in names if n in kept]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                key = (names[i], names[j])
                if key in seen:
                    continue
                seen.add(key)
                relations.append({"source": names[i], "target": names[j],
                                  "type": "RELATED_TO", "fact": s[:240]})
    return {"entities": entities, "relations": relations[:60]}

"""Parse and validate a relationship seed file (phase 1 of docs/NATIVE_RELATIONSHIP_SEEDING_DESIGN.md).

The file declares, and nothing is inferred: which ontology link types count and how strongly, and which
ontology record stands for which agent. This module only checks and fingerprints the declaration. It does
not read the ontology store and does not touch any society store, so parsing a seed changes nothing.

    format: agora.society.seed/v1
    pack_fingerprint: <64 hex characters>
    import_id: <ontology import the records come from>
    link_types:
      - {link_type_id: knows, direction: both, trust: 0.6, familiarity: 0.3}
    records:
      - {record_key: C-1001, agent: 3}
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..ontology.loader import _UniqueKeyLoader

SEED_FORMAT = "agora.society.seed/v1"
DIRECTIONS = ("both", "source_to_target")
MAX_LINK_TYPES = 100
MAX_RECORDS = 100_000
_TOP = {"format", "pack_fingerprint", "import_id", "link_types", "records"}
_LINK = {"link_type_id", "direction", "trust", "familiarity"}
_RECORD = {"record_key", "agent"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_TEXT = 200
_MAX_AGENT_ID = 2**63 - 1                      # SQLite's largest integer


class SeedError(ValueError):
    """The seed declaration is missing, malformed or contradicts itself."""


@dataclass(frozen=True)
class SeedLinkType:
    link_type_id: str
    direction: str
    trust: float
    familiarity: float


@dataclass(frozen=True)
class RelationshipSeed:
    pack_fingerprint: str
    import_id: str
    link_types: tuple[SeedLinkType, ...]
    records: tuple[tuple[str, int], ...]      # (record_key, agent id), in file order
    seed_hash: str                            # SHA-256 of the canonical declaration

    def agent_of(self, record_key: str) -> int | None:
        return dict(self.records).get(record_key)

    def rule_for(self, link_type_id: str) -> SeedLinkType | None:
        return next((r for r in self.link_types if r.link_type_id == link_type_id), None)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > _MAX_TEXT \
            or any(unicodedata.category(c) in ("Cc", "Cs") for c in value):  # controls and lone surrogates
        raise SeedError(f"{name} must be non-empty text without surrounding spaces or control characters, "
                        f"at most {_MAX_TEXT} characters")
    return value


def _unit(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:  # NaN fails this too
        raise SeedError(f"{name} must be a number from 0 to 1")
    return float(value) + 0.0                  # -0.0 becomes 0.0, so equal weights hash alike


def _only(item: Any, allowed: set[str], where: str) -> Mapping:
    if not isinstance(item, Mapping):
        raise SeedError(f"{where} must be a mapping")
    extra = set(item) - allowed
    if extra:
        raise SeedError(f"{where} has unknown field(s): {', '.join(sorted(map(str, extra)))}")
    missing = allowed - set(item)
    if missing:
        raise SeedError(f"{where} is missing: {', '.join(sorted(missing))}")
    return item


def _list(value: Any, name: str, limit: int) -> list:
    if not isinstance(value, list) or not value:
        raise SeedError(f"{name} must be a non-empty list")
    if len(value) > limit:
        raise SeedError(f"{name} has more than {limit} entries")
    return value


def parse_seed(doc: Any, *, agents: set[int] | None = None) -> RelationshipSeed:
    """Validate a decoded seed document. ``agents``, when given, is the set of agent IDs that exist."""
    doc = _only(doc, _TOP, "seed")
    if doc["format"] != SEED_FORMAT:
        raise SeedError(f"format must be {SEED_FORMAT}")
    fingerprint = doc["pack_fingerprint"]
    if not isinstance(fingerprint, str) or not _HEX64.match(fingerprint):
        raise SeedError("pack_fingerprint must be 64 lowercase hex characters")
    import_id = _text(doc["import_id"], "import_id")

    rules: list[SeedLinkType] = []
    for i, item in enumerate(_list(doc["link_types"], "link_types", MAX_LINK_TYPES)):
        item = _only(item, _LINK, f"link_types[{i}]")
        direction = item["direction"]
        if direction not in DIRECTIONS:
            raise SeedError(f"link_types[{i}].direction must be one of {', '.join(DIRECTIONS)}")
        rule = SeedLinkType(_text(item["link_type_id"], f"link_types[{i}].link_type_id"), direction,
                            _unit(item["trust"], f"link_types[{i}].trust"),
                            _unit(item["familiarity"], f"link_types[{i}].familiarity"))
        if any(r.link_type_id == rule.link_type_id for r in rules):
            raise SeedError(f"link type {rule.link_type_id!r} is listed twice")
        rules.append(rule)

    records: list[tuple[str, int]] = []
    keys: set[str] = set()
    used: set[int] = set()
    for i, item in enumerate(_list(doc["records"], "records", MAX_RECORDS)):
        item = _only(item, _RECORD, f"records[{i}]")
        key = _text(item["record_key"], f"records[{i}].record_key")
        agent = item["agent"]
        if type(agent) is not int or not 0 <= agent <= _MAX_AGENT_ID:
            raise SeedError(f"records[{i}].agent must be a whole number from 0 to {_MAX_AGENT_ID}")
        if key in keys:
            raise SeedError(f"record {key!r} is mapped twice")
        if agent in used:
            raise SeedError(f"agent {agent} stands for more than one record")
        if agents is not None and agent not in agents:
            raise SeedError(f"records[{i}].agent {agent} is not an agent in this run")
        keys.add(key)
        used.add(agent)
        records.append((key, agent))

    canonical = {"format": SEED_FORMAT, "pack_fingerprint": fingerprint, "import_id": import_id,
                 "link_types": [[r.link_type_id, r.direction, r.trust, r.familiarity] for r in rules],
                 "records": [[k, a] for k, a in records]}
    digest = hashlib.sha256(json.dumps(canonical, separators=(",", ":"), ensure_ascii=False,
                                       sort_keys=True).encode("utf-8")).hexdigest()
    return RelationshipSeed(fingerprint, import_id, tuple(rules), tuple(records), digest)


def load_seed(path: str | Path, *, agents: set[int] | None = None) -> RelationshipSeed:
    """Read and validate a seed file. A repeated key is refused, not resolved by keeping the last value."""
    try:
        doc = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)  # a SafeLoader
    except (OSError, ValueError, RecursionError, yaml.YAMLError) as exc:  # ValueError covers bad text and dates
        raise SeedError(f"cannot read seed file: {exc}") from exc
    return parse_seed(doc, agents=agents)


__all__ = ["DIRECTIONS", "RelationshipSeed", "SEED_FORMAT", "SeedError", "SeedLinkType", "load_seed", "parse_seed"]

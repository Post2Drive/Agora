"""Turn a validated relationship seed plus the ontology's active links into a deterministic edge plan.

Phase 2 of docs/NATIVE_RELATIONSHIP_SEEDING_DESIGN.md. This reads the ontology store (through its own
authorisation and audit) and writes nothing: no link is changed and no society store is touched. Applying
the plan to a run is a later phase.

What is counted, in order for each declared link type:
* only links the store reports as active (a retracted or superseded link gives no edge);
* only links whose two ends are both in the seed's declared import;
* only links whose two ends are both mapped to an agent, and to two different agents.
Everything else is counted, never silently dropped. Where several links give the same directed pair, the
edge takes the largest declared trust and familiarity and lists every link that contributed.

Limit: the store returns at most 100 links for one link type in one call. A larger set stops with an error
rather than seeding part of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .seed import RelationshipSeed, SeedError

_STORE_CAP = 100


@dataclass(frozen=True)
class SeedEdge:
    source: int
    target: int
    trust: float
    familiarity: float
    link_ids: tuple[str, ...]          # every link that gave this directed pair, in sorted order


@dataclass(frozen=True)
class SeedCounts:
    links_read: int
    links_used: int
    other_import: int
    not_mapped: int
    same_agent: int
    not_active: int


@dataclass(frozen=True)
class SeedPlan:
    seed_hash: str
    pack_fingerprint: str
    edges: tuple[SeedEdge, ...]        # sorted by (source, target)
    counts: SeedCounts


def _version(pack: Any, link_type_id: str) -> str:
    versions = sorted({item.version for item in pack.link_types if item.link_type_id == link_type_id})
    if not versions:
        raise SeedError(f"link type {link_type_id!r} is not in the ontology pack")
    if len(versions) > 1:
        raise SeedError(f"link type {link_type_id!r} has more than one version in the pack: {', '.join(versions)}")
    return versions[0]


def plan_seed_edges(store: Any, seed: RelationshipSeed, *, policy: Any, audit: Any) -> SeedPlan:
    """Read the active links for every declared link type and build the edge plan."""
    pack = store.get_pack(seed.pack_fingerprint, policy=policy, audit=audit)
    agent_of = dict(seed.records)
    best: dict[tuple[int, int], list] = {}      # (source, target) -> [trust, familiarity, {link_id}]
    read = used = other_import = not_mapped = same_agent = not_active = 0

    for rule in seed.link_types:
        version = _version(pack, rule.link_type_id)
        links = store.get_links(seed.pack_fingerprint, rule.link_type_id, version, policy=policy, audit=audit)
        if len(links) >= _STORE_CAP:
            raise SeedError(f"link type {rule.link_type_id!r} has {_STORE_CAP} or more links; the seed reads at most "
                            f"{_STORE_CAP - 1} per link type")
        for link in links:
            read += 1
            if link["status"] != "active":
                not_active += 1
                continue
            a, b = link["source"], link["target"]
            if a["import_id"] != seed.import_id or b["import_id"] != seed.import_id:
                other_import += 1
                continue
            source, target = agent_of.get(a["record_key"]), agent_of.get(b["record_key"])
            if source is None or target is None:
                not_mapped += 1
                continue
            if source == target:
                same_agent += 1
                continue
            used += 1
            pairs = [(source, target)]
            if rule.direction == "both":
                pairs.append((target, source))
            for pair in pairs:
                entry = best.setdefault(pair, [0.0, 0.0, set()])
                entry[0] = max(entry[0], rule.trust)
                entry[1] = max(entry[1], rule.familiarity)
                entry[2].add(link["link_id"])

    edges = tuple(SeedEdge(s, t, e[0], e[1], tuple(sorted(e[2]))) for (s, t), e in sorted(best.items()))
    return SeedPlan(seed.seed_hash, seed.pack_fingerprint, edges,
                    SeedCounts(read, used, other_import, not_mapped, same_agent, not_active))


__all__ = ["SeedCounts", "SeedEdge", "SeedPlan", "plan_seed_edges"]

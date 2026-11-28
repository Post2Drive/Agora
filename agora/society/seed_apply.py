"""Write a seed plan into a run's relationships (phase 3 of docs/NATIVE_RELATIONSHIP_SEEDING_DESIGN.md).

Each planned edge becomes one `adjust_relationship` change at round 0 with no causing message and the reason
`seed: link <link_id> <link_type_id> v<version>` (the first contributing link; `(+N more)` when others gave the
same pair). Edges start from 0 and move up by the seeded values, so the logged change equals the seeded value. The change log therefore shows where every starting edge came from. Nothing here reads the
ontology: the caller passes a finished plan. Whether a run may be seeded, and not seeding twice, is the engine's
job (`Simulation.seed_relationships`).
"""

from __future__ import annotations

from typing import Any

from .seed_plan import SeedPlan


def seed_reason(edge: Any) -> str:
    refs = edge.link_refs
    if not refs:
        return f"seed: link {edge.link_ids[0]}" if edge.link_ids else "seed"
    link_id, link_type, version = refs[0]
    extra = f" (+{len(refs) - 1} more)" if len(refs) > 1 else ""
    return f"seed: link {link_id} {link_type} v{version}{extra}"


def apply_seed_plan(society: Any, plan: SeedPlan, *, round: int = 0) -> int:
    """Create every planned edge from nothing. An edge that already exists is an error, never an overwrite."""
    for edge in plan.edges:
        if society.relationship(edge.source, edge.target) is not None:
            raise ValueError(f"relationship {edge.source}->{edge.target} already exists; seeding only creates edges")
    for edge in plan.edges:
        society.adjust_relationship(
            edge.source, edge.target, round=round, trust_delta=edge.trust, familiarity_delta=edge.familiarity,
            cause_message_id=None, reason=seed_reason(edge), initial_trust=0.0, initial_familiarity=0.0)
    return len(plan.edges)


__all__ = ["apply_seed_plan", "seed_reason"]

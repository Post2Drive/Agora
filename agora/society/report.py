"""A read-only report of who communicated, what moved and what followed, from the native society store.

Phase 6 of docs/NATIVE_SOCIAL_INTERACTION_DESIGN.md. The report is computed from the append-only
message log and relationship change log only, in a fixed order, so the same store gives the same
report. It carries the store's digest, so a report can be tied to the state it describes.

Not included by default: message text and the recorded reasons (which can name handles and
conversation topics). Pass ``include_reasons`` or ``include_text`` only where the caller's sensitivity
policy allows that output to leave the run. Agents are shown by their integer ID unless ``names`` maps
IDs to labels.

What this does not show: a change of stance is recorded only in a message's free-text reason, not as a
structured value, so it is not summarised here. The report describes communication and relationship
movement; it does not show that a message caused any change in opinion or that any of it predicts an
outcome.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .store import SocietyError, SocietyStore

REPORT_FORMAT = "agora.society.report/v1"
_MAX_TOP = 100
_CAUSES = 5
LIMITS = (
    "Stance changes are recorded only in free-text reasons and are not summarised.",
    "Relationship movement shows what the contact model recorded, not that a message caused an opinion change.",
    "No claim about predictive accuracy.",
)


def _label(names: Mapping[int, str] | None, agent: int) -> Any:
    return agent if names is None or agent not in names else names[agent]


def _top(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_TOP:
        raise SocietyError(f"top must be a whole number from 1 to {_MAX_TOP}")
    return value


def society_report(
    society: SocietyStore, *, top: int = 10, names: Mapping[int, str] | None = None,
    include_reasons: bool = False, include_text: bool = False,
) -> dict[str, Any]:
    """Build the report. Reads only; the store is not changed."""
    top = _top(top)
    if names is not None and (not isinstance(names, Mapping) or not all(
            type(k) is int and isinstance(v, str) and v.strip() for k, v in names.items())):
        raise SocietyError("names must map integer agent IDs to non-empty labels")
    q = society._q

    kinds = {r["kind"]: r["n"] for r in q(
        "SELECT kind, COUNT(*) AS n FROM society_conversations GROUP BY kind ORDER BY kind")}
    total = q("SELECT COUNT(*) AS n, COUNT(DISTINCT sender_id) AS senders, MIN(round) AS first, MAX(round) AS last "
              "FROM society_messages").fetchone()
    rounds = [{"round": r["round"], "messages": r["n"], "senders": r["senders"]} for r in q(
        "SELECT round, COUNT(*) AS n, COUNT(DISTINCT sender_id) AS senders FROM society_messages "
        "GROUP BY round ORDER BY round")]
    senders = [{"agent": _label(names, r["sender_id"]), "messages": r["n"]} for r in q(
        "SELECT sender_id, COUNT(*) AS n FROM society_messages GROUP BY sender_id "
        "ORDER BY n DESC, sender_id LIMIT ?", (top,))]

    pairs = []
    for row in q(
            "SELECT c.conversation_id, c.pair_key, COUNT(m.message_id) AS n, MIN(m.round) AS first, MAX(m.round) AS last "
            "FROM society_conversations c JOIN society_messages m ON m.conversation_id=c.conversation_id "
            "WHERE c.kind='direct' GROUP BY c.conversation_id ORDER BY n DESC, c.conversation_id LIMIT ?", (top,)):
        members = sorted(a for a, _ in society.members(row["conversation_id"]))
        senders_in_order = [r["sender_id"] for r in q(
            "SELECT sender_id FROM society_messages WHERE conversation_id=? ORDER BY message_id",
            (row["conversation_id"],))]
        exchanges = sum(1 for a, b in zip(senders_in_order, senders_in_order[1:]) if a != b)
        pairs.append({"agents": [_label(names, a) for a in members], "messages": row["n"],
                      "exchanges": exchanges, "first_round": row["first"], "last_round": row["last"]})

    moves = []
    for row in q(
            "SELECT source_id, target_id, COUNT(*) AS n, SUM(trust_delta) AS trust, SUM(familiarity_delta) AS fam, "
            "MIN(round) AS first, MAX(round) AS last FROM society_relationship_changes "
            "GROUP BY source_id, target_id ORDER BY ABS(SUM(trust_delta)) DESC, source_id, target_id LIMIT ?", (top,)):
        causes = [r["cause_message_id"] for r in q(
            "SELECT cause_message_id FROM society_relationship_changes WHERE source_id=? AND target_id=? "
            "AND cause_message_id IS NOT NULL ORDER BY change_id LIMIT ?",
            (row["source_id"], row["target_id"], _CAUSES))]
        entry = {"source": _label(names, row["source_id"]), "target": _label(names, row["target_id"]),
                 "changes": row["n"], "trust_net": round(row["trust"], 6), "familiarity_net": round(row["fam"], 6),
                 "first_round": row["first"], "last_round": row["last"], "cause_messages": causes}
        if include_reasons:
            entry["reasons"] = [r["reason"] for r in q(
                "SELECT reason FROM society_relationship_changes WHERE source_id=? AND target_id=? "
                "ORDER BY change_id LIMIT ?", (row["source_id"], row["target_id"], _CAUSES))]
        moves.append(entry)
    change_count = q("SELECT COUNT(*) AS n FROM society_relationship_changes").fetchone()["n"]

    ties = [{"source": _label(names, r["source_id"]), "target": _label(names, r["target_id"]),
             "trust": round(r["trust"], 6), "familiarity": round(r["familiarity"], 6),
             "last_contact_round": r["last_contact_round"]} for r in q(
        "SELECT source_id, target_id, trust, familiarity, last_contact_round FROM society_relationships "
        "ORDER BY trust DESC, familiarity DESC, source_id, target_id LIMIT ?", (top,))]

    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "society_digest": society.digest(),
        "conversations": kinds,
        "messages": {"total": total["n"], "senders": total["senders"],
                     "first_round": total["first"], "last_round": total["last"]},
        "activity_by_round": rounds,
        "top_senders": senders,
        "top_direct_pairs": pairs,
        "relationship_changes": {"total": change_count, "largest_net_trust_moves": moves},
        "strongest_ties": ties,
        "limits": list(LIMITS),
    }
    if include_text:
        report["recent_messages"] = [
            {"message_id": r["message_id"], "round": r["round"], "sender": _label(names, r["sender_id"]),
             "conversation_id": r["conversation_id"], "text": r["text"],
             **({"reason": r["reason"]} if include_reasons else {})} for r in q(
            "SELECT message_id, round, sender_id, conversation_id, text, reason FROM society_messages "
            "ORDER BY message_id DESC LIMIT ?", (top,))]
    return report


__all__ = ["LIMITS", "REPORT_FORMAT", "society_report"]

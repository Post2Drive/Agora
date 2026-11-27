"""Where each action proposal stands, read from the anchored audit chain. Reads only; changes nothing.

The chain already holds every step (proposed, approved or rejected, withdrawn or admitted, simulation
outcome). ``list_action_proposals`` reads them once from a verified chain and returns one entry per
digest; ``action_proposal_state`` does the same for one proposal document. A digest whose events do not
fit the rules in ``approvals.py`` is reported as ``inconsistent`` with a reason, so one bad record does
not hide the others.

States: ``proposed``, ``rejected``, ``approved`` (live), ``expired``, ``withdrawn``, ``admitted``,
``simulation_succeeded``, ``simulation_failed``, ``inconsistent``.

Limits: this reads the chain only. It does not re-read objects or sources, so ``approved`` means the chain
shows a live approval, not that the proposal would still pass ``verify_approved_action``. The chain is
local, so the limits in docs/ONTOLOGY_ACTION_PROPOSALS.md apply. Listing covers every proposal in the
chain, not one project, and needs read authority at the highest classification.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
import json
from typing import Any

from ..audit_anchor import verify_anchored
from . import approvals as _a
from . import outcomes as _o
from .store import OntologyError, OntologyObjectStore

_READ = "ontology_read"
_STATUS_STATES = {"ontology_action_simulation_succeeded": "simulation_succeeded",
                  "ontology_action_simulation_failed": "simulation_failed"}
_TYPES = ({_a._PROPOSED_TYPE, _a._CO_TYPE, *_a._OUTCOMES.values(), *_a._ENDINGS, *_STATUS_STATES})
_PREFIX = "ontology_action_"


def _bad(digest: str, reason: str, /, **known: Any) -> dict[str, Any]:
    known.pop("digest", None)
    return {"digest": digest, "state": "inconsistent", "reason": reason, **known}


def _derive(digest: str, events: list[dict[str, Any]], now: datetime, lifetime: timedelta) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_type.setdefault(event["event_type"], []).append(event)
    proposed = by_type.get(_a._PROPOSED_TYPE, [])
    allowed = [e for e in proposed if e.get("decision") == "allow" and isinstance(e.get("subject_id"), str)
               and e["subject_id"].strip()]
    if len(allowed) != 1:
        return _bad(digest, "the proposal is not recorded exactly once")
    proposer = allowed[0]["subject_id"]
    entry: dict[str, Any] = {"digest": digest, "proposed_by": proposer}
    decisions = [e for t in _a._OUTCOMES.values() for e in by_type.get(t, [])]
    endings = [e for t in _a._ENDINGS for e in by_type.get(t, [])]
    results = [e for t in _STATUS_STATES for e in by_type.get(t, [])]
    suffix = digest.split(":", 1)[1]
    seconds = by_type.get(_a._CO_TYPE, [])
    if seconds and (len(seconds) != 1 or not decisions or decisions[0]["event_type"] != _a._OUTCOMES["approve"]):
        return _bad(digest, "a second approval without exactly one approval", proposed_by=proposer)
    if not decisions:
        if endings or results:
            return _bad(digest, "an ending or outcome has no decision", proposed_by=proposer)
        return {**entry, "state": "proposed"}
    if len(decisions) != 1:
        return _bad(digest, "more than one decision", proposed_by=proposer)
    decision = decisions[0]
    decider = decision.get("subject_id")
    if (decision.get("event_id") != _a._DECISION_PREFIX + suffix or decision.get("operation") != _a._DECIDE
            or decision.get("decision") != "allow" or not isinstance(decider, str) or not decider.strip()
            or decider == proposer):
        return _bad(digest, "the decision is not well formed", proposed_by=proposer)
    entry["decided_by"] = decider
    if seconds:
        co = seconds[0].get("subject_id")
        if (seconds[0].get("event_id") != _a._CO_PREFIX + suffix or seconds[0].get("operation") != _a._DECIDE
                or seconds[0].get("decision") != "allow" or not isinstance(co, str) or not co.strip()
                or co in (proposer, decider)):
            return _bad(digest, "the second approval is not well formed", **entry)
        entry["co_approved_by"] = co
    if decision["event_type"] == _a._OUTCOMES["reject"]:
        if endings or results:
            return _bad(digest, "a rejected proposal has an ending or outcome", **entry)
        return {**entry, "state": "rejected"}
    try:
        approved_at = _a._approved_at(decision)
    except OntologyError:
        return _bad(digest, "the approval has no readable time", **entry)
    entry["expires_at"] = (approved_at + lifetime).isoformat()
    if not endings:
        if results:
            return _bad(digest, "an outcome has no admission", **entry)
        return {**entry, "state": "expired" if now >= approved_at + lifetime else "approved"}
    if len(endings) != 1:
        return _bad(digest, "more than one ending", **entry)
    ending = endings[0]
    actor = ending.get("subject_id")
    if (ending.get("event_id") != _a._final_id(digest) or ending.get("decision") != "allow"
            or not isinstance(actor, str) or not actor.strip()):
        return _bad(digest, "the ending is not well formed", **entry)
    if ending["event_type"] == "ontology_action_withdrawn":
        if results:
            return _bad(digest, "an outcome has no admission", **entry)
        return {**entry, "state": "withdrawn", "ended_by": actor}
    if actor in (decider, entry.get("co_approved_by")) or ending.get("operation") != _a._ADMIT:
        return _bad(digest, "the admission is not well formed", **entry)
    entry["admitted_by"] = actor
    if not results:
        return {**entry, "state": "admitted"}
    if len(results) != 1:
        return _bad(digest, "more than one outcome", **entry)
    result = results[0]
    if (result.get("event_id") != _o._OUTCOME_PREFIX + suffix or result.get("subject_id") != actor
            or result.get("decision") != "allow"):
        return _bad(digest, "the outcome is not well formed", **entry)
    return {**entry, "state": _STATUS_STATES[result["event_type"]], "result_hash": result.get("result_hash")}


def _read(writer: Any, digest: str | None) -> dict[str, list[dict[str, Any]]]:
    """Events of the proposal types, grouped by last resource ID, from a chain verified under the lock."""
    try:
        with writer.anchors.lock():
            if not verify_anchored(writer.chain, writer.anchors)["valid"]:
                raise OntologyError("audit chain is not cleanly anchored")
            needle = digest if digest is not None else _PREFIX
            rows = writer.chain.db.execute(
                "SELECT event_json FROM audit_events WHERE instr(event_json, ?) > 0 ORDER BY seq",
                (needle,)).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for (raw,) in rows:
            event = json.loads(raw)
            resources = event.get("resource_ids")
            if event.get("event_type") in _TYPES and isinstance(resources, list) and resources \
                    and isinstance(resources[-1], str) and _a._DIGEST.fullmatch(resources[-1]):
                if digest is None or resources[-1] == digest:
                    grouped.setdefault(resources[-1], []).append(event)
        return grouped
    except OntologyError:
        raise
    except Exception as exc:
        raise OntologyError("action proposal events could not be read from the audit chain") from exc


def list_action_proposals(
    store: OntologyObjectStore, *, policy: Any, audit: Any | None, state: str | None = None,
    max_age_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Every proposal in the chain with its state, in the order proposed, optionally one state only."""
    lifetime = _a._lifetime(max_age_seconds)
    writer = _a._anchored(audit)
    store._authorize(_READ, ["action_proposal_states"], policy=policy, audit=writer, sensitivity="sensitive")
    grouped = _read(writer, None)
    now = _a._now()
    entries = [_derive(d, events, now, lifetime) for d, events in grouped.items()]
    return [e for e in entries if state is None or e["state"] == state]


def action_proposal_state(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: Any, audit: Any | None, max_age_seconds: int | None = None,
) -> dict[str, Any]:
    """The state of one proposal document, read at the proposal's own classification."""
    lifetime = _a._lifetime(max_age_seconds)
    fields = _a._fields(store, document, expected_digest)
    writer = _a._anchored(audit)
    store._authorize(_READ, [fields["pack"], fields["action"], fields["version"], expected_digest],
                     policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    events = _read(writer, expected_digest).get(expected_digest)
    if not events:
        return _bad(expected_digest, "the proposal is not recorded in this chain")
    entry = _derive(expected_digest, events, _a._now(), lifetime)
    if "proposed_by" in entry and entry["proposed_by"] != fields["proposed_by"]:
        return _bad(expected_digest, "the proposal was recorded by someone other than the person it names")
    return entry


__all__ = ["action_proposal_state", "list_action_proposals"]

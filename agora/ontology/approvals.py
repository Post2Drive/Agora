"""Approval of an action proposal by a different person, recorded in the anchored audit chain.

A proposal (``actions.propose_action``) has a digest that the chain already holds. Here an approver
decides that digest once, as someone other than the proposer, and the decision is appended to the
chain under a fixed event ID, so a second decision for the same digest is refused. ``verify_approved_action``
is the check to run before any later step acts: it re-reads the objects and sources, and finds the
proposal and one approving decision in the chain. Nothing here executes an action.

The chain keeps no free text, so the decider's reason is recorded as a hash only.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

from ..audit_anchor import require_anchored, verify_anchored
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from .actions import (
    PROPOSAL_FORMAT, _SENSITIVITY_RANK, _exact_text, proposal_digest, recheck_action_proposal,
)
from .registry import OntologyError
from .store import OntologyObjectStore

_DECIDE = "ontology_action_decide"
_PROPOSED_TYPE = "ontology_action_proposed"
_DECISION_PREFIX = "ontology-action-decision-"
# The audit chain keeps only fixed, non-free-text fields, so the outcome is the event type and the
# decider's reason is kept as a hash.
_OUTCOMES = {"approve": "ontology_action_approved", "reject": "ontology_action_rejected"}
_APPROVED_TYPE = _OUTCOMES["approve"]
_WORDS = {"approve": "approved", "reject": "rejected"}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _fields(store: OntologyObjectStore, document: Any, expected_digest: Any) -> dict[str, Any]:
    """Shape checks and the digest comparison, with no I/O. Returns the fields the decision names."""
    if not isinstance(document, Mapping):
        raise OntologyError("proposal must be a mapping")
    if not isinstance(expected_digest, str) or not _DIGEST.fullmatch(expected_digest):
        raise OntologyError("expected digest must be sha256: followed by 64 lowercase hex digits")
    try:
        matches = proposal_digest(document) == expected_digest
    except (TypeError, ValueError) as exc:
        raise OntologyError("proposal is not canonical JSON content") from exc
    if not matches:
        raise OntologyError("proposal does not match the expected digest")
    try:
        action = document["action_type"]
        fields = {
            "format": document["format"], "project_id": document["project_id"],
            "pack": document["pack_fingerprint"], "action": action["action_type_id"],
            "version": action["version"], "sensitivity": document["sensitivity"],
            "proposed_by": document["proposed_by"], "policy_version": document["policy_version"],
        }
    except (KeyError, TypeError) as exc:
        raise OntologyError("proposal is missing required content") from exc
    if fields["format"] != PROPOSAL_FORMAT or fields["project_id"] != store.project_id:
        raise OntologyError("proposal is not an action proposal for this project")
    if any(not isinstance(fields[k], str) or not fields[k].strip()
           for k in ("pack", "action", "version", "proposed_by", "policy_version")):
        raise OntologyError("proposal is missing required content")
    if fields["sensitivity"] not in _SENSITIVITY_RANK:
        raise OntologyError("proposal has an unknown classification")
    return fields


def _anchored(audit: Any) -> Any:
    try:
        return require_anchored(audit)
    except PermissionError as exc:
        raise OntologyError("approvals need an anchored audit writer") from exc


def _events(writer: Any, digest: str, event_types: Any) -> list[dict[str, Any]]:
    """Chain events of the given types whose last resource ID is this digest, read from a verified chain."""
    event_types = {event_types} if isinstance(event_types, str) else set(event_types)
    try:
        with writer.anchors.lock():
            if not verify_anchored(writer.chain, writer.anchors)["valid"]:
                raise OntologyError("audit chain is not cleanly anchored")
            rows = writer.chain.db.execute(
                "SELECT event_json FROM audit_events WHERE instr(event_json, ?) > 0 ORDER BY seq",
                (digest,)).fetchall()
        found = []
        for (raw,) in rows:
            event = json.loads(raw)
            resources = event.get("resource_ids")
            if (event.get("event_type") in event_types and isinstance(resources, list)
                    and resources and resources[-1] == digest):
                found.append(event)
        return found
    except OntologyError:
        raise
    except Exception as exc:
        raise OntologyError("action proposal events could not be read from the audit chain") from exc


def _proposed_by_this_chain(writer: Any, fields: dict[str, Any], digest: str) -> None:
    """The chain must hold a proposal event with this digest from the person the document names."""
    if not any(e.get("decision") == "allow" and e.get("subject_id") == fields["proposed_by"]
               and e.get("policy_version") == fields["policy_version"]
               for e in _events(writer, digest, _PROPOSED_TYPE)):
        raise OntologyError("this proposal was not recorded in the audit chain by the person it names")


def decide_action_proposal(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    outcome: str, reason: str, *, policy: PolicyCallable | None, audit: Any | None,
) -> dict[str, str]:
    """Approve or reject one proposal, once, as someone other than its proposer.

    ``outcome`` is ``approve`` or ``reject``. Refused if the digest was not recorded as proposed by
    the person the document names, if the deciding identity is the proposer, or if the digest
    already has a decision. Executes nothing and does not re-read the objects.
    """
    if outcome not in _OUTCOMES:
        raise OntologyError("outcome must be approve or reject")
    reason = _exact_text(reason, "reason")
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    # Decided before the chain is read, so a denied caller learns nothing about what was proposed.
    decision = store._authorize(
        _DECIDE, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = decision.get("subject_id") if isinstance(decision, Mapping) else None
    if not isinstance(subject, str) or not subject.strip() or subject == "unknown":
        raise OntologyError("approval requires a principal-bound identity")
    if subject == fields["proposed_by"]:
        raise OntologyError("a proposal must be decided by someone other than its proposer")
    _proposed_by_this_chain(writer, fields, expected_digest)
    event_id = _DECISION_PREFIX + expected_digest.split(":", 1)[1]
    if writer.find_event(event_id) is not None:
        raise OntologyError("this proposal already has a decision")
    try:
        writer.append({
            "event_id": event_id,
            "event_type": _OUTCOMES[outcome],
            "operation": _DECIDE,
            "decision": "allow",
            "subject_id": subject,
            "policy_version": str(decision.get("policy_version", "unknown")),
            "resource_ids": resource_ids,
            "reason_hash": "sha256:" + hashlib.sha256(reason.encode("utf-8")).hexdigest(),
            "reason": "policy_allow",
        })
    except AuditReplayError as exc:
        raise OntologyError("this proposal already has a decision") from exc
    return {"digest": expected_digest, "outcome": _WORDS[outcome], "decided_by": subject,
            "proposed_by": fields["proposed_by"]}


def verify_approved_action(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
) -> dict[str, str]:
    """Raise unless this exact proposal is still valid and holds one approving decision from someone else.

    Needs read authority (the objects and sources are re-read, so a proposal whose pack, objects or
    sources changed is refused), then checks the chain: the proposal was recorded by the person it
    names, and its single decision is an approval by a different identity. Run it again immediately
    before acting; an approval is not a lease and does not expire.
    """
    fields = _fields(store, document, expected_digest)
    writer = _anchored(audit)
    recheck_action_proposal(store, document, expected_digest, policy=policy, audit=writer,
                            purpose=purpose, retention=retention)
    _proposed_by_this_chain(writer, fields, expected_digest)
    decided = _events(writer, expected_digest, _OUTCOMES.values())
    if not decided:
        raise OntologyError("this proposal has not been decided")
    if len(decided) != 1:
        raise OntologyError("this proposal has more than one decision")
    event = decided[0]
    if (event.get("event_id") != _DECISION_PREFIX + expected_digest.split(":", 1)[1]
            or event.get("operation") != _DECIDE or event.get("decision") != "allow"):
        raise OntologyError("the decision event is not well formed")
    if event.get("event_type") != _APPROVED_TYPE:
        raise OntologyError("this proposal was not approved")
    approver = event.get("subject_id")
    if not isinstance(approver, str) or not approver.strip() or approver == fields["proposed_by"]:
        raise OntologyError("the approval is not from someone other than the proposer")
    return {"digest": expected_digest, "approved_by": approver, "proposed_by": fields["proposed_by"]}


__all__ = ["decide_action_proposal", "verify_approved_action"]

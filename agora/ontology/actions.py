"""Action proposals over exact ontology objects. Nothing here executes an action.

A proposal binds one declared ActionType to an exact actor object, target object,
parameter set and cited source records, and gives that content one digest. A
later approval step can name the digest; this module does not approve, queue,
apply or write back anything. It evaluates only preconditions written as ``expr:`` (see preconditions.py).

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any
import uuid

from .. import protection as _protection
from ..audit_anchor import require_anchored
from ..policy_enforcement import PolicyCallable
from .binding import _is_allowed_value
from . import preconditions
from .registry import ActionType, OntologyError, OntologyPack, PropertyType, ProposalMismatchError
from .store import OntologyObjectStore, _canonical, _canonical_timestamp

PROPOSAL_FORMAT = "agora.ontology.action_proposal/v1"
_PROPOSE = "ontology_action_propose"
_READ = "ontology_read"
_SENSITIVITY_RANK = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
_MAX_TEXT = 4096
_MAX_PARAMETERS = 64
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Fields that say who built a proposal. Rebuilding cannot authenticate them.
_AUTHORSHIP = ("proposed_by", "policy_version")


@dataclass(frozen=True)
class ActionProposal:
    """Canonical proposal text and its digest. ``document`` returns a fresh copy."""

    content: str
    digest: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self.content)


def proposal_digest(document: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(dict(document)).encode("utf-8")).hexdigest()


def _exact_text(value: Any, field: str) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value) > _MAX_TEXT):
        raise OntologyError(f"{field} must be a canonical non-empty string")
    return value


def _action_type(pack: OntologyPack, action_type_id: str, version: str) -> ActionType:
    found = [x for x in pack.action_types
             if x.action_type_id == action_type_id and x.version == version]
    if len(found) != 1:
        raise OntologyError("action type/version does not resolve in the selected pack")
    action = found[0]
    # The pack parser enforces these; checked again because they bound what a proposal may mean.
    if (action.simulated_only is not True or action.execution_mode != "simulation_only"
            or action.external_writeback != "prohibited"):
        raise OntologyError("only simulation-only action types can be proposed")
    return action


def _input_properties(pack: OntologyPack, action: ActionType) -> dict[str, PropertyType]:
    """Each declared input must name one property of the pack, or nothing can type it."""
    properties = {x.property_id: x for x in pack.property_types}
    if len(set(action.inputs)) != len(action.inputs):
        raise OntologyError("action type repeats an input")
    if any(name not in properties for name in action.inputs):
        raise OntologyError("action type has an input that is not a pack property")
    return {name: properties[name] for name in action.inputs}


def _parameter(value: Any, prop: PropertyType) -> Any:
    """Return the canonical form of one parameter value; errors never carry the value."""
    refused = OntologyError(f"parameter value is not valid for property {prop.property_id}")
    if value is None:
        if not prop.nullable:
            raise refused
        return None
    kind = prop.data_type
    if kind == "boolean":
        if type(value) is not bool:
            raise refused
    elif kind == "integer":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise refused
    elif kind in {"string", "identifier", "enum", "decimal", "date", "timestamp"}:
        if not isinstance(value, str) or len(value) > _MAX_TEXT:
            raise refused
        if kind in {"identifier", "enum"} and (not value or value != value.strip()):
            raise refused
        if kind == "decimal":
            # Text only: a binary float has no exact canonical form.
            if not _DECIMAL.fullmatch(value):
                raise refused
            try:
                Decimal(value)
            except InvalidOperation as exc:
                raise refused from exc
        elif kind == "date":
            if not _DATE.fullmatch(value):
                raise refused
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise refused from exc
        elif kind == "timestamp":
            try:
                value = _canonical_timestamp(value, "parameter")
            except (OntologyError, ValueError, TypeError, OverflowError) as exc:
                raise refused from exc
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise refused from exc
    else:
        raise OntologyError(f"parameters of data type {kind} are not supported")
    if prop.allowed_values and not _is_allowed_value(value, prop):
        raise refused
    return value


def _evidence(refs: Any) -> list[tuple[str, str, int]]:
    parsed = OntologyObjectStore._parse_source_refs(refs)
    if any(set(ref) != {"import_id", "file_sha256", "locator"} for ref in refs):
        raise OntologyError("evidence refs carry only import_id, file_sha256, and locator")
    if len(set(parsed)) != len(parsed):
        raise OntologyError("evidence cites the same source record twice")
    return sorted(parsed)


def _compose(
    store: OntologyObjectStore, operation: str, pack_fingerprint: str,
    action_type_id: str, action_type_version: str,
    actor: Mapping[str, Any], target: Mapping[str, Any],
    parameters: Mapping[str, Any], evidence: list[Mapping[str, Any]], reason: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None, retention: str | None,
) -> tuple[dict[str, Any], list[str]]:
    # Shape checks first: no I/O.
    pack_fingerprint = _exact_text(pack_fingerprint, "pack_fingerprint")
    action_type_id = _exact_text(action_type_id, "action_type_id")
    action_type_version = _exact_text(action_type_version, "action_type_version")
    reason = _exact_text(reason, "reason")
    ends = {
        "actor": store._canonical_endpoint(actor, store.project_id, pack_fingerprint),
        "target": store._canonical_endpoint(target, store.project_id, pack_fingerprint),
    }
    if not isinstance(parameters, Mapping) or len(parameters) > _MAX_PARAMETERS or not all(
            isinstance(name, str) for name in parameters):
        raise OntologyError("parameters must map input property IDs to values")
    parameters = dict(parameters)
    cited = _evidence(evidence)
    keys = {role: store._link_key(end) for role, end in ends.items()}
    resource_ids = [pack_fingerprint, action_type_id, action_type_version,
                    *keys["actor"], *keys["target"],
                    *sorted({import_id for import_id, _, _ in cited})]

    # Decide before any lookup, so a denied caller learns nothing about what exists.
    store._authorize(operation, resource_ids, policy=policy, audit=audit)
    pack = store.get_pack(pack_fingerprint, policy=policy, audit=audit)
    action = _action_type(pack, action_type_id, action_type_version)
    object_versions = {x.type_id: x.version for x in pack.object_types}
    for role, type_id in (("actor", action.actor_type_id), ("target", action.target_type_id)):
        if (ends[role]["type_id"], ends[role]["type_version"]) != (type_id, object_versions[type_id]):
            raise OntologyError(f"{role} object does not match the action type")
    inputs = _input_properties(pack, action)
    if set(parameters) != set(inputs):
        raise OntologyError("parameters must name exactly the action type inputs")
    values = {name: _parameter(parameters[name], inputs[name]) for name in sorted(inputs)}

    connection = store._connect()
    try:
        stored = store._endpoint_sensitivity(
            connection, store.project_id, pack_fingerprint, [keys["actor"], keys["target"]])
    finally:
        connection.close()
    sensitivity = max([stored, *(x.sensitivity for x in inputs.values())],
                      key=_SENSITIVITY_RANK.__getitem__)
    decision = store._authorize(
        operation, resource_ids, policy=policy, audit=audit, sensitivity=sensitivity)
    subject = decision.get("subject_id") if isinstance(decision, Mapping) else None
    version = decision.get("policy_version") if isinstance(decision, Mapping) else None
    if not isinstance(subject, str) or not subject.strip() or subject == "unknown":
        raise OntologyError("action proposals require a principal-bound identity")

    objects = {}
    stored_values = {}
    for role, end in ends.items():
        # Re-reads the exact source row under the binding policy and checks stored provenance.
        instance = store.get_object(
            pack_fingerprint, end["type_id"], end["type_version"], end["record_key"],
            end["import_id"], policy=policy, audit=audit, purpose=purpose, retention=retention)
        stored_values[role] = instance["property_values"]
        objects[role] = {
            **end,
            "binding_fingerprint": instance["binding_fingerprint"],
            "schema_fingerprint": instance["schema_fingerprint"],
            "file_sha256": instance["file_sha256"],
            "source_row_id": instance["row_id"],
            "values_sha256": proposal_digest(instance["property_values"]),
        }
    # Evaluated on every build, so a recheck at approval and admission evaluates them again.
    expressions = [text for text in action.preconditions if preconditions.is_expression(text)]
    if expressions:
        properties = {x.property_id: x for x in pack.property_types}
        scope = {**stored_values, "param": values}
        for text in expressions:
            if not preconditions.evaluate(text, properties, scope):
                raise ProposalMismatchError(f"a declared precondition is not met: {text}")
    # After authorization, so an unauthorized caller cannot probe which imports exist.
    store._verify_link_source_refs(cited, audit)

    document = {
        "format": PROPOSAL_FORMAT,
        "project_id": store.project_id,
        "pack_fingerprint": pack_fingerprint,
        "action_type": {"action_type_id": action_type_id, "version": action_type_version,
                        "fingerprint": action.fingerprint},
        "actor": objects["actor"],
        "target": objects["target"],
        "parameters": values,
        "evidence": [{"import_id": i, "file_sha256": d, "locator": f"row:{n}"}
                     for i, d, n in cited],
        "reason": reason,
        "sensitivity": sensitivity,
        "proposed_by": subject,
        "policy_version": str(version) if version is not None else "unknown",
        "declared_preconditions": list(action.preconditions),
        "declared_effects": list(action.effects),
        "declared_permissions": list(action.permissions),
        "preconditions_evaluated": bool(action.preconditions) and len(expressions) == len(action.preconditions),
        "executed": False,
        "execution_mode": action.execution_mode,
        "external_writeback": action.external_writeback,
    }
    if expressions:
        # Only present when something was evaluated, so documents for packs without expressions are unchanged.
        document["preconditions_met"] = expressions
    return document, resource_ids


def propose_action(
    store: OntologyObjectStore, pack_fingerprint: str,
    action_type_id: str, action_type_version: str,
    actor: Mapping[str, Any], target: Mapping[str, Any],
    parameters: Mapping[str, Any], evidence: list[Mapping[str, Any]], reason: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
) -> ActionProposal:
    """Build one proposal and record its digest in the audit chain. Executes nothing."""
    document, resource_ids = _compose(
        store, _PROPOSE, pack_fingerprint, action_type_id, action_type_version,
        actor, target, parameters, evidence, reason,
        policy=policy, audit=audit, purpose=purpose, retention=retention)
    proposal = ActionProposal(_canonical(document), proposal_digest(document))
    writer = require_anchored(audit) if _protection.ANCHOR_REQUIRED else audit
    writer.append({
        "event_id": f"ontology-{uuid.uuid4().hex}",
        "event_type": "ontology_action_proposed",
        "operation": _PROPOSE,
        "decision": "allow",
        "subject_id": document["proposed_by"],
        "policy_version": document["policy_version"],
        "resource_ids": [*resource_ids, proposal.digest],
        "proposal_sensitivity": document["sensitivity"],
        "reason": "proposal_recorded_not_executed",
    })
    return proposal


def recheck_action_proposal(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
) -> None:
    """Raise unless the document has this digest and still matches the stored pack and sources.

    ``expected_digest`` must come from somewhere the document's holder cannot
    rewrite. ``proposed_by`` and ``policy_version`` are covered by the digest but
    cannot be rebuilt, and this does not show that anyone approved the proposal.
    """
    if not isinstance(document, Mapping):
        raise OntologyError("proposal must be a mapping")
    try:
        matches = proposal_digest(document) == expected_digest
    except (TypeError, ValueError) as exc:
        raise OntologyError("proposal is not canonical JSON content") from exc
    if not matches:
        raise OntologyError("proposal does not match the expected digest")
    try:
        if document["format"] != PROPOSAL_FORMAT:
            raise OntologyError("unsupported proposal format")
        action = document["action_type"]
        ends = [
            {key: document[role][key] for key in (
                "project_id", "pack_fingerprint", "type_id", "type_version",
                "import_id", "record_key")}
            for role in ("actor", "target")
        ]
        request = (document["pack_fingerprint"], action["action_type_id"], action["version"],
                   *ends, document["parameters"], document["evidence"], document["reason"])
    except (KeyError, TypeError) as exc:
        raise OntologyError("proposal is missing required content") from exc
    rebuilt, _ = _compose(
        store, _READ, *request,
        policy=policy, audit=audit, purpose=purpose, retention=retention)
    for name in _AUTHORSHIP:
        if not isinstance(document.get(name), str):
            raise OntologyError("proposal is missing required content")
        rebuilt[name] = document[name]
    # Canonical text, not ==: Python treats True as 1.
    if _canonical(rebuilt) != _canonical(dict(document)):
        raise ProposalMismatchError("proposal no longer matches the pack and source records")


__all__ = [
    "PROPOSAL_FORMAT", "ActionProposal", "proposal_digest", "propose_action",
    "recheck_action_proposal",
]

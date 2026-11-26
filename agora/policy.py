"""Deny-by-default RBAC + ABAC policy decision point.

This module is intentionally standalone. Protected boundaries call it through
the shared enforcement layer with an adapter-bound principal.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

POLICY_VERSION = "stage2-v2"
OPERATIONS = frozenset({
    "import", "binding", "simulation_input", "report_export",
    "decision_approval", "decision_outcome", "reconciliation_repair",
    "ontology_read", "ontology_write",
})
SENSITIVITY_RANK = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}

# Keep this deliberately small until an identity adapter defines the complete
# enterprise role model. Unknown roles are denied rather than inferred.
ROLE_OPERATIONS = {
    "operator": OPERATIONS - {"decision_approval", "reconciliation_repair"},
    "reviewer": frozenset({"binding", "report_export", "decision_outcome", "ontology_read"}),
    "approver": frozenset({"report_export", "decision_approval", "reconciliation_repair"}),
    "reader": frozenset({"report_export", "ontology_read"}),
}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _subject_id(subject: Any) -> str:
    if isinstance(subject, Mapping):
        return _text(subject.get("subject_id") or subject.get("id")) or "unknown"
    return _text(subject) or "unknown"


def _scope(subject: Any, resource: Mapping[str, Any]) -> tuple[str | None, str | None]:
    subject_scope = subject.get("project_id") if isinstance(subject, Mapping) else None
    subject_scope = subject_scope or (subject.get("tenant_id") if isinstance(subject, Mapping) else None)
    resource_scope = resource.get("project_id") or resource.get("tenant_id")
    target_scope = resource.get("resource_project_id") or resource.get("resource_tenant_id")
    return (str(subject_scope) if subject_scope is not None else None,
            str(resource_scope or target_scope) if (resource_scope or target_scope) is not None else None)


def _decision(subject: Any, role: Any, operation: Any, resource: Mapping[str, Any],
              *, policy_version: str, allowed: bool, reason: str) -> dict[str, Any]:
    ids = resource.get("resource_ids", resource.get("resource_id", []))
    if isinstance(ids, str):
        ids = [ids]
    elif not isinstance(ids, (list, tuple, set)):
        ids = []
    safe_ids = [str(item) for item in ids if isinstance(item, (str, int))]
    return {
        "subject_id": _subject_id(subject),
        "policy_version": policy_version,
        "decision": "allow" if allowed else "deny",
        "resource_ids": safe_ids,
        "reason": reason,
    }


def decide(subject: Any, role: str, operation: str, resource: Mapping[str, Any],
           *, policy_version: str = POLICY_VERSION) -> dict[str, Any]:
    """Return an audit-safe allow/deny decision for one boundary operation."""
    if not isinstance(resource, Mapping):
        resource = {}
    deny = lambda why: _decision(subject, role, operation, resource,
                                  policy_version=policy_version, allowed=False, reason=why)
    if role not in ROLE_OPERATIONS:
        return deny("unknown_role")
    if operation not in OPERATIONS:
        return deny("unknown_operation")
    if operation not in ROLE_OPERATIONS[role]:
        return deny("role_not_permitted")

    source_role = resource.get("source_role") or resource.get("data_role")
    if source_role == "sealed_holdout":
        return deny("sealed_holdout_forbidden")

    subject_scope, resource_scope = _scope(subject, resource)
    if subject_scope is None or resource_scope is None:
        return deny("scope_missing")
    if subject_scope != resource_scope:
        return deny("cross_scope")

    source_sensitivity = resource.get("source_sensitivity", resource.get("sensitivity"))
    target_sensitivity = resource.get("target_sensitivity", source_sensitivity)
    if source_sensitivity not in SENSITIVITY_RANK or target_sensitivity not in SENSITIVITY_RANK:
        return deny("sensitivity_missing")
    if SENSITIVITY_RANK[target_sensitivity] < SENSITIVITY_RANK[source_sensitivity]:
        return deny("sensitivity_downgrade")

    requires_policy = operation != "import" or bool(
        resource.get("will_bind") or resource.get("downstream_use")
    )
    if SENSITIVITY_RANK[source_sensitivity] >= SENSITIVITY_RANK["personal"] and requires_policy:
        if not _text(resource.get("purpose")) or not _text(resource.get("retention")):
            return deny("personal_data_policy_required")
    return _decision(subject, role, operation, resource, policy_version=policy_version,
                     allowed=True, reason="policy_allow")


def authorize(subject: Any, role: str, operation: str, resource: Mapping[str, Any],
              *, policy_version: str = POLICY_VERSION) -> dict[str, Any]:
    """Compatibility name for enforcement points."""
    return decide(subject, role, operation, resource, policy_version=policy_version)

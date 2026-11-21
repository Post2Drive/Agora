"""Shared fail-closed policy enforcement and denial audit recording.

A policy hook is a callable with the signature
policy(operation: str, resource: Mapping[str, Any]) -> Mapping[str, Any].
It should return an audit-safe decision mapping whose decision is allow or deny.
Callers can bind identity and role around agora.policy.decide.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import uuid
from typing import Any

from .audit_chain import AuditChainStore


class PolicyEnforcementError(PermissionError):
    """Raised when a policy hook denies or cannot decide an operation."""


PolicyCallable = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def enforce_policy(
    policy: PolicyCallable | None,
    *,
    project: str | Path,
    operation: str,
    resource: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Evaluate an optional decision callable and audit every denial.

    With policy=None this is a no-op, preserving legacy caller behaviour.
    The policy receives only declared metadata; callers invoke this before
    reading source bytes or snapshot databases.
    """
    if policy is None:
        return None
    if not callable(policy):
        decision: Mapping[str, Any] = {
            "decision": "deny", "reason": "policy_not_callable",
            "subject_id": "unknown", "policy_version": "unknown",
        }
    else:
        try:
            candidate = policy(operation, dict(resource))
            decision = candidate if isinstance(candidate, Mapping) else {
                "decision": "deny", "reason": "invalid_policy_decision",
                "subject_id": "unknown", "policy_version": "unknown",
            }
        except Exception:
            decision = {
                "decision": "deny", "reason": "policy_evaluation_error",
                "subject_id": "unknown", "policy_version": "unknown",
            }

    if decision.get("decision") == "allow":
        return decision

    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "policy_denied"
    subject_id = decision.get("subject_id")
    if not isinstance(subject_id, (str, int)) or not str(subject_id).strip():
        subject_id = "unknown"
    policy_version = decision.get("policy_version")
    if not isinstance(policy_version, str) or not policy_version.strip():
        policy_version = "unknown"
    resource_ids = decision.get("resource_ids", resource.get("resource_ids", []))
    if isinstance(resource_ids, (str, int)):
        resource_ids = [resource_ids]
    if not isinstance(resource_ids, (list, tuple, set)):
        resource_ids = []
    safe_resource_ids = [str(value) for value in resource_ids
                         if isinstance(value, (str, int)) and str(value).strip()]

    audit_path = Path(project) / "data" / "audit_chain.sqlite3"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        store = AuditChainStore(audit_path)
        try:
            store.append({
                "event_id": f"policy-denial-{uuid.uuid4().hex}",
                "event_type": "policy_denied",
                "subject_id": str(subject_id),
                "operation": operation,
                "decision": "deny",
                "policy_version": policy_version,
                "resource_ids": safe_resource_ids,
                "reason": reason,
            })
        finally:
            store.close()
    except Exception as exc:
        raise PolicyEnforcementError(
            "policy denied the operation and the denial audit could not be recorded"
        ) from exc

    raise PolicyEnforcementError(f"policy denied the {operation} operation: {reason}")


__all__ = ["PolicyCallable", "PolicyEnforcementError", "enforce_policy"]

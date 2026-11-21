"""Shared fail-closed policy enforcement and denial audit recording.

A policy hook is a callable with the signature
policy(operation: str, resource: Mapping[str, Any]) -> Mapping[str, Any].
It should return an audit-safe decision mapping whose decision is allow or deny.
Callers can bind identity and role around agora.policy.decide.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import re
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

    def safe_token(value: Any, *, limit: int = 128) -> str | None:
        if not isinstance(value, (str, int)):
            return None
        token = str(value).strip()
        if len(token) > limit or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", token):
            return None
        return token

    reason = safe_token(decision.get("reason"), limit=64) or "policy_denied"
    subject_id = safe_token(decision.get("subject_id")) or "unknown"
    policy_version = safe_token(decision.get("policy_version"), limit=64) or "unknown"
    # Audit only the resource identifiers supplied by the caller, not values
    # returned by an arbitrary decision callable.
    resource_ids = resource.get("resource_ids", [])
    if isinstance(resource_ids, (str, int)):
        resource_ids = [resource_ids]
    if not isinstance(resource_ids, (list, tuple, set)):
        resource_ids = []
    safe_resource_ids = [token for value in resource_ids
                         if (token := safe_token(value)) is not None]

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

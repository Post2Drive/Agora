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

from . import protection as _protection
from .audit_chain import AuditChainStore


class PolicyEnforcementError(PermissionError):
    """Raised when a policy hook denies or cannot decide an operation."""


PolicyCallable = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

_MINT = object()  # module-private capability token; only _mint_principal_policy holds it


class PrincipalPolicy:
    """Unforgeable policy capability bound to an adapter-issued Principal.

    Instances can only be minted by agora.principal.principal_policy() (via the
    private token). Subclassing and direct construction are refused, so a raw
    always-allow callable can never be presented as one. enforce_policy() in
    protected mode (agora.protection.POLICY_REQUIRED) accepts nothing else.
    """

    __slots__ = ("_fn", "_principal")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("PrincipalPolicy cannot be subclassed")

    def __new__(cls, *args: Any, **kwargs: Any) -> "PrincipalPolicy":
        if not args or args[0] is not _MINT:
            raise TypeError("PrincipalPolicy can only be minted by agora.principal.principal_policy()")
        return super().__new__(cls)

    def __init__(self, token: object, fn: PolicyCallable, principal: Any) -> None:
        object.__setattr__(self, "_fn", fn)
        object.__setattr__(self, "_principal", principal)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("PrincipalPolicy is immutable")

    def __call__(self, operation: str, resource: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._fn(operation, resource)


def _mint_principal_policy(fn: PolicyCallable, principal: Any) -> PrincipalPolicy:
    return PrincipalPolicy(_MINT, fn, principal)


def _is_principal_bound(policy: Any) -> bool:
    # A non-Principal binding is still safe: decide_principal() denies it
    # (principal_missing), so only the mint provenance needs checking here.
    return type(policy) is PrincipalPolicy


_NOT_BOUND = object()


def enforce_policy(
    policy: PolicyCallable | None,
    *,
    project: str | Path,
    operation: str,
    resource: Mapping[str, Any],
    audit: Any | None = None,
) -> Mapping[str, Any] | None:
    """Evaluate an optional decision callable and audit every denial.

    With policy=None this is a no-op, preserving legacy caller behaviour.
    The policy receives only declared metadata; callers invoke this before
    reading source bytes or snapshot databases.

    audit, when given, is an object with append(event) (for example an
    AnchoredAuditChain). The caller owns its lifecycle. Without it, a denial is
    still raised but is NOT written to an unanchored chain when anchoring is
    required (the default); the legacy unanchored project-local chain is used
    only when agora.protection.ANCHOR_REQUIRED is relaxed (tests).

    There is no caller override: whether a missing policy is denied is decided
    only by agora.protection.POLICY_REQUIRED (True in production). When
    agora.protection.ANCHOR_REQUIRED is set, a denial is written only through an
    AnchoredAuditChain (checked with require_anchored); None or a plain
    AuditChainStore is refused and the denial is still raised.
    """
    if policy is None and not _protection.POLICY_REQUIRED:
        return None
    if policy is not None and callable(policy) and _protection.POLICY_REQUIRED \
            and not _is_principal_bound(policy):
        # Protected mode: a raw callable (e.g. always-allow) is never trusted.
        policy = _NOT_BOUND
    if policy is None or not callable(policy) or policy is _NOT_BOUND:
        decision: Mapping[str, Any] = {
            "decision": "deny",
            "reason": ("policy_required" if policy is None else
                       "policy_not_principal_bound" if policy is _NOT_BOUND else
                       "policy_not_callable"),
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

    event = {
        "event_id": f"policy-denial-{uuid.uuid4().hex}",
        "event_type": "policy_denied",
        "subject_id": str(subject_id),
        "operation": operation,
        "decision": "deny",
        "policy_version": policy_version,
        "resource_ids": safe_resource_ids,
        "reason": reason,
    }
    try:
        if _protection.ANCHOR_REQUIRED:
            if audit is None:
                raise PolicyEnforcementError("no anchored audit writer supplied")
            from .audit_anchor import require_anchored
            require_anchored(audit).append(event)
        elif audit is not None:
            audit.append(event)
        else:
            audit_path = Path(project) / "data" / "audit_chain.sqlite3"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            store = AuditChainStore(audit_path)
            try:
                store.append(event)
            finally:
                store.close()
    except Exception as exc:
        raise PolicyEnforcementError(
            "policy denied the operation and the denial audit could not be recorded"
        ) from exc

    raise PolicyEnforcementError(f"policy denied the {operation} operation: {reason}")


__all__ = ["PolicyCallable", "PrincipalPolicy", "PolicyEnforcementError", "enforce_policy"]

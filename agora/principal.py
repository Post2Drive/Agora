"""Trusted principal boundary (first slice: synthetic fixtures only).

A Principal is issued by an adapter, never built from request input. The
principal-based decision derives role, scope and assurance from the principal
and then delegates to the central PDP. No OIDC, network or real credentials.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

from agora.policy import ROLE_OPERATIONS, decide


class IdentityError(ValueError):
    """Raised when a principal or adapter input is invalid."""


class Assurance(IntEnum):
    LOW = 0
    STANDARD = 1
    HIGH = 2


# Minimum assurance per operation; unlisted operations need STANDARD.
MIN_ASSURANCE = {"decision_approval": Assurance.HIGH, "decision_outcome": Assurance.STANDARD}


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise IdentityError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class Principal:
    subject_id: str
    tenant_id: str
    project_ids: frozenset[str]
    roles: frozenset[str]
    assurance: Assurance
    issuer: str
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("subject_id", "tenant_id", "issuer"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise IdentityError(f"{name} is required")
        if not isinstance(self.project_ids, frozenset) or not all(
            isinstance(p, str) and p.strip() for p in self.project_ids
        ):
            raise IdentityError("project_ids must be a frozenset of non-empty strings")
        if not isinstance(self.roles, frozenset) or not self.roles:
            raise IdentityError("roles must be a non-empty frozenset")
        unknown = self.roles - set(ROLE_OPERATIONS)
        if unknown:
            raise IdentityError("unknown role in principal")
        if not isinstance(self.assurance, Assurance):
            raise IdentityError("assurance must be an Assurance value")
        object.__setattr__(self, "expires_at", _utc(self.expires_at, "expires_at"))


class SyntheticFixtureAdapter:
    """Test-only adapter: resolves a fixture key to a fixed fixture definition.

    It refuses to construct in production mode and never accepts caller-supplied
    roles or scopes, only a key that must exist in the fixture table.
    """

    ISSUER = "synthetic-fixture-issuer"

    def __init__(self, fixtures: Mapping[str, Mapping[str, Any]], *, production: bool = False) -> None:
        if production:
            raise IdentityError("synthetic adapter is disabled in production mode")
        self._fixtures = {key: dict(value) for key, value in fixtures.items()}

    def issue(self, fixture_key: str) -> Principal:
        fixture = self._fixtures.get(fixture_key)
        if fixture is None:
            raise IdentityError("unknown fixture identity")
        try:
            return Principal(
                subject_id=fixture["subject_id"], tenant_id=fixture["tenant_id"],
                project_ids=frozenset(fixture["project_ids"]), roles=frozenset(fixture["roles"]),
                assurance=Assurance[fixture["assurance"]], issuer=self.ISSUER,
                expires_at=fixture["expires_at"],
            )
        except KeyError as exc:
            raise IdentityError("malformed fixture identity") from exc


def decide_principal(
    principal: Principal | None, operation: str, resource: Mapping[str, Any],
    *, now: datetime | None = None, trusted_issuers: frozenset[str] = frozenset({SyntheticFixtureAdapter.ISSUER}),
) -> tuple[dict[str, Any], str | None]:
    """Return (audit-safe decision, role that allowed it). Fails closed."""
    def deny(reason: str, subject: str = "unknown") -> tuple[dict[str, Any], None]:
        base = decide({"subject_id": subject}, "reader", "unknown_operation", {})
        base.update({"decision": "deny", "reason": reason, "subject_id": subject})
        return base, None

    if not isinstance(principal, Principal):
        return deny("principal_missing")
    sid = principal.subject_id
    moment = _utc(now or datetime.now(timezone.utc), "now")
    if moment >= principal.expires_at:
        return deny("principal_expired", sid)
    if principal.issuer not in trusted_issuers:
        return deny("issuer_untrusted", sid)
    if not isinstance(resource, Mapping):
        return deny("scope_missing", sid)
    project = resource.get("project_id")
    if not isinstance(project, str) or not project:
        return deny("scope_missing", sid)
    if project not in principal.project_ids:
        return deny("cross_scope", sid)
    tenant = resource.get("tenant_id")
    if tenant is not None and tenant != principal.tenant_id:
        return deny("cross_tenant", sid)
    if principal.assurance < MIN_ASSURANCE.get(operation, Assurance.STANDARD):
        return deny("assurance_insufficient", sid)

    last: dict[str, Any] | None = None
    for role in sorted(principal.roles):
        result = decide({"subject_id": sid, "project_id": project}, role, operation, resource)
        if result["decision"] == "allow":
            return result, role
        last = result
    return (last or deny("role_not_permitted", sid)[0]), None


__all__ = ["Assurance", "IdentityError", "Principal", "SyntheticFixtureAdapter", "decide_principal"]

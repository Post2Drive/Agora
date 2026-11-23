"""Trusted principal boundary (first slice: synthetic fixtures only).

A Principal is issued by an adapter, never built from request input. The
principal-based decision derives role, scope and assurance from the principal
and then delegates to the central PDP. No OIDC, network or real credentials.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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


class _IssueKey:
    __slots__ = ()


_ISSUED = _IssueKey()


@dataclass(frozen=True)
class Principal:
    subject_id: str
    tenant_id: str
    project_ids: frozenset[str]
    roles: frozenset[str]
    assurance: Assurance
    issuer: str
    expires_at: datetime
    # Adapter provenance: only SyntheticFixtureAdapter.issue() sets this (module-private key).
    # A hand-built Principal carries None and is denied by decide_principal ("principal_not_adapter_issued").
    # Residual: in-process Python can still reach _ISSUED; real separation needs the production adapter.
    _origin: object = field(default=None, repr=False, compare=False)

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
                expires_at=fixture["expires_at"], _origin=_ISSUED,
            )
        except KeyError as exc:
            raise IdentityError("malformed fixture identity") from exc


def decide_principal(
    principal: Principal | None, operation: str, resource: Mapping[str, Any],
    *, now: datetime | None = None, required_role: str | None = None,
    trusted_issuers: frozenset[str] = frozenset({SyntheticFixtureAdapter.ISSUER}),
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
    if principal._origin is not _ISSUED:
        return deny("principal_not_adapter_issued", sid)
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

    candidates = sorted(principal.roles)
    if required_role is not None:
        if required_role not in principal.roles:
            return deny("role_not_permitted", sid)
        candidates = [required_role]
    last: dict[str, Any] | None = None
    for role in candidates:
        result = decide({"subject_id": sid, "project_id": project}, role, operation, resource)
        if result["decision"] == "allow":
            return result, role
        last = result
    return (last or deny("role_not_permitted", sid)[0]), None


class BoundPolicy:
    """A policy callable provably bound to a Principal.

    enforce_policy() accepts a policy only when it is a BoundPolicy; an arbitrary
    (operation, resource) lambda is refused under protection.PRINCIPAL_BOUND_REQUIRED.
    The binding is not, by itself, trust: every call still runs decide_principal,
    which rejects an untrusted issuer, expiry, wrong scope or insufficient
    assurance. A BoundPolicy carrying a hand-built principal with an untrusted
    issuer is therefore denied at decision time, not accepted.
    """

    __slots__ = ("_principal", "_required_role", "_now", "_trusted_issuers")

    def __init__(self, principal: Principal | None, *, required_role: str | None,
                 now: datetime | None, trusted_issuers: frozenset[str]):
        if principal is not None and not isinstance(principal, Principal):
            raise IdentityError("BoundPolicy requires a Principal or None")
        self._principal = principal
        self._required_role = required_role
        self._now = now
        self._trusted_issuers = trusted_issuers

    @property
    def principal(self) -> Principal | None:
        return self._principal

    def __call__(self, operation: str, resource: Mapping[str, Any]) -> dict[str, Any]:
        decision, _ = decide_principal(
            self._principal, operation, resource, now=self._now,
            required_role=self._required_role, trusted_issuers=self._trusted_issuers)
        return decision


def is_principal_bound(policy: Any) -> bool:
    """True only for an exact BoundPolicy instance (the forgeable surface is the
    Principal it carries, which decide_principal re-checks on every call)."""
    # Exact type: a subclass could override __call__ and bypass decide_principal.
    return type(policy) is BoundPolicy


def principal_policy(
    principal: Principal | None, *, required_role: str | None = None,
    now: datetime | None = None,
    trusted_issuers: frozenset[str] = frozenset({SyntheticFixtureAdapter.ISSUER}),
) -> BoundPolicy:
    """Bind a Principal into a BoundPolicy for enforce_policy().

    The callback takes only (operation, resource): authority comes from the bound,
    adapter-issued principal, never from resource fields or caller roles.
    """
    return BoundPolicy(principal, required_role=required_role, now=now,
                       trusted_issuers=trusted_issuers)


class _MintKey:
    """Module-private capability: only code in this module can hold the single instance."""
    __slots__ = ()


_MINT = _MintKey()
_SCOPE_FIELDS = ("project_id", "import_id", "binding_id", "manifest_hash", "scenario_hash")


class AuthorizationReceipt:
    """Opaque proof that a Principal-bound policy ALLOWED one exact simulation input.

    Minted only by mint_simulation_receipt() after an allow decision; bound to the principal's issuer,
    subject, role and expiry and to the exact project, import, binding, manifest and scenario hash.
    Not constructible, copyable or picklable by callers; a plain mapping is never accepted as proof."""

    __slots__ = ("_token", "issuer", "subject_id", "role", "expires_at", "project_id", "import_id",
                 "binding_id", "manifest_hash", "scenario_hash")

    def __init__(self, token: object, **fields: Any) -> None:
        if token is not _MINT:
            raise IdentityError("authorization receipts can only be minted from an allow decision")
        object.__setattr__(self, "_token", token)
        for name, value in fields.items():
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("receipt is immutable")

    def __reduce__(self):  # blocks pickle, copy.copy and copy.deepcopy
        raise TypeError("authorization receipts cannot be copied or serialised")


def _str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def mint_simulation_receipt(policy: Any, *, resource: Mapping[str, Any], manifest_hash: str,
                            scenario_hash: str, now: datetime | None = None) -> AuthorizationReceipt:
    """Mint a receipt only for an exact BoundPolicy whose decision for this exact resource is allow.

    resource is the same simulation_input resource the policy decides on (project_id, import_id, binding_id,
    sensitivity, purpose, retention); the receipt binds its project, import and binding plus the hashes."""
    if not is_principal_bound(policy) or policy.principal is None:
        raise IdentityError("a receipt needs a Principal-bound policy")
    if not isinstance(resource, Mapping):
        raise IdentityError("resource must be a mapping")
    scope = {"project_id": resource.get("project_id"), "import_id": resource.get("import_id"),
             "binding_id": resource.get("binding_id"), "manifest_hash": manifest_hash,
             "scenario_hash": scenario_hash}
    if not all(_str(v) for v in scope.values()):
        raise IdentityError("receipt scope fields must be non-empty strings")
    principal = policy.principal
    decision, role = decide_principal(
        principal, "simulation_input", resource, now=policy._now,
        required_role=policy._required_role, trusted_issuers=policy._trusted_issuers)
    if decision.get("decision") != "allow" or role is None:
        raise IdentityError("policy did not allow this simulation input")
    return AuthorizationReceipt(_MINT, issuer=principal.issuer, subject_id=principal.subject_id, role=role,
                                expires_at=principal.expires_at, **scope)


def verify_simulation_receipt(receipt: Any, *, now: datetime | None = None,
                              trusted_issuers: frozenset[str] = frozenset({SyntheticFixtureAdapter.ISSUER}),
                              **expected: str) -> AuthorizationReceipt:
    """Fail closed (IdentityError) unless receipt is a genuine, unexpired, trusted, exactly-scoped receipt."""
    if type(receipt) is not AuthorizationReceipt or getattr(receipt, "_token", None) is not _MINT:
        raise IdentityError("authorization receipt missing or not genuine")
    if set(expected) != set(_SCOPE_FIELDS):
        raise IdentityError("receipt verification needs the full scope")
    if _utc(now or datetime.now(timezone.utc), "now") >= receipt.expires_at:
        raise IdentityError("authorization receipt expired")
    if receipt.issuer not in trusted_issuers:
        raise IdentityError("authorization receipt issuer untrusted")
    for name in _SCOPE_FIELDS:
        if not _str(expected[name]) or getattr(receipt, name) != expected[name]:
            raise IdentityError(f"authorization receipt scope mismatch: {name}")
    return receipt


__all__ = ["AuthorizationReceipt", "mint_simulation_receipt", "verify_simulation_receipt", "principal_policy", "BoundPolicy", "is_principal_bound", "Assurance",
           "IdentityError", "Principal", "SyntheticFixtureAdapter", "decide_principal"]

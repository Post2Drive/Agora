"""Permission boundary for human decision-record approval."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from datetime import datetime

from agora.policy import decide
from agora.principal import Principal, decide_principal


class DecisionPermissionError(PermissionError):
    """Raised when the central policy decision point denies approval."""

    def __init__(self, decision: dict[str, Any]):
        self.decision = dict(decision)
        super().__init__(f"decision approval denied: {decision.get('reason', 'policy_denied')}")


def authorize_decision_approval(
    subject: Mapping[str, Any],
    role: str,
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the shared policy decision point for an approval operation."""
    decision = decide(subject, role, "decision_approval", resource)
    if decision.get("decision") != "allow":
        raise DecisionPermissionError(decision)
    return decision


def authorize_decision_approval_principal(
    principal: Principal | None,
    resource: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """Principal-native approval gate: authority comes only from the principal.

    Requires the ``approver`` role specifically (a principal holding other roles
    cannot approve). Raises DecisionPermissionError with the audit-safe denial.
    Returns (decision, role).
    """
    decision, role = decide_principal(
        principal, "decision_approval", resource, now=now, required_role="approver",
    )
    if role is None or decision.get("decision") != "allow":
        raise DecisionPermissionError(decision)
    return decision, role


__all__ = [
    "DecisionPermissionError", "authorize_decision_approval",
    "authorize_decision_approval_principal",
]

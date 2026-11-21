"""Permission boundary for human decision-record approval."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agora.policy import decide


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


__all__ = ["DecisionPermissionError", "authorize_decision_approval"]

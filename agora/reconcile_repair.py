"""Reviewed, idempotent repair of MISSING decision audit events.

The detector (agora.reconcile) is read-only. This module is the only writer. It
repairs one class of gap: a stored, source-valid decision transition whose audit
event is missing (for example after a crash between the decision write and the
audit write). It refuses to touch conflicts, invalid sources and orphans, never
edits or deletes any record, and appends only through an anchored writer.

Safety contract (docs/RECONCILIATION_SPEC.md):
- Principal-bound authorization (operation ``reconciliation_repair``, approver only).
- The anchor must verify cleanly, and the caller must pass the exact audit head
  it reviewed; a stale plan is refused.
- Any non-repairable finding blocks the whole run (fail closed, nothing written).
- Deterministic event ids make a replay a no-op (idempotent).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .audit_anchor import AnchoredAuditChain, require_anchored, verify_anchored
from .principal import Principal, decide_principal
from .reconcile import ReconcileBlocked, reconcile


class RepairRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def repair_id(decision_id: str, version: int, transition: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{decision_id}|{version}|{transition}|{fingerprint}".encode()).hexdigest()
    return f"reconcile-{digest[:32]}"


def _audit_head(audit: AnchoredAuditChain) -> str:
    return verify_anchored(audit.chain, audit.anchors).get("head_hash", "")


def apply_repairs(
    decisions_db: str | Path, audit: AnchoredAuditChain, *,
    principal: Principal | None, project_id: str, expected_audit_head: str,
) -> dict[str, Any]:
    """Append the missing audit events; returns {"repaired": n, "repair_ids": [...]}."""
    require_anchored(audit)
    resource = {"project_id": project_id, "source_sensitivity": "internal",
                "resource_ids": ["reconciliation"]}
    decision, role = decide_principal(principal, "reconciliation_repair", resource)
    if role is None:
        raise RepairRefused(f"NOT_AUTHORIZED:{decision.get('reason', 'denied')}")

    state = verify_anchored(audit.chain, audit.anchors)
    if not state["valid"]:
        raise RepairRefused(f"ANCHOR_NOT_CLEAN:{state['status']}")
    if state["head_hash"] != expected_audit_head:
        raise RepairRefused("STALE_AUDIT_HEAD")

    try:
        report = reconcile(decisions_db, audit.chain.path)
    except ReconcileBlocked as exc:
        raise RepairRefused(f"RECONCILE_BLOCKED:{exc.code}") from exc
    blockers = [f for f in report["findings"] if f["status"] != "missing"]
    if blockers:
        raise RepairRefused("NON_REPAIRABLE_FINDINGS")  # conflicts / invalid sources / orphans: human review

    import sqlite3
    from contextlib import closing
    rows = {}
    with closing(sqlite3.connect(f"file:{Path(decisions_db).resolve().as_posix()}?mode=ro", uri=True)) as src:
        for did, ver, trans, actor, fp in src.execute(
                "SELECT decision_id,version,transition,actor,decision_fingerprint FROM decision_approval_events"):
            rows[(did, ver, trans)] = (actor, fp)

    ids: list[str] = []
    for finding in report["findings"]:
        key = (finding["decision_id"], finding["version"], finding["transition"])
        actor, fp = rows[key]
        rid = repair_id(*key, fp)
        audit.append({
            "event_id": rid,
            "event_type": f"decision_{key[2]}",
            "subject_id": actor,
            "operation": "decision_approval" if key[2] == "approved" else "decision_lifecycle",
            "decision": "allow",
            "resource_ids": [key[0], f"version-{key[1]}"],
            "decision_fingerprint": fp,
            "reason": "reconciled_from_store",
        })
        ids.append(rid)
    return {"repaired": len(ids), "repair_ids": ids}


__all__ = ["RepairRefused", "apply_repairs", "repair_id"]

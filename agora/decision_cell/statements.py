"""The recorded list of statements an event item makes (DECISION_CELL_SPEC 2A and 3A).

Without this list the gate cannot know that an item has statements to label, nor that one was left out. The
trusted service registers each statement's id and wording. Registrations are versions in the anchored audit
chain: a later version must keep every earlier statement with the same wording and add at least one, so a
statement cannot be dropped or reworded under its id. A corrected wording is a new statement.

Once an item has a list:

* a choice that decides on the evidence is blocked unless the gate was given the labels
  (``request_labelled_option``, or ``respond_to_item`` with ``statements``);
* the labelled path accepts only exactly the listed statements.

``open_response_window`` refuses an item without a list, so every item windowed from then on is covered.

Trust boundary. Registration takes no principal: it is the service's record of what it ingested, like
opening a response window. Nothing here checks the list against any source, so a statement missing from the
first version stays unseen until it is added, and an item that was never registered can still be decided
without labels. The chain keeps a hash of each wording, not the wording. Event intake is not built.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from agora.audit_anchor import AnchoredAuditChain, AnchorWriteError, verify_anchored
from agora.audit_chain import AuditReplayError
from agora.decision_cell.options import DecisionCellError, statement_set_event_id
from agora.decision_cell.project_store import _canonical, _hash, _identifier, _writer
from agora.policy import POLICY_VERSION

MAX_STATEMENTS = 100
_EVENT_TYPE = "decision_cell_item_statements"
_SYSTEM = "system:decision-cell"
_TAG = "statement:"


class StatementSetError(DecisionCellError):
    """A refused or untrustworthy statement-list operation. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ItemStatements:
    tenant_id: str
    project_id: str
    study_id: str
    item_id: str
    version: int
    # (statement id, hash of its wording), ordered by statement id.
    statements: tuple[tuple[str, str], ...]


def wording_hash(statement_text: str) -> str:
    return _hash(_canonical(statement_text))


def _text(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def load_item_statements(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                         audit: AnchoredAuditChain) -> ItemStatements | None:
    """The latest list, or None if the item was never registered. A trusted service-side read."""
    writer = _writer(audit)
    key = (tenant_id, project_id, study_id, item_id)
    if not all(_identifier(v) for v in key):
        raise StatementSetError("ID_INVALID", "ids must be exact non-empty strings")
    try:
        with writer.anchors.lock():
            state = verify_anchored(writer.chain, writer.anchors)
            if not state["valid"]:
                raise StatementSetError("AUDIT_UNANCHORED", state["status"])
            rows = []
            while True:
                row = writer.chain.db.execute(
                    "SELECT event_json FROM audit_events WHERE event_id=?",
                    (statement_set_event_id(*key, len(rows) + 1),)).fetchone()
                if row is None:
                    break
                rows.append(row[0])
        listed: dict[str, str] = {}
        for version, raw in enumerate(rows, 1):
            event = json.loads(raw)
            if event.get("event_type") != _EVENT_TYPE or event.get("sequence") != version:
                raise StatementSetError("STORE_INCONSISTENT", "a list version does not match its id")
            current: dict[str, str] = {}
            for value in event["resource_ids"]:
                if value.startswith(_TAG):
                    digest, statement_id = value[len(_TAG):].split(":", 1)
                    current[statement_id] = digest
            if len(current) <= len(listed) or not listed.items() <= current.items():
                raise StatementSetError("STORE_INCONSISTENT", "a list version dropped or changed a statement")
            listed = current
    except StatementSetError:
        raise
    except Exception as exc:
        raise StatementSetError("STORE_ERROR", "the statement list could not be read") from exc
    if not rows:
        return None
    return ItemStatements(*key, len(rows), tuple(sorted(listed.items())))


def register_item_statements(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                             statements: Mapping[str, str], expected_version: int,
                             audit: AnchoredAuditChain) -> ItemStatements:
    """Record the item's full statement list, id to wording, as the next version.

    ``expected_version`` is 0 to create, else the version being extended. Raises ``StatementSetError``;
    nothing was recorded unless the code is ``AUDIT_ANCHOR_WRITE_FAILED``.
    """
    writer = _writer(audit)
    if not isinstance(statements, Mapping) or not 1 <= len(statements) <= MAX_STATEMENTS \
            or not all(_identifier(i) and _text(t) for i, t in statements.items()):
        raise StatementSetError(
            "STATEMENTS_INVALID", f"give 1 to {MAX_STATEMENTS} exact statement ids, each with its wording")
    key = (tenant_id, project_id, study_id, item_id)
    current = load_item_statements(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                                   item_id=item_id, audit=writer)
    version = current.version if current else 0
    if type(expected_version) is not int or expected_version != version:
        raise StatementSetError("VERSION_CONFLICT", "the list changed or does not exist at that version")
    listed = {i: wording_hash(t) for i, t in statements.items()}
    if current:
        earlier = dict(current.statements)
        if not earlier.items() <= listed.items():
            raise StatementSetError("STATEMENT_REMOVED", "keep every listed statement with its wording")
        if len(listed) == len(earlier):
            raise StatementSetError("NOTHING_ADDED", "the new version adds no statement")
    event = {
        "event_id": statement_set_event_id(*key, version + 1), "event_type": _EVENT_TYPE,
        "subject_id": _SYSTEM, "operation": "register_item_statements", "decision": "allow",
        "policy_version": POLICY_VERSION, "sequence": version + 1, "count": len(listed),
        "resource_ids": [f"tenant:{tenant_id}", f"project:{project_id}", f"study:{study_id}",
                         f"item:{item_id}"] + [f"{_TAG}{d}:{i}" for i, d in sorted(listed.items())],
    }
    try:
        writer.append(event)
    except AuditReplayError as exc:
        # Another writer recorded this version first; ours was checked against the one before it.
        raise StatementSetError("VERSION_CONFLICT", "this version was written concurrently") from exc
    except AnchorWriteError as exc:
        raise StatementSetError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; reconcile first") from exc
    except Exception as exc:
        raise StatementSetError("AUDIT_FAILED", "the list could not be recorded") from exc
    return ItemStatements(*key, version + 1, tuple(sorted(listed.items())))


def require_no_newer_list(db: sqlite3.Connection, listed: ItemStatements) -> None:
    """Inside an append transaction: refuse if the item gained statements since the list was read."""
    newer = statement_set_event_id(listed.tenant_id, listed.project_id, listed.study_id, listed.item_id,
                                   listed.version + 1)
    if db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (newer,)).fetchone():
        raise StatementSetError("STATEMENTS_CHANGED", "the item gained statements; read it again")


__all__ = ["ItemStatements", "MAX_STATEMENTS", "StatementSetError", "load_item_statements",
           "register_item_statements", "require_no_newer_list", "wording_hash"]

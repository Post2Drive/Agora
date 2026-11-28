"""The recorded list of statements an event item makes (DECISION_CELL_SPEC 2A and 3A).

Without this list the gate cannot know that an item has statements to label, nor that one was left out. The
trusted service registers each statement's id and wording. Registrations are versions in the anchored audit
chain: a later version must keep every earlier statement with the same wording and add a statement or raise a
rating, so a statement cannot be dropped or reworded under its id. A corrected wording is a new statement.

Each statement is registered with a rating: its sensitivity and, from ``personal`` up, its data owner. The
gate takes both from here for any run that would add the statement. A later version may raise a rating or name
an owner where none was recorded; it may not lower a rating or replace an owner. Lists recorded before ratings
existed still load, and no run may add an unrated statement.

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
from agora.policy import POLICY_VERSION, SENSITIVITY_RANK

MAX_STATEMENTS = 100
_EVENT_TYPE = "decision_cell_item_statements"
_SYSTEM = "system:decision-cell"
_TAG = "statement:"
_RATING_TAG = "rating:"


def statement_input_id(item_id: str, statement_id: str) -> str:
    """The ``InputRef.input_id`` of one statement of one item, for CHANGE_INPUTS and data-owner grants."""
    if not (_identifier(item_id) and _identifier(statement_id)):
        raise StatementSetError("INPUT_INVALID", "ids must be exact non-empty strings")
    return "statement:" + _canonical([item_id, statement_id])


class StatementSetError(DecisionCellError):
    """A refused or untrustworthy statement-list operation. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class StatementRating:
    """How sensitive one statement is, and whose data it is."""
    sensitivity: str
    data_owner_subject_id: str | None = None


def _valid_rating(sensitivity: object, owner: object) -> bool:
    if not isinstance(sensitivity, str) or sensitivity not in SENSITIVITY_RANK:
        return False
    if owner is None:
        return SENSITIVITY_RANK[sensitivity] < SENSITIVITY_RANK["personal"]
    return _identifier(owner)


def _rating_conflict(earlier: Mapping[str, StatementRating], later: Mapping[str, StatementRating]) -> str | None:
    """Why ``later`` may not replace ``earlier``, as an error code, or None if it may."""
    for statement_id, old in earlier.items():
        new = later.get(statement_id)
        if new is None or SENSITIVITY_RANK[new.sensitivity] < SENSITIVITY_RANK[old.sensitivity]:
            return "RATING_LOWERED"
        if old.data_owner_subject_id is not None and new.data_owner_subject_id != old.data_owner_subject_id:
            return "DATA_OWNER_CHANGED"
    return None


@dataclass(frozen=True)
class ItemStatements:
    tenant_id: str
    project_id: str
    study_id: str
    item_id: str
    version: int
    # (statement id, hash of its wording), ordered by statement id.
    statements: tuple[tuple[str, str], ...]
    # (statement id, rating), ordered by statement id. A statement missing here was recorded unrated.
    ratings: tuple[tuple[str, StatementRating], ...] = ()


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
        rated: dict[str, StatementRating] = {}
        for version, raw in enumerate(rows, 1):
            event = json.loads(raw)
            if event.get("event_type") != _EVENT_TYPE or event.get("sequence") != version:
                raise StatementSetError("STORE_INCONSISTENT", "a list version does not match its id")
            current: dict[str, str] = {}
            ratings: dict[str, StatementRating] = {}
            for value in event["resource_ids"]:
                if value.startswith(_TAG):
                    digest, statement_id = value[len(_TAG):].split(":", 1)
                    current[statement_id] = digest
                elif value.startswith(_RATING_TAG):
                    statement_id, sensitivity, owner = json.loads(value[len(_RATING_TAG):])
                    if statement_id in ratings or not _valid_rating(sensitivity, owner):
                        raise StatementSetError("STORE_INCONSISTENT", "a list version holds a bad rating")
                    ratings[statement_id] = StatementRating(sensitivity, owner)
            if not listed.items() <= current.items() or (current == listed and ratings == rated):
                raise StatementSetError("STORE_INCONSISTENT", "a list version dropped or reworded a statement, or changed nothing")
            if not ratings.keys() <= current.keys() or _rating_conflict(rated, ratings):
                raise StatementSetError("STORE_INCONSISTENT", "a list version weakened or misplaced a rating")
            listed, rated = current, ratings
    except StatementSetError:
        raise
    except Exception as exc:
        raise StatementSetError("STORE_ERROR", "the statement list could not be read") from exc
    if not rows:
        return None
    return ItemStatements(*key, len(rows), tuple(sorted(listed.items())), tuple(sorted(rated.items())))


def register_item_statements(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                             statements: Mapping[str, str], ratings: Mapping[str, StatementRating],
                             expected_version: int, audit: AnchoredAuditChain) -> ItemStatements:
    """Record the item's full statement list, id to wording and id to rating, as the next version.

    ``expected_version`` is 0 to create, else the version being extended. Raises ``StatementSetError``;
    nothing was recorded unless the code is ``AUDIT_ANCHOR_WRITE_FAILED``.
    """
    writer = _writer(audit)
    if not isinstance(statements, Mapping) or not 1 <= len(statements) <= MAX_STATEMENTS \
            or not all(_identifier(i) and _text(t) for i, t in statements.items()):
        raise StatementSetError(
            "STATEMENTS_INVALID", f"give 1 to {MAX_STATEMENTS} exact statement ids, each with its wording")
    if not isinstance(ratings, Mapping) or set(ratings) != set(statements) or not all(
            isinstance(r, StatementRating) and _valid_rating(r.sensitivity, r.data_owner_subject_id)
            for r in ratings.values()):
        raise StatementSetError(
            "RATINGS_INVALID", "rate every statement; personal and sensitive ones need a data owner")
    rated = dict(ratings)
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
        conflict = _rating_conflict(dict(current.ratings), rated)
        if conflict:
            raise StatementSetError(conflict, "a recorded rating may only be raised and its owner kept")
        if listed == earlier and rated == dict(current.ratings):
            raise StatementSetError("NOTHING_ADDED", "the new version adds no statement and raises no rating")
    event = {
        "event_id": statement_set_event_id(*key, version + 1), "event_type": _EVENT_TYPE,
        "subject_id": _SYSTEM, "operation": "register_item_statements", "decision": "allow",
        "policy_version": POLICY_VERSION, "sequence": version + 1, "count": len(listed),
        "resource_ids": [f"tenant:{tenant_id}", f"project:{project_id}", f"study:{study_id}",
                         f"item:{item_id}"] + [f"{_TAG}{d}:{i}" for i, d in sorted(listed.items())]
        + [_RATING_TAG + _canonical([i, r.sensitivity, r.data_owner_subject_id]) for i, r in sorted(rated.items())],
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
    return ItemStatements(*key, version + 1, tuple(sorted(listed.items())), tuple(sorted(rated.items())))


def require_no_newer_list(db: sqlite3.Connection, listed: ItemStatements) -> None:
    """Inside an append transaction: refuse if the list or a rating changed since it was read."""
    newer = statement_set_event_id(listed.tenant_id, listed.project_id, listed.study_id, listed.item_id,
                                   listed.version + 1)
    if db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (newer,)).fetchone():
        raise StatementSetError("STATEMENTS_CHANGED", "the item's statement list changed; read it again")


__all__ = ["ItemStatements", "MAX_STATEMENTS", "StatementRating", "StatementSetError",
           "load_item_statements", "register_item_statements", "require_no_newer_list", "statement_input_id",
           "wording_hash"]

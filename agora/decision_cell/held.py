"""Which recorded statements a source study already holds, and their ratings (DECISION_CELL_SPEC 3A).

A run started from a snapshot carries every event added up to that round. ``trace_held_statements`` traces
each one to a recorded statement, so the gate can ask for the data owner's grant again.

Rules chosen here:

* An added event is traced only if it is exactly what a run here adds (``type`` news, ``text``, ``round``),
  its text is the recorded wording of a statement, and at least one such statement belongs to an item in
  the basis of a parent result the caller named. Otherwise nothing is established and the run is refused.
* The source records text, not statement ids. So every recorded statement of the study with that wording is
  judged, whichever item it belongs to: the strictest rating then applies, and naming a parent whose item
  rates the same words lower removes no grant.
* The ratings in force now are used, not those in force when the source ran.
* A statement list recorded or changed in the study after the read blocks the commit of the gate's entry.

Limits. Matching is by exact wording. An event reworded after it was added is refused as untraced, but
nothing here sees data that reached the source any other way (its scenario, population or knowledge graph),
and nothing proves the source was produced by the named parent.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from agora.audit_anchor import AnchoredAuditChain
from agora.decision_cell.options import InputRef
from agora.decision_cell.retractions import _rows, _scope
from agora.decision_cell.run_results import load_run_result
from agora.decision_cell.statements import (
    ItemStatements, StatementSetError, load_item_statements, statement_input_id, wording_hash,
)

_LIST_PREFIX = "dc-item-statements-"
_LISTS_AFTER = ("SELECT seq, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? AND seq>? "
                "ORDER BY seq")
_ADDED_KEYS = {"type", "text", "round"}


@dataclass(frozen=True)
class HeldStatements:
    """The recorded statements a source holds, each as the gate judges it, and what was read to find them."""
    tenant_id: str
    project_id: str
    study_id: str
    inputs: tuple[InputRef, ...]            # ordered by input id; an unrated one has an empty sensitivity
    read_through: int                       # audit sequence of the newest statement list that was seen


def _item_of(raw: str, scope: list[str]) -> str | None:
    """The item a statement-list entry belongs to, or None if the entry is another study's."""
    try:
        resources = json.loads(raw)["resource_ids"]
        if resources[:3] != scope:
            return None
        if not resources[3].startswith("item:"):
            raise ValueError("no item")
        return resources[3][len("item:"):]
    except Exception as exc:
        raise StatementSetError("STORE_INCONSISTENT", "a statement-list entry is not usable") from exc


def _study_lists(tenant_id: str, project_id: str, study_id: str,
                 audit: AnchoredAuditChain) -> tuple[list[ItemStatements], int]:
    scope = _scope(tenant_id, project_id, study_id)
    rows = _rows(audit, _LISTS_AFTER, (len(_LIST_PREFIX), _LIST_PREFIX, 0))
    items = {_item_of(raw, scope) for _, raw in rows} - {None}
    lists = [load_item_statements(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                                  item_id=item_id, audit=audit) for item_id in sorted(items)]
    if any(listed is None for listed in lists):
        raise StatementSetError("STORE_INCONSISTENT", "a statement list is missing its first version")
    return lists, rows[-1][0] if rows else 0


def _wording_of(round_number: object, raw: object) -> str | None:
    """The hash of the text of an event shaped like one a run here adds, or None."""
    try:
        event = json.loads(raw)
        if set(event) != _ADDED_KEYS or event["type"] != "news" or event["round"] != round_number \
                or not isinstance(event["text"], str):
            return None
        return wording_hash(event["text"])
    except Exception:
        return None


def trace_held_statements(*, tenant_id: str, project_id: str, study_id: str,
                          added_events: tuple[tuple[int, str], ...], parent_result_ids: tuple[str, ...],
                          audit: AnchoredAuditChain) -> HeldStatements | None:
    """The statements behind ``added_events`` (round, event JSON), or None if any one cannot be traced.

    A trusted service-side read. Raises if the audit chain or a statement list cannot be trusted.
    """
    key = dict(tenant_id=tenant_id, project_id=project_id, study_id=study_id)
    lists, read_through = _study_lists(audit=audit, **key)
    parent_items: set[str] = set()
    for parent_id in parent_result_ids:
        parent = load_run_result(result_id=parent_id, audit=audit, **key)
        if parent is None:
            return None
        parent_items.update(parent.item_ids)
    found: dict[str, InputRef] = {}
    for round_number, raw in added_events:
        digest = _wording_of(round_number, raw)
        matches = [(listed, statement_id) for listed in lists
                   for statement_id, recorded in listed.statements if recorded == digest]
        if not any(listed.item_id in parent_items for listed, _ in matches):
            return None
        for listed, statement_id in matches:
            rating = dict(listed.ratings).get(statement_id)
            input_id = statement_input_id(listed.item_id, statement_id)
            found[input_id] = InputRef(input_id, rating.sensitivity if rating else "",
                                       rating.data_owner_subject_id if rating else None)
    return HeldStatements(inputs=tuple(found[i] for i in sorted(found)), read_through=read_through, **key)


def require_no_newer_lists(db: sqlite3.Connection, held: HeldStatements) -> None:
    """Inside an append transaction: refuse if any statement list of the study was recorded since the read."""
    scope = _scope(held.tenant_id, held.project_id, held.study_id)
    for _, raw in db.execute(_LISTS_AFTER, (len(_LIST_PREFIX), _LIST_PREFIX, held.read_through)):
        if _item_of(raw, scope) is not None:
            raise StatementSetError("STATEMENTS_CHANGED", "a statement list in the study changed; submit again")


__all__ = ["HeldStatements", "require_no_newer_lists", "trace_held_statements"]

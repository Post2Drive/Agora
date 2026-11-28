"""Which event items each run result rests on (DECISION_CELL_SPEC 2A, "stamped in every result and report").

``retraction_stamps`` stamps only the items a caller names. This module records those items once, when a
result is produced, in the anchored audit chain, so that a later reader names only the result.

Rules chosen here:

* A result is recorded against one allowed run choice (``decision_cell_option``, a run option or
  CHANGE_INPUTS) that carries the item's labels. That item is always in the basis; it cannot be left out.
* The caller adds the other items the result used and names the parent results whose evidence it carries.
  A parent's whole recorded basis is copied into the child, so an item cannot be lost along a chain of
  results. A parent must already be recorded in the same study, which rules out cycles.
* Every item in a basis needs a recorded statement list, so a mistyped id is refused, not silently never
  stamped.
* A result is recorded once. Its basis is never changed or withdrawn.
* Stamps are worked out when read, so a retraction recorded after the result still stamps it.

Where the item cannot be told apart, this stamps rather than clears: a fork's without-event branch, or a
CHANGE_INPUTS run that left the choice's own item out, still has that item in its basis. A rerun that should
carry no stamp has to come from a choice on another item and not name a parent that used the retracted one.

Limits. Recording takes no principal: it is the trusted service's record of what it ran, like a statement
list. Nothing here checks that a run happened, that ``result_hash`` is the hash of its output, or that the
other items and parents named are all it used: an omitted one is never stamped. The gate keeps only hashes
of CHANGE_INPUTS inputs, so they cannot be checked either. A result nobody records is not listed, and an
unrecorded result id is refused rather than reported as unstamped. Only ``executor`` (FORK_FROM_EVENT) calls
this module; no engine, report or screen does. Reads perform no caller permission check.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from agora.audit_anchor import AnchoredAuditChain, AnchorWriteError
from agora.audit_chain import AuditReplayError
from agora.decision_cell.options import statement_set_event_id
from agora.decision_cell.project_store import _canonical, _hash, _identifier, _writer
from agora.decision_cell.retractions import (
    _RUN_OPERATIONS,
    CorrectionError,
    _rows,
    _scope,
    retraction_stamps,
)
from agora.policy import POLICY_VERSION

MAX_BASIS_ITEMS = 200
MAX_PARENTS = 20
_PREFIX = "dc-run-result-"
_GATE_PREFIX = "decision-cell-"
_EVENT_TYPE = "decision_cell_run_result"
_SYSTEM = "system:decision-cell"
_HEX = frozenset("0123456789abcdef")


class RunResultError(CorrectionError):
    """A refused or untrustworthy run-result operation. ``code`` is stable and safe to log.

    A chain that cannot be read or is not cleanly anchored raises the parent ``CorrectionError``; catch that.
    """


@dataclass(frozen=True)
class RunResultBasis:
    tenant_id: str
    project_id: str
    study_id: str
    result_id: str
    gate_event_id: str                      # the allowed run choice this result came from
    result_hash: str                        # as the service gave it; not checked against any output
    parent_result_ids: tuple[str, ...]
    item_ids: tuple[str, ...]               # every item it rests on, parents' included, ordered by id
    audit_sequence: int


def _event_id(tenant_id: str, project_id: str, study_id: str, result_id: str) -> str:
    return _PREFIX + _hash(_canonical([tenant_id, project_id, study_id, result_id]))


def _check_ids(*values: object) -> None:
    if not all(_identifier(v) for v in values):
        raise RunResultError("ID_INVALID", "ids must be exact non-empty strings")


def _tagged(resources: list[str], tag: str) -> tuple[str, ...]:
    return tuple(v[len(tag):] for v in resources if v.startswith(tag))


def _parse(tenant_id: str, project_id: str, study_id: str, audit_sequence: int, event_id: str,
           raw: str) -> RunResultBasis:
    try:
        event = json.loads(raw)
        resources = event["resource_ids"]
        (result_id,) = _tagged(resources, "result:")
        (gate_event_id,) = _tagged(resources, "gate:")
        items = _tagged(resources, "basis:")
        if (event["event_type"] != _EVENT_TYPE or event["decision"] != "allow"
                or resources[:3] != _scope(tenant_id, project_id, study_id)
                or event_id != _event_id(tenant_id, project_id, study_id, result_id)
                or not items or event["count"] != len(items)):
            raise ValueError("a result record does not match its id")
        return RunResultBasis(tenant_id, project_id, study_id, result_id, gate_event_id, event["result_hash"],
                              _tagged(resources, "parent:"), items, audit_sequence)
    except Exception as exc:
        raise RunResultError("STORE_INCONSISTENT", "a run-result record is not usable") from exc


def load_run_result(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                    audit: AnchoredAuditChain) -> RunResultBasis | None:
    """The recorded basis of one result, or None if it was never recorded. A trusted service-side read."""
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, result_id)
    event_id = _event_id(tenant_id, project_id, study_id, result_id)
    rows = _rows(writer, "SELECT seq, event_json FROM audit_events WHERE event_id=?", (event_id,))
    if not rows:
        return None
    return _parse(tenant_id, project_id, study_id, rows[0][0], event_id, rows[0][1])


def _gate_item(writer: AnchoredAuditChain, scope: list[str], gate_event_id: str) -> str:
    """The item of an allowed, labelled run choice in this study."""
    rows = _rows(writer, "SELECT event_json FROM audit_events WHERE event_id=?", (gate_event_id,))
    if not gate_event_id.startswith(_GATE_PREFIX) or not rows:
        raise RunResultError("GATE_PASS_NOT_FOUND", "name the audit entry of the run choice")
    try:
        event = json.loads(rows[0][0])
        if event["event_type"] != "decision_cell_option" or event["operation"] not in _RUN_OPERATIONS:
            raise RunResultError("NOT_A_RUN_CHOICE", "only a run choice can have a result")
        if event["decision"] != "allow":
            raise RunResultError("GATE_PASS_BLOCKED", "the gate blocked that choice")
        resources = event.get("resource_ids", [])
        if len(resources) < 4 or not resources[3].startswith("item:"):
            raise RunResultError("GATE_PASS_UNLABELLED", "the choice was not made with the item's labels")
        if resources[:3] != scope:
            raise RunResultError("GATE_PASS_OTHER_STUDY", "the choice belongs to another study")
        return resources[3][len("item:"):]
    except RunResultError:
        raise
    except Exception as exc:
        raise RunResultError("STORE_INCONSISTENT", "the gate entry is not usable") from exc


def record_run_result(*, tenant_id: str, project_id: str, study_id: str, result_id: str, gate_event_id: str,
                      result_hash: str, audit: AnchoredAuditChain, other_item_ids: tuple[str, ...] = (),
                      parent_result_ids: tuple[str, ...] = ()) -> RunResultBasis:
    """Record, once, what a run result rests on.

    Raises ``RunResultError``; nothing was recorded unless the code is ``AUDIT_ANCHOR_WRITE_FAILED``.
    """
    writer = _writer(audit)
    if not isinstance(other_item_ids, tuple) or not isinstance(parent_result_ids, tuple):
        raise RunResultError("BASIS_INVALID", "give the other items and the parent results as tuples")
    _check_ids(tenant_id, project_id, study_id, result_id, gate_event_id, *other_item_ids, *parent_result_ids)
    if not isinstance(result_hash, str) or len(result_hash) != 64 or not _HEX.issuperset(result_hash):
        raise RunResultError("RESULT_HASH_INVALID", "give the result's SHA-256 as 64 lowercase hex digits")
    parents = tuple(sorted(set(parent_result_ids)))
    if len(parents) > MAX_PARENTS:
        raise RunResultError("BASIS_TOO_LARGE", f"at most {MAX_PARENTS} parent results")
    scope = _scope(tenant_id, project_id, study_id)
    items = {_gate_item(writer, scope, gate_event_id), *other_item_ids}
    for parent_id in parents:
        parent = load_run_result(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                                 result_id=parent_id, audit=writer)
        if parent is None:
            raise RunResultError("PARENT_NOT_RECORDED", "record the parent result first")
        items.update(parent.item_ids)
    if len(items) > MAX_BASIS_ITEMS:
        raise RunResultError("BASIS_TOO_LARGE", f"at most {MAX_BASIS_ITEMS} items; none is dropped to fit")
    for item_id in sorted(items):
        listed = statement_set_event_id(tenant_id, project_id, study_id, item_id, 1)
        if not _rows(writer, "SELECT 1 FROM audit_events WHERE event_id=?", (listed,)):
            raise RunResultError("ITEM_NOT_REGISTERED", "every item in the basis needs a recorded statement list")
    event = {
        "event_id": _event_id(tenant_id, project_id, study_id, result_id), "event_type": _EVENT_TYPE,
        "subject_id": _SYSTEM, "operation": "record_run_result", "decision": "allow",
        "policy_version": POLICY_VERSION, "count": len(items), "result_hash": result_hash,
        "resource_ids": scope + [f"result:{result_id}", f"gate:{gate_event_id}"]
        + [f"parent:{p}" for p in parents] + [f"basis:{i}" for i in sorted(items)],
    }
    try:
        writer.append(event)
    except AuditReplayError as exc:
        raise RunResultError("RESULT_ALREADY_RECORDED", "a result's basis is recorded once") from exc
    except AnchorWriteError as exc:
        raise RunResultError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; reconcile first") from exc
    except Exception as exc:
        raise RunResultError("AUDIT_FAILED", "the result could not be recorded") from exc
    return load_run_result(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                           result_id=result_id, audit=writer)


def run_result_stamps(*, tenant_id: str, project_id: str, study_id: str, result_id: str,
                      audit: AnchoredAuditChain) -> tuple[tuple[str, str], ...]:
    """``retraction_stamps`` over everything the recorded result rests on. Whoever shows it must show these.

    An unrecorded result raises: its items are unknown, which is not the same as nothing retracted.
    """
    basis = load_run_result(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                            result_id=result_id, audit=audit)
    if basis is None:
        raise RunResultError("RESULT_NOT_RECORDED", "what this result rests on is not recorded")
    return retraction_stamps(tenant_id=tenant_id, project_id=project_id, study_id=study_id,
                             item_ids=basis.item_ids, audit=audit)


def run_results_resting_on(*, tenant_id: str, project_id: str, study_id: str, item_id: str,
                           audit: AnchoredAuditChain) -> tuple[RunResultBasis, ...]:
    """The recorded results whose basis includes this item, in the order recorded.

    These are the recorded results a retraction of the item affects. An empty answer does not show that no
    run used it: unrecorded results and unnamed items are not seen.
    """
    writer = _writer(audit)
    _check_ids(tenant_id, project_id, study_id, item_id)
    rows = _rows(writer, "SELECT seq, event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? "
                         "ORDER BY seq", (len(_PREFIX), _PREFIX))
    scope = _scope(tenant_id, project_id, study_id)
    found = []
    for sequence, event_id, raw in rows:
        try:
            resources = json.loads(raw)["resource_ids"]
            mine = resources[:3] == scope
        except Exception as exc:
            raise RunResultError("STORE_INCONSISTENT", "a run-result record is not usable") from exc
        if mine:
            basis = _parse(tenant_id, project_id, study_id, sequence, event_id, raw)
            if item_id in basis.item_ids:
                found.append(basis)
    return tuple(found)


__all__ = ["MAX_BASIS_ITEMS", "MAX_PARENTS", "RunResultBasis", "RunResultError", "load_run_result",
           "record_run_result", "run_result_stamps", "run_results_resting_on"]

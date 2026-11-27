"""Run the simulation an admission allows, once, and compute the result digest here.

``outcomes.record_simulation_outcome`` takes the caller's word for the result digest. This module
calls the simulator itself, builds a canonical result record that names the proposal, and records
that record's digest as the admission's outcome.

A start event is appended under a fixed ID *before* the simulator is called, so the chain allows one
run per admission, also when two callers race or a process dies. Once it exists, a hand-reported
outcome is refused, and once an outcome exists no run can start. Both are checked while the chain's
write lock is held.

The simulator is ordinary Python supplied by the caller, run in this process. Nothing isolates it:
this module cannot show that it only simulates, that it is the code its ID names, or that it did
nothing else.

Rules and limits: docs/ONTOLOGY_ACTION_PROPOSALS.md.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any

from ..audit_anchor import AnchorWriteError
from ..audit_chain import AuditReplayError
from ..policy_enforcement import PolicyCallable
from . import approvals
from .actions import recheck_action_proposal
from .approvals import _anchored, _approved_at, _fields, _final_id, _principal
from .outcomes import (
    _ALREADY, _OUTCOME, _OUTCOME_PREFIX, _RUN_PREFIX, _STATUSES, _admission, _has_event,
)
from .registry import OntologyError
from .store import OntologyObjectStore

RESULT_FORMAT = "agora.ontology.simulation_result/v1"
# A run must start this soon after its admission. The objects are re-read at the start as well.
RUN_START_WINDOW_SECONDS = 60 * 60
MAX_RESULT_BYTES = 16 * 1024 * 1024
_STARTED_TYPE = "ontology_action_simulation_started"
_SIMULATOR_ID = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}")
_ERROR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_ALREADY_RUN = "a simulation run was already started for this admission"

Simulator = Callable[[dict[str, Any]], Any]


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _same_json(left: Any, right: Any) -> bool:
    """Equal with identical JSON types, so nothing was converted on the way through JSON."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (left.keys() == right.keys() and all(type(k) is str for k in left)
                and all(_same_json(v, right[k]) for k, v in left.items()))
    if type(left) is list:
        return len(left) == len(right) and all(map(_same_json, left, right))
    return left == right


def _record(digest: str, simulator_id: str, status: str, key: str, value: Any) -> str:
    return _canonical({"format": RESULT_FORMAT, "proposal_digest": digest,
                       "simulator_id": simulator_id, "status": status, key: value})


def _simulate(simulator: Simulator, document: str, digest: str, simulator_id: str) -> tuple[str, str]:
    """Call the simulator and return (status, canonical result record).

    An exception, or output that is not exactly JSON or is too large, is a failed run. Only the kind
    of failure is kept: a message could carry source values. A BaseException (interrupt, exit) is
    not caught, which leaves the run started and without an outcome.
    """
    try:
        output = simulator(json.loads(document))
    except Exception as exc:
        name = type(exc).__name__
        failure = {"kind": "simulator_raised",
                   "error_type": name if _ERROR_NAME.fullmatch(name) else "other"}
        return "failed", _record(digest, simulator_id, "failed", "failure", failure)
    try:
        # Serialised once: the record is built from this copy, never from the caller's object again.
        copy = json.loads(_canonical(output))
        if not _same_json(output, copy):
            raise ValueError("not exactly JSON")
        record = _record(digest, simulator_id, "succeeded", "output", copy)
        if len(record.encode("utf-8")) > MAX_RESULT_BYTES:
            raise ValueError("too large")
    except Exception:  # whatever the object does when read, the started run still gets an outcome
        return "failed", _record(digest, simulator_id, "failed", "failure",
                                 {"kind": "unusable_output"})
    return "succeeded", record


def _start_deadline(writer: Any, digest: str) -> datetime:
    return _approved_at(writer.find_event(_final_id(digest))) + timedelta(
        seconds=RUN_START_WINDOW_SECONDS)


def _in_window(deadline: datetime) -> None:
    now = approvals._now()
    if now >= deadline:
        raise OntologyError("the admission is too old to start a simulation run")
    if now < deadline - timedelta(seconds=RUN_START_WINDOW_SECONDS) - approvals._CLOCK_SKEW:
        raise OntologyError("the admission is dated after the current time")


def run_admitted_simulation(
    store: OntologyObjectStore, document: Mapping[str, Any], expected_digest: str,
    *, simulator: Simulator, simulator_id: str,
    policy: PolicyCallable | None, audit: Any | None,
    purpose: str | None = None, retention: str | None = None,
) -> dict[str, str]:
    """Run ``simulator`` once for an admitted action and record the digest of what it returned.

    Needs outcome and read authority, and the identity that admitted the action. The run must start
    within ``RUN_START_WINDOW_SECONDS`` of the admission, and the proposal's objects and sources
    must still match (they are read before the start event is appended, not inside its transaction).

    ``simulator`` receives its own copy of the proposal document and returns a JSON value (objects
    with text keys, arrays, text, finite numbers, booleans, null). ``simulator_id`` is the caller's
    name for it, in lowercase letters, digits and ``_.:-``.

    Returns ``result``, the canonical record text whose SHA-256 is ``result_digest``. The caller
    keeps it; the chain holds only the digest. A simulator that raises, or returns something else,
    gives a recorded ``failed`` outcome. There is no second run, whatever happens after the start.
    """
    if not callable(simulator):
        raise OntologyError("simulator must be callable")
    if not isinstance(simulator_id, str) or not _SIMULATOR_ID.fullmatch(simulator_id):
        raise OntologyError("simulator_id must be 1 to 128 lowercase letters, digits or _.:-")
    fields = _fields(store, document, expected_digest)
    # Taken now: later changes to the caller's mapping do not reach the simulator.
    content = _canonical(document)
    writer = _anchored(audit)
    resource_ids = [fields["pack"], fields["action"], fields["version"], expected_digest]
    decision = store._authorize(
        _OUTCOME, resource_ids, policy=policy, audit=writer, sensitivity=fields["sensitivity"])
    subject = _principal(decision)
    if subject != _admission(writer, fields, expected_digest, resource_ids):
        raise OntologyError("only the identity that admitted the action can run its simulation")
    suffix = expected_digest.split(":", 1)[1]
    run_id, outcome_id = _RUN_PREFIX + suffix, _OUTCOME_PREFIX + suffix
    if writer.find_event(outcome_id) is not None:
        raise OntologyError(_ALREADY)
    if writer.find_event(run_id) is not None:
        raise OntologyError(_ALREADY_RUN)
    deadline = _start_deadline(writer, expected_digest)
    _in_window(deadline)
    recheck_action_proposal(store, json.loads(content), expected_digest, policy=policy,
                            audit=writer, purpose=purpose, retention=retention)

    def may_start(db: Any) -> None:
        if _has_event(db, outcome_id):
            raise OntologyError(_ALREADY)
        _in_window(deadline)

    common = {"operation": _OUTCOME, "decision": "allow", "subject_id": subject,
              "policy_version": str(decision.get("policy_version", "unknown")),
              "resource_ids": resource_ids, "reason": "policy_allow",
              "simulator_id_hash": _hash(simulator_id)}
    try:
        writer.append({"event_id": run_id, "event_type": _STARTED_TYPE, **common},
                      in_transaction=may_start)
    except AuditReplayError as exc:
        raise OntologyError(_ALREADY_RUN) from exc
    except AnchorWriteError as exc:
        raise OntologyError("the run start was appended but not anchored; nothing was run, "
                            "reconcile the audit chain") from exc

    status, result = _simulate(simulator, content, expected_digest, simulator_id)
    result_digest = _hash(result)
    try:
        writer.append({"event_id": outcome_id, "event_type": _STATUSES[status],
                       "result_hash": result_digest, **common})
    except AuditReplayError as exc:
        raise OntologyError(_ALREADY) from exc
    except AnchorWriteError as exc:
        raise OntologyError("the simulation ran and its outcome was appended but not anchored; "
                            "reconcile the audit chain") from exc
    return {"digest": expected_digest, "status": status, "result_digest": result_digest,
            "result": result, "simulator_id": simulator_id, "recorded_by": subject}


__all__ = ["MAX_RESULT_BYTES", "RESULT_FORMAT", "RUN_START_WINDOW_SECONDS",
           "run_admitted_simulation"]

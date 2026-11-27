"""An event item's verification labels, bound into the option gate (DECISION_CELL_SPEC 2A and 3A).

``item_evidence`` reads the label in force for each of an item's statements and hashes the whole view.
``request_labelled_option`` is the gate path that uses it:

* a choice that decides on the evidence (IGNORE and the run options, CHANGE_INPUTS included) must name the
  view the person was shown, and is blocked if the view has changed since;
* the view's hash is part of the action fingerprint, so a second approval given for one view does not cover
  another;
* the attempt records each statement's label, and flags every CONFIRMED one that rests on the
  primary-source exception (``exception:primary_source:<statement id>``), so reviews can count them;
* nothing is recorded if a label or the project record changes before the attempt is committed.

A label never allows or forbids an option by itself: the spec lets a human act on unconfirmed items.

Limits. Which statements an item has, their wording, sources and judgments are trusted service-layer
inputs; a statement the service leaves out is not seen here. ``request_option`` and
``request_project_option`` still judge a choice without any labels, so a service must call this path for the
binding to hold. Nothing here shows a view to anyone, so a matching hash does not prove a person read it.
The labels cover CHANGE_INPUTS evidence only as far as the service lists it. A result is not an
authorization token.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from agora.audit_anchor import AnchoredAuditChain
from agora.decision_cell.options import GateResult, OptionRequest, ProjectRecord, request_option
from agora.decision_cell.project_store import (
    ProjectRecordError, _canonical, _event_id as _record_event_id, _hash, _identifier, load_project_record,
)
from agora.decision_cell.verification import (
    IndependenceJudgment, Source, StatementLabel, VerificationError, _key, _label_event_id, statement_label,
)
from agora.principal import Principal

MAX_STATEMENTS = 100


@dataclass(frozen=True)
class StatementEvidence:
    """One statement of an item as the trusted service holds it."""
    statement_id: str
    statement_text: str
    sources: tuple[Source, ...]
    judgments: tuple[IndependenceJudgment, ...] = ()


@dataclass(frozen=True)
class ItemEvidence:
    tenant_id: str
    project_id: str
    study_id: str
    item_id: str
    # (statement id, label in force), ordered by statement id.
    statements: tuple[tuple[str, StatementLabel], ...]
    evidence_hash: str

    @property
    def primary_source_exception_ids(self) -> tuple[str, ...]:
        """Statements whose CONFIRMED label rests on the exception; every result relying on one must say so."""
        return tuple(i for i, s in self.statements if s.relies_on_primary_source_exception)


@dataclass(frozen=True)
class LabelledGateResult:
    gate: GateResult
    evidence: ItemEvidence


def item_evidence(
    *, tenant_id: str, project_id: str, study_id: str, item_id: str,
    statements: tuple[StatementEvidence, ...], audit: AnchoredAuditChain,
) -> ItemEvidence:
    """The labels in force for an item and the hash of that view. A trusted service-side read.

    The order in which statements, sources and judgments are listed does not change the hash.
    """
    if not isinstance(statements, tuple) or not 1 <= len(statements) <= MAX_STATEMENTS \
            or not all(isinstance(s, StatementEvidence) and _identifier(s.statement_id) for s in statements):
        raise VerificationError("EVIDENCE_INVALID", f"statements must be a tuple of 1 to {MAX_STATEMENTS}")
    if len({s.statement_id for s in statements}) != len(statements):
        raise VerificationError("EVIDENCE_INVALID", "every statement needs its own exact id")
    labels = tuple(
        (s.statement_id, statement_label(
            tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id,
            statement_id=s.statement_id, statement_text=s.statement_text, sources=s.sources,
            judgments=s.judgments, audit=audit))
        for s in sorted(statements, key=lambda s: s.statement_id))
    body = [tenant_id, project_id, study_id, item_id, [
        [statement_id, s.label.value, s.basis.value if s.basis else None, s.primary_source_id,
         s.confirmed_by_subject_id, s.stale_confirmation, s.revision, s.assessment.evidence_fingerprint]
        for statement_id, s in labels]]
    return ItemEvidence(tenant_id, project_id, study_id, item_id, labels, _hash(_canonical(body)))


def require_unchanged(db: sqlite3.Connection, evidence: ItemEvidence) -> None:
    """Inside an append transaction: refuse if any statement gained a promotion or demotion since the read."""
    for statement_id, label in evidence.statements:
        key = _key(evidence.tenant_id, evidence.project_id, evidence.study_id, evidence.item_id, statement_id)
        if db.execute("SELECT 1 FROM audit_events WHERE event_id=?",
                      (_label_event_id(key, label.revision + 1),)).fetchone():
            raise VerificationError("EVIDENCE_CHANGED", "a label changed; read the item again")


def _flags(evidence: ItemEvidence) -> tuple[str, ...]:
    flags = [f"tenant:{evidence.tenant_id}", f"project:{evidence.project_id}",
             f"study:{evidence.study_id}", f"item:{evidence.item_id}"]
    flags += [f"label:{s.label.value}:{i}" for i, s in evidence.statements]
    flags += [f"stale_confirmation:{i}" for i, s in evidence.statements if s.stale_confirmation]
    flags += [f"exception:primary_source:{i}" for i in evidence.primary_source_exception_ids]
    return tuple(flags)


def request_labelled_option(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, audit: AnchoredAuditChain, **context: Any,
) -> LabelledGateResult:
    """``request_project_option`` with the item's labels read here and bound into the attempt.

    The item is ``request.event_id``. An untrustworthy store or malformed evidence raises before the gate
    is reached; a blocked choice is returned and audited like any other.
    """
    if {"record", "record_hash", "evidence_hash", "audit_flags", "in_transaction"} & set(context):
        raise ProjectRecordError("RECORD_INVALID", "stored inputs cannot be supplied by the caller")
    if not isinstance(request, OptionRequest) or context.get("study") is None:
        raise VerificationError("REQUEST_INVALID", "an OptionRequest and a StudyState are required")
    stored = load_project_record(tenant_id=tenant_id, project_id=project_id, audit=audit)
    evidence = item_evidence(
        tenant_id=tenant_id, project_id=project_id, study_id=context["study"].study_id,
        item_id=request.event_id, statements=statements, audit=audit)
    record = stored.record if stored else ProjectRecord(project_id, tenant_id, "")
    next_version = (stored.version if stored else 0) + 1

    def inputs_unchanged(db: sqlite3.Connection) -> None:
        if db.execute("SELECT 1 FROM audit_events WHERE event_id=?",
                      (_record_event_id(tenant_id, project_id, next_version),)).fetchone():
            raise VerificationError("RECORD_CHANGED", "the project record changed; submit again")
        require_unchanged(db, evidence)

    gate = request_option(
        principal, request, record=record, audit=audit,
        record_hash=stored.record_hash if stored else None, evidence_hash=evidence.evidence_hash,
        audit_flags=_flags(evidence), in_transaction=inputs_unchanged, **context)
    return LabelledGateResult(gate, evidence)


__all__ = ["ItemEvidence", "LabelledGateResult", "MAX_STATEMENTS", "StatementEvidence", "item_evidence",
           "request_labelled_option", "require_unchanged"]

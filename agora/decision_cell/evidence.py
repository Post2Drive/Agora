"""An event item's verification labels, bound into the option gate (DECISION_CELL_SPEC 2A and 3A).

``item_evidence`` reads the label in force for each of an item's statements and hashes the whole view.
``request_labelled_option`` is the gate path that uses it:

* a choice that decides on the evidence (IGNORE and the run options, CHANGE_INPUTS included) must name the
  view the person was shown, and is blocked if the view has changed since;
* the view's hash is part of the action fingerprint, so a second approval given for one view does not cover
  another;
* the attempt records each statement's label, and flags every CONFIRMED one that rests on the
  primary-source exception (``exception:primary_source:<statement id>``), so reviews can count them;
* nothing is recorded if a label or the project record changes before the attempt is committed;
* a recorded retraction or correction of the item (``retractions``) is part of the view in the same way: it
  changes the hash, is recorded with the attempt, and blocks the commit if it arrives after the read.

A label never allows or forbids an option by itself: the spec lets a human act on unconfirmed items. A
statement's recorded rating does: a run that would add it needs its data owner's grant (see ``statements``).

The item must have a recorded statement list (``statements``), and exactly those statements, as worded,
must be given. Once it has one, the other gate calls block every choice that decides on the evidence.

Limits. Sources and judgments are trusted service-layer inputs, and so is the statement list: nothing checks
it against any content. ``request_option`` and ``request_project_option`` still judge a choice about an item
that was never registered. Nothing here shows a view to anyone, so a matching hash does not prove a person read it.
The labels cover CHANGE_INPUTS evidence only as far as the service lists it. A result is not an
authorization token.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from agora.audit_anchor import AnchoredAuditChain
from agora.decision_cell.options import (
    GateResult, InputRef, OptionRequest, ProjectRecord, request_option,
)
from agora.decision_cell.project_store import (
    ProjectRecordError, _canonical, _event_id as _record_event_id, _hash, _identifier, load_project_record,
)
from agora.decision_cell.retractions import (
    BASED_ON_RETRACTED_ITEM, CorrectionKind, ItemCorrection, load_item_corrections, require_no_newer_correction,
)
from agora.decision_cell.statements import (
    MAX_STATEMENTS, ItemStatements, load_item_statements, require_no_newer_list, statement_input_id,
    wording_hash,
)
from agora.decision_cell.verification import (
    IndependenceJudgment, Source, StatementLabel, VerificationError, _key, _label_event_id, statement_label,
)
from agora.principal import Principal


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
    # The item's recorded statement list these labels were read against.
    listed: ItemStatements
    # Retractions and corrections of this item, in the order recorded.
    corrections: tuple[ItemCorrection, ...] = ()

    @property
    def stamps(self) -> tuple[str, ...]:
        """What a result relying on this item must show because it was retracted."""
        retracted = any(c.kind is CorrectionKind.RETRACTION for c in self.corrections)
        return (BASED_ON_RETRACTED_ITEM,) if retracted else ()

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
    listed = load_item_statements(
        tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id, audit=audit)
    if listed is None:
        raise VerificationError("STATEMENTS_NOT_REGISTERED", "record the item's statement list first")
    # A non-string wording is left for the label read below to refuse as malformed evidence.
    if all(isinstance(s.statement_text, str) for s in statements) and dict(listed.statements) != {
            s.statement_id: wording_hash(s.statement_text) for s in statements}:
        raise VerificationError("STATEMENTS_MISMATCH", "give exactly the listed statements, as worded")
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
    corrections = load_item_corrections(
        tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id, audit=audit)
    if corrections:  # added only when present, so other views keep their hash
        body.append([[c.kind.value, c.correcting_item_id] for c in corrections])
    if listed.ratings:  # so a second approval lapses when a rating is raised; unrated lists keep their hash
        body.append(["ratings", [[i, r.sensitivity, r.data_owner_subject_id] for i, r in listed.ratings]])
    return ItemEvidence(tenant_id, project_id, study_id, item_id, labels, _hash(_canonical(body)), listed,
                        corrections)


def require_unchanged(db: sqlite3.Connection, evidence: ItemEvidence) -> None:
    """Inside an append transaction: refuse if, since the read, a statement was added, promoted or demoted,
    or the item was retracted or corrected."""
    require_no_newer_list(db, evidence.listed)
    require_no_newer_correction(db, evidence.tenant_id, evidence.project_id, evidence.study_id,
                                evidence.item_id, len(evidence.corrections))
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
    flags += [f"{c.kind.value}:{c.correcting_item_id}" for c in evidence.corrections]
    return tuple(flags)


def _recorded_inputs(listed: ItemStatements) -> tuple[InputRef, ...]:
    """Every listed statement as the gate judges it. An unrated one gets an empty sensitivity, which blocks."""
    ratings = dict(listed.ratings)
    return tuple(InputRef(statement_input_id(listed.item_id, statement_id),
                          ratings[statement_id].sensitivity if statement_id in ratings else "",
                          ratings[statement_id].data_owner_subject_id if statement_id in ratings else None)
                 for statement_id, _ in listed.statements)


def request_labelled_option(
    principal: Principal | None, request: OptionRequest, *, statements: tuple[StatementEvidence, ...],
    tenant_id: str, project_id: str, audit: AnchoredAuditChain, **context: Any,
) -> LabelledGateResult:
    """``request_project_option`` with the item's labels read here and bound into the attempt.

    The item is ``request.event_id``. An untrustworthy store or malformed evidence raises before the gate
    is reached; a blocked choice is returned and audited like any other.
    """
    if {"record", "record_hash", "evidence_hash", "item_statements", "audit_flags",
            "in_transaction"} & set(context):
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
        item_statements=_recorded_inputs(evidence.listed),
        audit_flags=_flags(evidence), in_transaction=inputs_unchanged, **context)
    return LabelledGateResult(gate, evidence)


__all__ = ["ItemEvidence", "LabelledGateResult", "MAX_STATEMENTS", "StatementEvidence", "item_evidence",
           "request_labelled_option", "require_unchanged"]

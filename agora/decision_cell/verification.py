"""Verification labels for one statement in an event item (DECISION_CELL_SPEC section 2A).

The system computes CLAIM or REPORTED-BY-MULTIPLE and may say a statement could be confirmed. It never
returns CONFIRMED on its own: that needs a recorded promotion by the project's designated owner, or by a
delegate named in the stored project record, who holds the high-assurance approver role.

Independence fails closed. Two sources count as two only if a person recorded that pair as independent for
this statement, nobody recorded it as not independent, both have a known owner and a known upstream origin,
those owners differ, and the supplied citation links and origins show neither a path between them nor a
common upstream (including the origin of a source that one of them copies). Neither they nor any listed
source they draw on may have identical content hashes.

A promotion is bound to a fingerprint of the evidence judged: the statement wording, each source's
attributes and content hash, and the judgments. If any of these is added, removed or edited, the old
promotion no longer applies and the computed label is returned.

Trust boundary. Sources, their attributes (owner, origin, citations, primary kind, correction policy) and
the judgments are trusted service-layer inputs; nothing here authenticates them or looks for hidden copying.
A content hash is not checked against any content here. Judgments name a statement id, so after the wording
changes they still count towards the computed label; only the promotion lapses.
``tenant_id`` and ``audit`` come from the service's configuration. The audit chain keeps hashes of the
evidence and reason texts, not the texts; the service must keep them. This module fetches nothing, scores
no source and does not handle retractions.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from itertools import combinations

from agora.audit_anchor import AnchoredAuditChain, AnchorWriteError, verify_anchored
from agora.audit_chain import AuditReplayError
from agora.decision_cell.options import DecisionCellError
from agora.decision_cell.project_store import (
    _canonical, _event_id as _record_event_id, _hash, _identifier, _writer, load_project_record,
)
from agora.policy import POLICY_VERSION
from agora.principal import Principal, decide_principal

MAX_SOURCES = 100
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PREFIX = "dc-label-"
_CONFIRMED, _DEMOTED = "confirmed", "demoted"


class Label(str, Enum):
    CLAIM = "CLAIM"
    REPORTED_BY_MULTIPLE = "REPORTED-BY-MULTIPLE"
    CONFIRMED = "CONFIRMED"


class PrimaryKind(str, Enum):
    """The three kinds of primary source the spec names."""
    PARTY_ITSELF = "party_itself"
    OFFICIAL_RECORD = "official_record"
    ORIGINAL_FOOTAGE_WITH_PROVENANCE = "original_footage_with_provenance"


class Basis(str, Enum):
    INDEPENDENT_PAIR = "independent_pair"
    PRIMARY_SOURCE = "primary_source"      # the spec's exception: no qualifying independent pair


class VerificationError(DecisionCellError):
    """Refused or untrustworthy verification operation. ``code`` is stable and safe to log."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class Source:
    source_id: str
    # SHA-256 (64 lower-case hex) of the source content that was judged, computed by the service.
    content_hash: str = field(kw_only=True)
    owner_id: str | None = None             # None: unknown, so independence cannot be established
    upstream_origin_id: str | None = None   # wire story, press release or original post; None: unknown
    cites: frozenset[str] = frozenset()     # ids this source cites, syndicates or copies
    primary_kind: PrimaryKind | None = None
    published_correction_policy: bool = False


@dataclass(frozen=True)
class IndependenceJudgment:
    statement_id: str                       # a judgment made for one statement is not usable for another
    source_a: str
    source_b: str
    independent: bool
    judged_by_subject_id: str
    basis: str


@dataclass(frozen=True)
class Assessment:
    computed_label: Label                    # never CONFIRMED
    confirmable_by: Basis | None             # a proposal only; None means nobody may confirm this evidence
    primary_source_ids: tuple[str, ...]
    evidence_fingerprint: str


@dataclass(frozen=True)
class StatementLabel:
    label: Label
    assessment: Assessment
    # Set only while label is CONFIRMED.
    basis: Basis | None = None
    primary_source_id: str | None = None
    confirmed_by_subject_id: str | None = None
    # A promotion is in force on the chain but was made on different evidence, so it does not apply.
    stale_confirmation: bool = False
    revision: int = 0                        # promotions and demotions recorded so far

    @property
    def relies_on_primary_source_exception(self) -> bool:
        """Every result that relies on a statement with this set must show the flag (spec 2A)."""
        return self.basis is Basis.PRIMARY_SOURCE


def _reason_text(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _validate(statement_id: object, statement_text: object, sources: object, judgments: object) -> None:
    if not _identifier(statement_id):
        raise VerificationError("ID_INVALID", "statement id")
    if not _reason_text(statement_text):
        raise VerificationError("EVIDENCE_INVALID", "the statement wording is required")
    if not isinstance(sources, tuple) or not 1 <= len(sources) <= MAX_SOURCES:
        raise VerificationError("EVIDENCE_INVALID", f"sources must be a tuple of 1 to {MAX_SOURCES}")
    ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Source) or not _identifier(source.source_id) or source.source_id in ids:
            raise VerificationError("EVIDENCE_INVALID", "every source needs its own exact id")
        ids.add(source.source_id)
        if not isinstance(source.content_hash, str) or not _SHA256.fullmatch(source.content_hash):
            raise VerificationError("EVIDENCE_INVALID", "every source needs the SHA-256 of its content")
        if not all(v is None or _identifier(v) for v in (source.owner_id, source.upstream_origin_id)):
            raise VerificationError("EVIDENCE_INVALID", "owner and origin are exact ids or None")
        if not isinstance(source.cites, frozenset) or not all(_identifier(c) for c in source.cites):
            raise VerificationError("EVIDENCE_INVALID", "cites must be a frozenset of exact ids")
        if source.primary_kind is not None and not isinstance(source.primary_kind, PrimaryKind):
            raise VerificationError("EVIDENCE_INVALID", "unknown primary kind")
        if type(source.published_correction_policy) is not bool:
            raise VerificationError("EVIDENCE_INVALID", "correction policy must be true or false")
    if not isinstance(judgments, tuple):
        raise VerificationError("EVIDENCE_INVALID", "judgments must be a tuple")
    for judgment in judgments:
        if (not isinstance(judgment, IndependenceJudgment) or type(judgment.independent) is not bool
                or judgment.statement_id != statement_id
                or judgment.source_a not in ids or judgment.source_b not in ids
                or judgment.source_a == judgment.source_b
                or not _identifier(judgment.judged_by_subject_id) or not _reason_text(judgment.basis)):
            raise VerificationError("EVIDENCE_INVALID", "a judgment names this statement, two listed sources, who and why")


def _upstream(source_id: str, sources_by_id: dict[str, Source]) -> set[str]:
    """The source and everything it draws on: citations and recorded origins, followed through every
    listed source reached by either. Source ids and origin ids share one set, so a listed source named
    as another's origin brings its own citations and origin with it.
    """
    seen, todo = set(), [source_id]
    while todo:
        current = todo.pop()
        if current not in seen:
            seen.add(current)
            listed = sources_by_id.get(current)
            if listed is not None:
                todo.extend(listed.cites)
                if listed.upstream_origin_id is not None:
                    todo.append(listed.upstream_origin_id)
    return seen


def assess_statement(
    statement_id: str, sources: tuple[Source, ...],
    judgments: tuple[IndependenceJudgment, ...] = (), *, statement_text: str,
) -> Assessment:
    """The label the system may show by itself, and whether an approver could confirm. Pure."""
    _validate(statement_id, statement_text, sources, judgments)
    verdicts: dict[frozenset[str], bool] = {}
    for judgment in judgments:
        pair = frozenset((judgment.source_a, judgment.source_b))
        verdicts[pair] = verdicts.get(pair, True) and judgment.independent  # any "no" wins
    by_id = {s.source_id: s for s in sources}
    upstreams = {i: _upstream(i, by_id) for i in by_id}
    # Identical content among what two sources draw on is a copy, whatever the links and judgments say.
    contents = {i: {by_id[u].content_hash for u in upstreams[i] if u in by_id} for i in by_id}

    def independent(a: Source, b: Source) -> bool:
        return (verdicts.get(frozenset((a.source_id, b.source_id))) is True
                and None not in (a.owner_id, b.owner_id, a.upstream_origin_id, b.upstream_origin_id)
                and a.owner_id != b.owner_id
                and not upstreams[a.source_id] & upstreams[b.source_id]
                and not contents[a.source_id] & contents[b.source_id])

    pairs = [(a, b) for a, b in combinations(sources, 2) if independent(a, b)]
    qualifying = any(s.primary_kind is not None or s.published_correction_policy
                     for pair in pairs for s in pair)
    primaries = tuple(sorted(s.source_id for s in sources if s.primary_kind is not None))
    confirmable = Basis.INDEPENDENT_PAIR if qualifying else Basis.PRIMARY_SOURCE if primaries else None

    body = {
        "statement_id": statement_id,
        "statement_text": statement_text,
        "sources": sorted(
            [s.source_id, s.owner_id, s.upstream_origin_id, sorted(s.cites),
             s.primary_kind.value if s.primary_kind else None, s.published_correction_policy,
             s.content_hash]
            for s in sources),
        "judgments": sorted(
            [*sorted((j.source_a, j.source_b)), j.independent, j.judged_by_subject_id, j.basis]
            for j in judgments),
    }
    return Assessment(Label.REPORTED_BY_MULTIPLE if pairs else Label.CLAIM, confirmable, primaries,
                      _hash(_canonical(body)))


def _key(tenant_id: str, project_id: str, study_id: str, item_id: str, statement_id: str) -> str:
    return _hash(_canonical([tenant_id, project_id, study_id, item_id, statement_id]))


def _label_event_id(key: str, revision: int) -> str:
    return f"{_PREFIX}{key}-{revision}"


def _history(writer: AnchoredAuditChain, key: str) -> list[dict]:
    """This statement's promotions and demotions in order, from a cleanly anchored chain."""
    try:
        with writer.anchors.lock():
            state = verify_anchored(writer.chain, writer.anchors)
            if not state["valid"]:
                raise VerificationError("AUDIT_UNANCHORED", state["status"])
            prefix = f"{_PREFIX}{key}-"
            rows = writer.chain.db.execute(
                "SELECT event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? ORDER BY seq",
                (len(prefix), prefix)).fetchall()
        events = []
        for revision, (event_id, raw) in enumerate(rows, 1):
            event = json.loads(raw)
            # Revisions alternate: confirmed, demoted, confirmed, ...
            kind = _CONFIRMED if revision % 2 else _DEMOTED
            if (event_id != _label_event_id(key, revision) or event.get("sequence") != revision
                    or event.get("event_type") != f"decision_cell_label_{kind}"):
                raise VerificationError("STORE_INCONSISTENT", "label history is out of order")
            events.append(event)
        return events
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError("STORE_ERROR", "the label history could not be read") from exc


def statement_label(
    *, tenant_id: str, project_id: str, study_id: str, item_id: str, statement_id: str,
    statement_text: str, sources: tuple[Source, ...], judgments: tuple[IndependenceJudgment, ...] = (),
    audit: AnchoredAuditChain,
) -> StatementLabel:
    """The label in force for this evidence. A trusted service-side read; no caller permission check."""
    writer = _writer(audit)
    if not all(_identifier(v) for v in (tenant_id, project_id, study_id, item_id)):
        raise VerificationError("ID_INVALID", "ids must be exact non-empty strings")
    assessment = assess_statement(statement_id, sources, judgments, statement_text=statement_text)
    history = _history(writer, _key(tenant_id, project_id, study_id, item_id, statement_id))
    revision = len(history)
    if revision % 2 == 0:
        return StatementLabel(assessment.computed_label, assessment, revision=revision)
    event = history[-1]
    if event.get("evidence_fingerprint") != assessment.evidence_fingerprint:
        return StatementLabel(assessment.computed_label, assessment, stale_confirmation=True,
                              revision=revision)
    try:
        basis = Basis(event["reason"])
        primary = [v[len("primary:"):] for v in event["resource_ids"] if v.startswith("primary:")]
    except Exception as exc:
        raise VerificationError("STORE_INCONSISTENT", "a promotion has no valid basis") from exc
    return StatementLabel(
        Label.CONFIRMED, assessment, basis=basis, primary_source_id=primary[0] if primary else None,
        confirmed_by_subject_id=event["subject_id"], revision=revision)


def _change_label(
    principal: Principal | None, *, kind: str, tenant_id: str, project_id: str, study_id: str,
    item_id: str, statement_id: str, statement_text: str, sources: tuple[Source, ...],
    judgments: tuple[IndependenceJudgment, ...], reason_text: str, primary_source_id: str | None,
    primary_reason_text: str | None, expected_revision: int, audit: AnchoredAuditChain,
    now: datetime | None,
) -> StatementLabel:
    writer = _writer(audit)
    context = dict(tenant_id=tenant_id, project_id=project_id, study_id=study_id, item_id=item_id,
                   statement_id=statement_id, statement_text=statement_text, sources=sources,
                   judgments=judgments, audit=writer)
    current = statement_label(**context)
    subject = principal.subject_id if isinstance(principal, Principal) else "unknown"
    operation = "confirm_statement" if kind == _CONFIRMED else "demote_statement"
    scope = [f"tenant:{tenant_id}", f"project:{project_id}", f"study:{study_id}", f"item:{item_id}",
             f"statement:{statement_id}"]

    def refuse(code: str, detail: str = "") -> VerificationError:
        try:
            writer.append({
                "event_id": f"dc-statement-denied-{uuid.uuid4().hex}",
                "event_type": "decision_cell_label_denied", "subject_id": subject,
                "operation": operation, "decision": "deny", "policy_version": POLICY_VERSION,
                "reason": code, "resource_ids": scope,
            })
        except Exception as exc:
            raise VerificationError("AUDIT_FAILED", f"refused ({code}) and not recorded") from exc
        return VerificationError(code, detail)

    stored = load_project_record(tenant_id=tenant_id, project_id=project_id, audit=writer)
    if stored is None:
        raise refuse("NO_PROJECT_RECORD")
    decision, role = decide_principal(
        principal, "decision_approval",
        {"project_id": project_id, "tenant_id": tenant_id, "source_sensitivity": "internal"},
        now=now, required_role="approver")
    if role is None:
        raise refuse("NOT_PERMITTED", decision["reason"])
    if subject != stored.record.owner_subject_id and subject not in stored.record.delegate_subject_ids:
        raise refuse("NOT_DESIGNATED_APPROVER")
    if not _reason_text(reason_text):
        raise refuse("REASON_MISSING")
    if type(expected_revision) is not int or expected_revision != current.revision:
        raise refuse("REVISION_CONFLICT", "the label history changed since it was read")

    revision = current.revision + 1
    key = _key(tenant_id, project_id, study_id, item_id, statement_id)
    event = {
        "event_id": _label_event_id(key, revision), "event_type": f"decision_cell_label_{kind}",
        "subject_id": subject, "operation": operation, "decision": "allow",
        "policy_version": POLICY_VERSION, "sequence": revision, "resource_ids": scope,
        "record_hash": stored.record_hash, "reason_text_hash": _hash(_canonical(reason_text)),
        "evidence_fingerprint": current.assessment.evidence_fingerprint,
    }
    if kind == _CONFIRMED:
        if revision % 2 == 0:
            # Includes a stale promotion: it must be demoted on the record before a new one.
            raise refuse("ALREADY_PROMOTED", "demote the promotion in force first")
        basis = current.assessment.confirmable_by
        if basis is None:
            raise refuse("EVIDENCE_INSUFFICIENT")
        if basis is Basis.PRIMARY_SOURCE:
            if primary_source_id not in current.assessment.primary_source_ids \
                    or not _reason_text(primary_reason_text):
                raise refuse("PRIMARY_SOURCE_NOT_JUSTIFIED", "name a listed primary source and say why")
            event["resource_ids"] = scope + [f"primary:{primary_source_id}"]
            event["primary_reason_hash"] = _hash(_canonical(primary_reason_text))
        elif primary_source_id is not None or primary_reason_text is not None:
            raise refuse("PRIMARY_SOURCE_NOT_NEEDED", "this evidence has a qualifying independent pair")
        event["reason"] = basis.value
    else:
        if revision % 2:
            raise refuse("NOT_PROMOTED")
        event["reason"] = "demoted"

    def record_unchanged(db: sqlite3.Connection) -> None:
        # A newer project record could have removed this delegate after the check above.
        newer = _record_event_id(tenant_id, project_id, stored.version + 1)
        if db.execute("SELECT 1 FROM audit_events WHERE event_id=?", (newer,)).fetchone():
            raise VerificationError("RECORD_CHANGED", "the project record changed; submit again")

    try:
        writer.append(event, in_transaction=record_unchanged)
    except VerificationError:
        raise
    except AuditReplayError as exc:
        raise VerificationError("REVISION_CONFLICT", "another change was recorded first") from exc
    except AnchorWriteError as exc:
        raise VerificationError("AUDIT_ANCHOR_WRITE_FAILED", "committed but unanchored; reconcile first") from exc
    except Exception as exc:
        raise VerificationError("AUDIT_FAILED", "the label change could not be recorded") from exc
    return statement_label(**context)


def confirm_statement(
    principal: Principal | None, *, tenant_id: str, project_id: str, study_id: str, item_id: str,
    statement_id: str, statement_text: str, sources: tuple[Source, ...],
    judgments: tuple[IndependenceJudgment, ...] = (), reason_text: str, expected_revision: int,
    audit: AnchoredAuditChain, primary_source_id: str | None = None,
    primary_reason_text: str | None = None, now: datetime | None = None,
) -> StatementLabel:
    """Promote to CONFIRMED. Refused attempts are audited and raise ``VerificationError``."""
    return _change_label(
        principal, kind=_CONFIRMED, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
        item_id=item_id, statement_id=statement_id, statement_text=statement_text,
        sources=sources, judgments=judgments, reason_text=reason_text, primary_source_id=primary_source_id,
        primary_reason_text=primary_reason_text, expected_revision=expected_revision, audit=audit, now=now)


def demote_statement(
    principal: Principal | None, *, tenant_id: str, project_id: str, study_id: str, item_id: str,
    statement_id: str, statement_text: str, sources: tuple[Source, ...],
    judgments: tuple[IndependenceJudgment, ...] = (), reason_text: str, expected_revision: int,
    audit: AnchoredAuditChain, now: datetime | None = None,
) -> StatementLabel:
    """Withdraw the promotion in force, including a stale one. Same permission as promotion."""
    return _change_label(
        principal, kind=_DEMOTED, tenant_id=tenant_id, project_id=project_id, study_id=study_id,
        item_id=item_id, statement_id=statement_id, statement_text=statement_text,
        sources=sources, judgments=judgments, reason_text=reason_text, primary_source_id=None, primary_reason_text=None,
        expected_revision=expected_revision, audit=audit, now=now)


__all__ = [
    "Assessment", "Basis", "IndependenceJudgment", "Label", "MAX_SOURCES", "PrimaryKind", "Source",
    "StatementLabel", "VerificationError", "assess_statement", "confirm_statement", "demote_statement",
    "statement_label",
]

"""Verification labels (DECISION_CELL_SPEC 2A). Synthetic sources and principals only."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decision_cell import (
    Basis, IndependenceJudgment, Label, PrimaryKind, ProjectRecord, Source, VerificationError,
    assess_statement as _assess, confirm_statement, demote_statement, statement_label, write_project_record,
)
from agora.decision_cell import verification as v
from agora.principal import SyntheticFixtureAdapter

NOW = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(subject, roles=("approver",), **kw):
    base = {"subject_id": subject, "tenant_id": "t1", "project_ids": ["p1"], "roles": list(roles),
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


AD = SyntheticFixtureAdapter({
    "owner": _fx("owner"), "delegate": _fx("dee"), "stranger": _fx("sam"),
    "owner_operator": _fx("owner", ["operator"]), "owner_low": _fx("owner", assurance="STANDARD"),
    "outsider": _fx("owner", project_ids=["p2"]),
})
OWNER = AD.issue("owner")

H, H2 = "a" * 64, "b" * 64


def _h(name):
    return hashlib.sha256(name.encode()).hexdigest()


TEXT = "the port closed on 27 November"
A = Source("a", "owner-a", "origin-a", published_correction_policy=True, content_hash=H)
B = Source("b", "owner-b", "origin-b", content_hash=H2)
PRIMARY = Source("gazette", "state", "notice-1", primary_kind=PrimaryKind.OFFICIAL_RECORD, content_hash="c" * 64)


def assess_statement(statement_id, sources, judgments=(), statement_text=TEXT):
    return _assess(statement_id, sources, judgments, statement_text=statement_text)


def judged(a="a", b="b", independent=True, who="analyst", why="separate reporters on site", statement="st1"):
    return IndependenceJudgment(statement, a, b, independent, who, why)


@pytest.fixture
def audit(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.db")
    anchors = AnchorStore(tmp_path / "audit.anchor", "c1")
    bootstrap_anchor(chain, anchors, performed_by="test")
    writer = AnchoredAuditChain(chain, anchors)
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner"), expected_version=0,
                         audit=writer, now=NOW)
    yield writer
    writer.close()


def events(audit):
    return [json.loads(r[0]) for r in audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]


def where(audit, sources=(A, B), judgments=(judged(),), **kw):
    return dict(tenant_id="t1", project_id="p1", study_id="s1", item_id="e1", statement_id="st1",
                statement_text=TEXT, sources=sources, judgments=judgments, audit=audit, **kw)


def confirm(audit, principal=OWNER, revision=0, **kw):
    kw.setdefault("reason_text", "both checked")
    return confirm_statement(principal, expected_revision=revision, now=NOW, **where(audit, **kw))


def demote(audit, principal=OWNER, revision=1, **kw):
    kw.setdefault("reason_text", "withdrawn")
    return demote_statement(principal, expected_revision=revision, now=NOW, **where(audit, **kw))


def refused(code, call):
    with pytest.raises(VerificationError) as caught:
        call()
    assert caught.value.code == code, str(caught.value)


# -- the computed label -------------------------------------------------------

def test_two_judged_independent_sources_are_reported_by_multiple():
    result = assess_statement("st1", (A, B), (judged(),))
    assert (result.computed_label, result.confirmable_by) == (Label.REPORTED_BY_MULTIPLE, Basis.INDEPENDENT_PAIR)


@pytest.mark.parametrize("second,judgments", [
    (B, ()),                                                    # nobody established independence
    (B, (judged(independent=False),)),
    (B, (judged(), judged("b", "a", False, "other"))),          # any "no" wins, either order
    (replace(B, owner_id=None), (judged(),)),
    (replace(B, upstream_origin_id=None), (judged(),)),
    (replace(B, owner_id="owner-a"), (judged(),)),
    (replace(B, upstream_origin_id="origin-a"), (judged(),)),
    (replace(B, cites=frozenset({"a"})), (judged(),)),
    (replace(B, cites=frozenset({"wire"})), (judged(),)),       # A cites the same wire below
])
def test_sources_count_as_one_unless_independence_is_established(second, judgments):
    first = replace(A, cites=frozenset({"wire"})) if second.cites == frozenset({"wire"}) else A
    result = assess_statement("st1", (first, second), judgments)
    assert (result.computed_label, result.confirmable_by) == (Label.CLAIM, None)


def test_copying_through_a_third_source_makes_a_pair_dependent():
    middle = Source("m", "owner-m", "origin-m", cites=frozenset({"a"}), content_hash=_h("1"))
    b = replace(B, cites=frozenset({"m"}))
    assert assess_statement("st1", (A, middle, b), (judged(),)).computed_label is Label.CLAIM


def test_sharing_the_origin_of_a_copied_source_makes_a_pair_dependent():
    middle = Source("m", "owner-m", "origin-b", content_hash=_h("2"))  # A copies m, which comes from B's origin
    a = replace(A, cites=frozenset({"m"}))
    assert assess_statement("st1", (a, middle, B), (judged(),)).computed_label is Label.CLAIM


def test_a_source_named_as_the_others_origin_makes_a_pair_dependent():
    b = replace(B, upstream_origin_id="a")
    assert assess_statement("st1", (A, b), (judged(),)).computed_label is Label.CLAIM


@pytest.mark.parametrize("extra", [
    # a's origin is a listed post that itself comes from b's origin
    (Source("m", "owner-m", "origin-b", content_hash=_h("3")),),
    # a's origin is a listed post that copies b
    (Source("m", "owner-m", "origin-m", cites=frozenset({"b"}), content_hash=_h("4")),),
    # ... and the same one step further along the chain of origins
    (Source("m", "owner-m", "n", content_hash=_h("5")),
     Source("n", "owner-n", "origin-n", cites=frozenset({"b"}), content_hash=_h("6"))),
])
def test_a_listed_origin_brings_its_own_upstream_with_it(extra):
    sources = (replace(A, upstream_origin_id="m"), B, *extra)
    result = assess_statement("st1", sources, (judged(),))
    assert (result.computed_label, result.confirmable_by) == (Label.CLAIM, None)


def test_an_origin_followed_from_a_cited_source_counts():
    sources = (replace(A, cites=frozenset({"m"})), B, Source("m", "owner-m", "n", content_hash=_h("7")),
               Source("n", "owner-n", "origin-n", cites=frozenset({"b"}), content_hash=_h("8")))
    assert assess_statement("st1", sources, (judged(),)).computed_label is Label.CLAIM


def test_a_source_that_is_its_own_origin_terminates_and_stays_independent():
    sources = (replace(A, upstream_origin_id="a"), B)
    assert assess_statement("st1", sources, (judged(),)).computed_label is Label.REPORTED_BY_MULTIPLE


@pytest.mark.parametrize("bad", [None, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, H + "\n", 5])
def test_every_source_needs_a_content_hash(bad):
    refused("EVIDENCE_INVALID", lambda: assess_statement("st1", (A, replace(B, content_hash=bad)), (judged(),)))


@pytest.mark.parametrize("text", [None, "", "  ", "\ud800"])
def test_the_statement_wording_is_required(text):
    refused("EVIDENCE_INVALID", lambda: assess_statement("st1", (A, B), (judged(),), text))


@pytest.mark.parametrize("change", [
    {"statement_text": "the port reopened on 27 November"},
    {"sources": (A, replace(B, content_hash="e" * 64))},
])
def test_edited_wording_or_source_content_drops_a_confirmation(audit, change):
    confirm(audit)
    after = statement_label(**{**where(audit), **change})
    assert after.label is Label.REPORTED_BY_MULTIPLE and after.stale_confirmation
    assert after.confirmed_by_subject_id is None


def test_a_judgment_for_another_statement_is_refused():
    refused("EVIDENCE_INVALID", lambda: assess_statement("st1", (A, B), (judged(statement="st2"),)))


def test_a_citation_cycle_terminates():
    a, b = replace(A, cites=frozenset({"b"})), replace(B, cites=frozenset({"a"}))
    assert assess_statement("st1", (a, b), (judged(),)).computed_label is Label.CLAIM


def test_a_pair_without_primary_or_correction_policy_cannot_be_confirmed(audit):
    plain = (replace(A, published_correction_policy=False), B)
    result = assess_statement("st1", plain, (judged(),))
    assert (result.computed_label, result.confirmable_by) == (Label.REPORTED_BY_MULTIPLE, None)
    refused("EVIDENCE_INSUFFICIENT", lambda: confirm(audit, sources=plain))


def test_a_correction_policy_outside_the_independent_pair_does_not_qualify_it():
    sources = (replace(A, published_correction_policy=False), B,
               Source("c", published_correction_policy=True, content_hash=_h("9")))
    assert assess_statement("st1", sources, (judged(),)).confirmable_by is None


def test_the_system_never_computes_confirmed(audit):
    for sources, judgments in (((A, B), (judged(),)), ((PRIMARY,), ())):
        assert assess_statement("st1", sources, judgments).computed_label is not Label.CONFIRMED
        assert statement_label(**where(audit, sources, judgments)).label is not Label.CONFIRMED


@pytest.mark.parametrize("sources,judgments", [
    ((), ()), ([A], ()), ((A, A), ()), ((replace(A, source_id=" a"),), ()),
    ((replace(A, cites={"b"}),), ()), ((replace(A, primary_kind="official_record"),), ()),
    ((replace(A, published_correction_policy=1),), ()), ((replace(A, owner_id=""),), ()),
    ((A, B), [judged()]), ((A, B), (judged(b="zz"),)), ((A, B), (judged(b="a"),)),
    ((A, B), (judged(independent=1),)), ((A, B), (judged(who=""),)), ((A, B), (judged(why=" "),)),
    (tuple(Source(f"s{i}", content_hash=_h(f"s{i}")) for i in range(v.MAX_SOURCES + 1)), ()),
])
def test_malformed_evidence_is_refused(sources, judgments):
    refused("EVIDENCE_INVALID", lambda: assess_statement("st1", sources, judgments))


def test_fingerprint_ignores_order_but_not_content():
    base = assess_statement("st1", (A, B), (judged(),)).evidence_fingerprint
    assert assess_statement("st1", (B, A), (judged("b", "a"),)).evidence_fingerprint == base
    for other in (assess_statement("st2", (A, B), (judged(statement="st2"),)),
                  assess_statement("st1", (A, replace(B, owner_id="x")), (judged(),)),
                  assess_statement("st1", (A, B), (judged(why="different"),))):
        assert other.evidence_fingerprint != base


# -- promotion ----------------------------------------------------------------

def test_owner_confirms_and_the_chain_records_it_without_reason_text(audit):
    result = confirm(audit, reason_text="secret reason")
    assert (result.label, result.basis, result.confirmed_by_subject_id, result.revision) == (
        Label.CONFIRMED, Basis.INDEPENDENT_PAIR, "owner", 1)
    assert not result.relies_on_primary_source_exception
    assert statement_label(**where(audit)) == result
    assert "secret reason" not in json.dumps(events(audit))
    assert events(audit)[-1]["evidence_fingerprint"] == result.assessment.evidence_fingerprint
    assert audit.verify()["valid"]


@pytest.mark.parametrize("who,code", [
    (None, "NOT_PERMITTED"), ("owner_operator", "NOT_PERMITTED"), ("owner_low", "NOT_PERMITTED"),
    ("outsider", "NOT_PERMITTED"), ("delegate", "NOT_DESIGNATED_APPROVER"),
    ("stranger", "NOT_DESIGNATED_APPROVER"),
])
def test_only_the_designated_approver_can_confirm_and_refusals_are_audited(audit, who, code):
    refused(code, lambda: confirm(audit, AD.issue(who) if who else None))
    assert statement_label(**where(audit)).label is Label.REPORTED_BY_MULTIPLE
    assert (events(audit)[-1]["decision"], events(audit)[-1]["reason"]) == ("deny", code)


def test_a_recorded_delegate_may_confirm(audit):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", frozenset({"dee"})),
                         expected_version=1, audit=audit, now=NOW)
    assert confirm(audit, AD.issue("delegate")).confirmed_by_subject_id == "dee"


def test_a_delegate_removed_during_the_call_cannot_confirm(audit, monkeypatch):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", frozenset({"dee"})),
                         expected_version=1, audit=audit, now=NOW)
    real = v.load_project_record

    def load_then_remove(**kw):
        stored = real(**kw)
        write_project_record(OWNER, ProjectRecord("p1", "t1", "owner"), expected_version=2,
                             audit=audit, now=NOW)
        return stored

    monkeypatch.setattr(v, "load_project_record", load_then_remove)
    refused("RECORD_CHANGED", lambda: confirm(audit, AD.issue("delegate")))
    assert statement_label(**where(audit)).revision == 0


def test_no_project_record_means_nobody_can_confirm(audit):
    refused("NO_PROJECT_RECORD", lambda: confirm_statement(
        OWNER, expected_revision=0, reason_text="x", now=NOW,
        **{**where(audit), "project_id": "p9"}))


@pytest.mark.parametrize("text", ["", "  ", None, "\ud800"])
def test_a_reason_is_required(audit, text):
    refused("REASON_MISSING", lambda: confirm(audit, reason_text=text))


@pytest.mark.parametrize("source_id,why", [
    (None, None), ("gazette", None), ("gazette", " "), (None, "official"), ("other", "official"),
])
def test_the_primary_source_exception_must_name_the_source_and_why(audit, source_id, why):
    refused("PRIMARY_SOURCE_NOT_JUSTIFIED", lambda: confirm(
        audit, sources=(PRIMARY,), judgments=(), primary_source_id=source_id, primary_reason_text=why))


def test_primary_source_confirmation_is_flagged(audit):
    result = confirm(audit, sources=(PRIMARY,), judgments=(), primary_source_id="gazette",
                     primary_reason_text="the notifying authority's own record")
    assert result.label is Label.CONFIRMED and result.relies_on_primary_source_exception
    assert result.primary_source_id == "gazette"
    assert result.assessment.computed_label is Label.CLAIM


def test_a_primary_claim_is_not_accepted_when_the_pair_route_applies(audit):
    refused("PRIMARY_SOURCE_NOT_NEEDED", lambda: confirm(
        audit, primary_source_id="a", primary_reason_text="x"))


@pytest.mark.parametrize("sources,judgments", [
    ((A, B, PRIMARY), (judged(),)),
    ((A, replace(B, owner_id="new")), (judged(),)),
    ((A, B), (judged(), judged(independent=False, who="second"))),
])
def test_changed_evidence_makes_a_confirmation_stale(audit, sources, judgments):
    confirm(audit)
    after = statement_label(**where(audit, sources, judgments))
    assert after.label is not Label.CONFIRMED and after.stale_confirmation
    assert after.basis is None and after.confirmed_by_subject_id is None
    # It must be demoted on the record before the new evidence can be confirmed.
    refused("ALREADY_PROMOTED", lambda: confirm(audit, revision=1, sources=sources, judgments=judgments))


def test_demote_then_confirm_again(audit):
    confirm(audit)
    down = demote(audit)
    assert (down.label, down.revision, down.stale_confirmation) == (Label.REPORTED_BY_MULTIPLE, 2, False)
    assert confirm(audit, revision=2).revision == 3


def test_demotion_needs_a_promotion_and_the_same_permission(audit):
    refused("NOT_PROMOTED", lambda: demote(audit, revision=0))
    confirm(audit)
    refused("NOT_DESIGNATED_APPROVER", lambda: demote(audit, AD.issue("stranger")))
    assert statement_label(**where(audit)).label is Label.CONFIRMED


@pytest.mark.parametrize("revision", [1, -1, False, "0"])
def test_a_stale_or_malformed_revision_is_refused(audit, revision):
    refused("REVISION_CONFLICT", lambda: confirm(audit, revision=revision))


def test_a_concurrent_change_is_a_conflict(audit, monkeypatch):
    stale = statement_label(**where(audit))
    confirm(audit)
    real, calls = v.statement_label, []
    monkeypatch.setattr(v, "statement_label",
                        lambda **kw: stale if not calls and not calls.append(1) else real(**kw))
    refused("REVISION_CONFLICT", lambda: confirm(audit))


def test_confirmation_does_not_cross_study_item_or_statement(audit):
    confirm(audit)
    for change in ({"study_id": "s2"}, {"item_id": "e2"},
                   {"statement_id": "st2", "judgments": (judged(statement="st2"),)}):
        assert statement_label(**{**where(audit), **change}).revision == 0


def test_a_history_gap_is_refused(audit):
    key = v._key("t1", "p1", "s1", "e1", "st1")
    audit.append({"event_id": v._label_event_id(key, 2), "event_type": "decision_cell_label_confirmed",
                  "sequence": 2})
    refused("STORE_INCONSISTENT", lambda: statement_label(**where(audit)))


def test_an_unanchored_writer_is_refused(audit):
    with pytest.raises(PermissionError):
        statement_label(**{**where(audit), "audit": audit.chain})


@pytest.mark.parametrize("order", [(True, False), (False, True)])
def test_a_contrary_judgment_wins_in_either_order(order):
    judgments = tuple(judged(independent=answer, who=f"person-{answer}") for answer in order)
    assert assess_statement("st1", (A, B), judgments).computed_label is Label.CLAIM


def test_a_history_event_with_the_wrong_revision_number_is_refused(audit):
    key = v._key("t1", "p1", "s1", "e1", "st1")
    audit.append({"event_id": v._label_event_id(key, 1), "event_type": "decision_cell_label_confirmed",
                  "sequence": 7})
    refused("STORE_INCONSISTENT", lambda: statement_label(**where(audit)))


def test_an_unanchored_tail_is_not_read(audit):
    audit.chain.append({"event_id": "appended-without-an-anchor"})
    refused("AUDIT_UNANCHORED", lambda: statement_label(**where(audit)))


def test_identical_content_is_a_copy_even_when_judged_independent():
    result = assess_statement("st1", (A, replace(B, content_hash=A.content_hash)), (judged(),))
    assert (result.computed_label, result.confirmable_by) == (Label.CLAIM, None)


def test_copying_a_source_with_the_others_content_makes_a_pair_dependent():
    middle = Source("m", "owner-m", "origin-m", content_hash=B.content_hash)
    a = replace(A, cites=frozenset({"m"}))
    assert assess_statement("st1", (a, middle, B), (judged(),)).computed_label is Label.CLAIM


@pytest.mark.parametrize("side", ["first", "second"])
@pytest.mark.parametrize("copied", [
    {"owner_id": "other"},                   # replaced below by the other side's owner
    {"owner_id": None},
    {"upstream_origin_id": None},
])
def test_a_copied_source_must_have_a_known_origin_and_an_owner_unrelated_to_the_other_side(side, copied):
    first, second = (A, B) if side == "first" else (B, A)
    if copied.get("owner_id") == "other":
        copied = {"owner_id": second.owner_id}
    middle = replace(Source("m", "owner-m", "origin-m", content_hash=_h("3")), **copied)
    sources = (replace(first, cites=frozenset({"m"})), middle, second)
    judgments = (judged(first.source_id, second.source_id),)
    result = assess_statement("st1", sources, judgments)
    assert (result.computed_label, result.confirmable_by) == (Label.CLAIM, None)


def test_a_copied_source_with_its_own_owner_and_origin_keeps_a_pair_independent():
    middle = Source("m", "owner-m", "origin-m", content_hash=_h("3"))
    result = assess_statement("st1", (replace(A, cites=frozenset({"m"})), middle, B), (judged(),))
    assert result.computed_label is Label.REPORTED_BY_MULTIPLE


def test_two_sides_copying_different_outlets_of_one_owner_are_dependent():
    m = Source("m", "owner-x", "origin-m", content_hash=_h("3"))
    n = Source("n", "owner-x", "origin-n", content_hash=_h("4"))
    sources = (replace(A, cites=frozenset({"m"})), replace(B, cites=frozenset({"n"})), m, n)
    assert assess_statement("st1", sources, (judged(),)).computed_label is Label.CLAIM


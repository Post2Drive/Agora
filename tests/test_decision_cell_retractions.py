"""Retractions and corrections of event items (DECISION_CELL_SPEC 2A). Synthetic data only."""
from __future__ import annotations

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    CorrectionError,
    CorrectionKind,
    Escalation,
    EscalationStatus,
    Option,
    ProjectRecord,
    allowed_run_attempts,
    load_item_corrections,
    load_response_window,
    open_response_window,
    record_item_correction,
    register_item_statements,
    respond_to_item,
    retraction_stamps,
    write_project_record,
)
from agora.decision_cell import evidence as ev
from agora.decision_cell import response_window as rw
from agora.decision_cell import retractions as rt
from tests.test_decision_cell_evidence import (
    PAIR,
    STUDY,
    ask,
    choice,
    listed,
    run_context,
    view,
)
from tests.test_decision_cell_verification import (  # noqa: F401
    AD,
    NOW,
    OWNER,
    audit,
    events,
)

SCOPE = dict(tenant_id="t1", project_id="p1", study_id="s1")


def new_item(audit, item):
    register_item_statements(statements={"n1": f"notice from {item}"}, expected_version=0, audit=audit,
                             item_id=item, **SCOPE)


def link(audit, by="r1", original="e1", kind=CorrectionKind.RETRACTION, principal=OWNER, count=0, **kw):
    kw.setdefault("reason_text", "the source withdrew it")
    return record_item_correction(principal, item_id=original, correcting_item_id=by, kind=kind,
                                  expected_count=count, audit=audit, now=NOW, **SCOPE, **kw)


@pytest.fixture
def two_items(audit):
    listed(audit)
    new_item(audit, "r1")
    return audit


def refused(code, call):
    with pytest.raises(CorrectionError) as caught:
        call()
    assert caught.value.code == code, str(caught.value)


def links(audit, item="e1"):
    return load_item_corrections(item_id=item, audit=audit, **SCOPE)


def stamps(audit, *items):
    return retraction_stamps(item_ids=items, audit=audit, **SCOPE)


# -- recording ----------------------------------------------------------------

def test_a_retraction_links_the_new_item_and_stamps_only_the_original(two_items):
    recorded = link(two_items)
    assert (recorded.item_id, recorded.correcting_item_id, recorded.kind, recorded.sequence) == (
        "e1", "r1", CorrectionKind.RETRACTION, 1)
    assert links(two_items) == (recorded,) and links(two_items, "r1") == ()
    assert stamps(two_items, "r1", "e1", "e1") == (("e1", BASED_ON_RETRACTED_ITEM),)


def test_a_correction_is_not_a_retraction(two_items):
    link(two_items, kind=CorrectionKind.CORRECTION)
    assert stamps(two_items, "e1") == () and view(two_items).stamps == ()
    new_item(two_items, "r2")
    link(two_items, by="r2", count=1)
    assert stamps(two_items, "e1") == (("e1", BASED_ON_RETRACTED_ITEM),)
    assert view(two_items).stamps == (BASED_ON_RETRACTED_ITEM,)


def test_retracting_a_retraction_keeps_the_first_stamp(two_items):
    link(two_items)
    new_item(two_items, "r2")
    link(two_items, by="r2", original="r1")
    assert [i for i, _ in stamps(two_items, "e1", "r1")] == ["e1", "r1"]


@pytest.mark.parametrize("principal,code", [
    (AD.issue("delegate"), "NOT_DESIGNATED_APPROVER"), (AD.issue("stranger"), "NOT_DESIGNATED_APPROVER"),
    (AD.issue("owner_operator"), "NOT_PERMITTED"), (AD.issue("owner_low"), "NOT_PERMITTED"),
    (AD.issue("outsider"), "NOT_PERMITTED"), (None, "NOT_PERMITTED"),
])
def test_only_the_owner_or_a_named_delegate_can_link_and_refusals_are_audited(two_items, principal, code):
    refused(code, lambda: link(two_items, principal=principal))
    assert links(two_items) == ()
    event = events(two_items)[-1]
    assert (event["event_type"], event["decision"], event["reason"]) == (
        "decision_cell_item_correction_denied", "deny", code)


def test_a_delegate_named_in_the_record_can_link(two_items):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", frozenset({"dee"})), expected_version=1,
                         audit=two_items, now=NOW)
    assert link(two_items, principal=AD.issue("delegate")).recorded_by_subject_id == "dee"


@pytest.mark.parametrize("change,code", [
    (dict(reason_text=" "), "REASON_MISSING"), (dict(reason_text=None), "REASON_MISSING"),
    (dict(count=1), "COUNT_CONFLICT"), (dict(by="e1"), "SAME_ITEM"),
    (dict(by="never-listed"), "ITEM_NOT_REGISTERED"),
    (dict(original="never-listed"), "ITEM_NOT_REGISTERED"),
    (dict(by="e1", original="r1"), "NOT_A_NEWER_ITEM"),
])
def test_an_unusable_link_is_refused(two_items, change, code):
    refused(code, lambda: link(two_items, **change))
    assert links(two_items) == () and links(two_items, "r1") == ()
    assert events(two_items)[-1]["reason"] == code


def test_a_kind_must_be_stated(two_items):
    refused("KIND_INVALID", lambda: link(two_items, kind="retraction"))


def test_one_new_item_links_to_one_original(two_items):
    new_item(two_items, "r2")
    link(two_items, by="r2")
    for original, count in (("e1", 1), ("r1", 0)):
        refused("ALREADY_LINKED", lambda: link(two_items, by="r2", original=original, count=count))
    assert len(links(two_items)) == 1 and links(two_items, "r1") == ()
    assert events(two_items)[-1]["reason"] == "ALREADY_LINKED"


def test_the_same_item_ids_in_another_study_are_separate(two_items):
    link(two_items)
    other = dict(tenant_id="t1", project_id="p1", study_id="s2")
    for item in ("e1", "r1"):
        register_item_statements(statements={"n1": item}, expected_version=0, audit=two_items,
                                 item_id=item, **other)
    assert retraction_stamps(item_ids=("e1",), audit=two_items, **other) == ()
    record_item_correction(OWNER, item_id="e1", correcting_item_id="r1", kind=CorrectionKind.RETRACTION,
                           reason_text="x", expected_count=0, audit=two_items, now=NOW, **other)


def test_a_record_change_during_linking_records_nothing(two_items, monkeypatch):
    real = rt.load_project_record

    def stale(**kw):
        stored = real(**kw)
        write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", frozenset({"x"})),
                             expected_version=stored.version, audit=two_items, now=NOW)
        return stored

    monkeypatch.setattr(rt, "load_project_record", stale)
    refused("RECORD_CHANGED", lambda: link(two_items))
    assert links(two_items) == ()


def test_a_forged_history_is_refused(two_items):
    event_id = rt._event_id("t1", "p1", "s1", "e1", 1)
    two_items.append({"event_id": event_id, "event_type": "something_else", "subject_id": "x",
                      "decision": "allow", "sequence": 1, "reason": "retraction", "resource_ids": ["a", "b"]})
    refused("STORE_INCONSISTENT", lambda: stamps(two_items, "e1"))


def test_an_unanchored_chain_is_refused(two_items):
    two_items.chain.append({"event_id": "unanchored", "event_type": "x"})
    refused("AUDIT_UNANCHORED", lambda: links(two_items))


@pytest.mark.parametrize("items,code", [((), "ITEMS_REQUIRED"), (["e1"], "ITEMS_REQUIRED"),
                                        ((" e1",), "ID_INVALID")])
def test_stamps_need_the_items_named_exactly(two_items, items, code):
    refused(code, lambda: retraction_stamps(item_ids=items, audit=two_items, **SCOPE))


# -- the gate -----------------------------------------------------------------

def test_a_retraction_after_the_view_blocks_the_choice_until_it_is_seen(two_items):
    seen = view(two_items)
    link(two_items)
    stale = ask(two_items, choice(viewed=seen.evidence_hash))
    assert stale.gate.failures == ("evidence_changed_since_viewed",)
    current = view(two_items)
    assert current.evidence_hash != seen.evidence_hash
    fresh = ask(two_items, choice(viewed=current.evidence_hash))
    assert fresh.gate.executable  # a retraction forbids nothing; the person decides
    assert "retraction:r1" in events(two_items)[-1]["resource_ids"]


def test_a_second_approval_from_before_the_retraction_does_not_cover_the_choice(two_items):
    def approved(fingerprint=None):
        escalation = Escalation(EscalationStatus.APPROVED, "second", fingerprint) if fingerprint else Escalation()
        return ask(two_items, choice(Option.CONTINUE, view(two_items).evidence_hash),
                   escalation=escalation, **run_context()).gate

    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", second_approver_subject_id="second",
                                              requires_second_approval=True),
                         expected_version=1, audit=two_items, now=NOW)
    before = approved().action_fingerprint
    assert approved(before).executable
    link(two_items)
    assert approved(before).failures == ("second_approval_for_different_action",)


def test_a_retraction_between_read_and_commit_records_nothing(two_items, monkeypatch):
    seen = view(two_items).evidence_hash
    real = ev.load_item_corrections

    def stale(**kw):
        result = real(**kw)
        link(two_items)
        return result

    monkeypatch.setattr(ev, "load_item_corrections", stale)
    refused("CORRECTIONS_CHANGED", lambda: ask(two_items, choice(viewed=seen)))
    assert not any(e["event_type"] == "decision_cell_option" for e in events(two_items))


def test_a_retraction_after_the_gate_entry_keeps_the_window_unanswered(two_items, monkeypatch):
    key = dict(**SCOPE, item_id="e1", audit=two_items)
    open_response_window(now=NOW, **key)
    seen = view(two_items).evidence_hash
    real = rw.request_labelled_option

    def then_retract(*a, **kw):
        result = real(*a, **kw)
        link(two_items)
        return result

    monkeypatch.setattr(rw, "request_labelled_option", then_retract)
    refused("CORRECTIONS_CHANGED", lambda: respond_to_item(
        OWNER, choice(viewed=seen), tenant_id="t1", project_id="p1", study=STUDY, audit=two_items,
        approved_result_hash_for=lambda s: None, now=NOW, statements=(PAIR,)))
    assert load_response_window(**key).decision_count == 0


def test_run_attempts_are_listed_and_marked_against_the_first_link(two_items):
    def run():
        return ask(two_items, choice(Option.CONTINUE, view(two_items).evidence_hash), **run_context())

    ask(two_items, choice(viewed=view(two_items).evidence_hash))  # IGNORE: not a run
    ask(two_items, choice(Option.CONTINUE), **run_context())      # blocked: no view named
    assert run().gate.executable
    assert [a.made_before_any_link for a in attempts(two_items)] == [True]
    link(two_items)
    assert run().gate.executable
    found = attempts(two_items)
    assert [(a.option, a.subject_id, a.made_before_any_link) for a in found] == [
        ("CONTINUE", "owner", True), ("CONTINUE", "owner", False)]
    assert attempts(two_items, "r1") == ()


def attempts(audit, item="e1"):
    return allowed_run_attempts(item_id=item, audit=audit, **SCOPE)

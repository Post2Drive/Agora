"""Verification labels bound into the option gate (DECISION_CELL_SPEC 2A and 3A). Synthetic data only."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from agora.decision_cell import (
    Escalation, EscalationStatus, Option, OptionRequest, ProjectRecord, StatementEvidence, StudyState,
    StatementSetError, VerificationError, item_evidence, load_item_statements, load_response_window,
    open_response_window, register_item_statements, request_labelled_option, request_option,
    request_project_option, respond_to_item, write_project_record,
)
from agora.decision_cell import evidence as ev
from agora.decision_cell import response_window as rw
from agora.decision_cell.project_store import ProjectRecordError
from tests.test_decision_cell_verification import (
    A, AD, B, NOW, OWNER, PRIMARY, TEXT, audit, confirm, demote, events, judged,  # noqa: F401
)

STUDY = StudyState("s1", 3)
PAIR = StatementEvidence("st1", TEXT, (A, B), (judged(),))
SOLE = StatementEvidence("st2", "a notice was issued", (PRIMARY,))
WORDING = {"st1": TEXT, "st2": SOLE.statement_text}
KW = dict(tenant_id="t1", project_id="p1", study_id="s1", item_id="e1")


def listed(audit, statements=(PAIR,), item="e1"):
    """Register any statement ids not yet listed, as intake would. Never rewords a listed one."""
    if not (isinstance(statements, tuple) and 0 < len(statements) <= 100
            and all(isinstance(s, StatementEvidence) for s in statements)
            and len({s.statement_id for s in statements}) == len(statements)):
        return
    key = {**KW, "item_id": item}
    current = load_item_statements(audit=audit, **key)
    have = dict(current.statements) if current else {}
    new = {s.statement_id: s.statement_text for s in statements if s.statement_id not in have}
    if new:
        old = {i: WORDING[i] for i in have}
        register_item_statements(statements={**old, **new}, expected_version=current.version if current else 0,
                                 audit=audit, **key)
        WORDING.update(new)


def view(audit, statements=(PAIR,)):
    listed(audit, statements)
    return item_evidence(statements=statements, audit=audit, **KW)


def choice(option=Option.IGNORE, viewed=None, **kw):
    base = dict(option=option, event_id="e1", reason="seen", budget_units=100, viewed_evidence_hash=viewed)
    base.update(kw)
    return OptionRequest(**base)


def ask(audit, request, statements=(PAIR,), **kw):
    kw.setdefault("study", STUDY)
    kw.setdefault("now", NOW)
    listed(audit, statements)
    return request_labelled_option(OWNER, request, statements=statements, tenant_id="t1", project_id="p1",
                                   audit=audit, **kw)


def run_context():
    return dict(branch_cost_units=10, snapshot_verifies=lambda s, r: True)


def test_a_choice_on_the_current_view_passes_and_records_the_labels(audit):
    current = view(audit)
    result = ask(audit, choice(viewed=current.evidence_hash))
    assert result.gate.executable and result.evidence == current
    event = events(audit)[-1]
    assert event["evidence_hash"] == current.evidence_hash
    assert "label:REPORTED-BY-MULTIPLE:st1" in event["resource_ids"]
    assert not any(v.startswith("exception:") for v in event["resource_ids"])


@pytest.mark.parametrize("option", [Option.IGNORE, Option.CONTINUE, Option.CHANGE_INPUTS])
def test_a_deciding_choice_must_name_the_view_it_was_made_on(audit, option):
    result = ask(audit, choice(option))
    assert "evidence_view_required" in result.gate.failures and not result.gate.executable


def test_a_promotion_after_the_view_blocks_a_deciding_choice(audit):
    seen = view(audit).evidence_hash
    confirm(audit)
    result = ask(audit, choice(viewed=seen))
    assert result.gate.failures == ("evidence_changed_since_viewed",)
    assert events(audit)[-1]["decision"] == "deny"


@pytest.mark.parametrize("changed", [
    replace(PAIR, judgments=(judged(independent=False),)),
    replace(PAIR, sources=(A, replace(B, content_hash="d" * 64))),
])
def test_changed_evidence_changes_the_view(audit, changed):
    seen = view(audit).evidence_hash
    assert ask(audit, choice(viewed=seen), (changed,)).gate.failures == ("evidence_changed_since_viewed",)


def test_an_added_statement_changes_the_view_but_listing_order_does_not(audit):
    one = view(audit)
    assert view(audit, (replace(PAIR, sources=(B, A)),)) == one
    two = view(audit, (PAIR, SOLE))
    assert one.evidence_hash != two.evidence_hash
    assert view(audit, (SOLE, PAIR)) == two


def test_the_view_hash_is_bound_to_the_item(audit):
    listed(audit, item="e2")
    other = item_evidence(statements=(PAIR,), audit=audit, **{**KW, "item_id": "e2"})
    assert other.evidence_hash != view(audit).evidence_hash


@pytest.mark.parametrize("option,extra", [(Option.HOLD, {"recheck_at": NOW + timedelta(hours=1)}),
                                          (Option.COMPARE, {})])
def test_a_choice_that_decides_nothing_is_not_blocked_by_an_old_view(audit, option, extra):
    assert ask(audit, choice(option, "e" * 64, **extra)).gate.executable


def test_unconfirmed_evidence_does_not_forbid_a_human_run_choice(audit):
    claim = replace(PAIR, judgments=())
    current = view(audit, (claim,))
    result = ask(audit, choice(Option.CONTINUE, current.evidence_hash), (claim,), **run_context())
    assert result.gate.executable
    assert "label:CLAIM:st1" in events(audit)[-1]["resource_ids"]


def test_the_primary_source_exception_and_a_stale_confirmation_are_flagged(audit):
    confirm_args = dict(sources=(PRIMARY,), judgments=(), primary_source_id="gazette",
                        primary_reason_text="the official record")
    confirm(audit, **confirm_args)
    sole = StatementEvidence("st1", TEXT, (PRIMARY,))
    current = view(audit, (sole,))
    assert current.primary_source_exception_ids == ("st1",)
    assert ask(audit, choice(viewed=current.evidence_hash), (sole,)).gate.executable
    flags = events(audit)[-1]["resource_ids"]
    assert "exception:primary_source:st1" in flags and "label:CONFIRMED:st1" in flags
    ask(audit, choice(Option.COMPARE), (replace(sole, sources=(replace(PRIMARY, content_hash="d" * 64),)),))
    assert "stale_confirmation:st1" in events(audit)[-1]["resource_ids"]


def test_a_second_approval_does_not_carry_over_to_new_evidence(audit):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", second_approver_subject_id="sam",
                                              requires_second_approval=True),
                         expected_version=1, audit=audit, now=NOW)
    first = view(audit)
    pending = ask(audit, choice(Option.CONTINUE, first.evidence_hash), **run_context())
    approval = Escalation(EscalationStatus.APPROVED, "sam", pending.gate.action_fingerprint)
    assert ask(audit, choice(Option.CONTINUE, first.evidence_hash), escalation=approval,
               **run_context()).gate.executable
    confirm(audit)
    later = ask(audit, choice(Option.CONTINUE, view(audit).evidence_hash), escalation=approval,
                **run_context())
    assert later.gate.failures == ("second_approval_for_different_action",)


def _after_view(monkeypatch, module, name, action):
    """Run ``action`` once, just after ``module.name`` returns: a change between the read and the commit."""
    real, done = getattr(module, name), []

    def wrapped(*args, **kwargs):
        value = real(*args, **kwargs)
        if not done:
            done.append(True)
            action()
        return value

    monkeypatch.setattr(module, name, wrapped)


@pytest.mark.parametrize("promoted_first", [False, True])
def test_a_label_change_before_the_commit_records_nothing(audit, monkeypatch, promoted_first):
    if promoted_first:
        confirm(audit)
    seen = view(audit).evidence_hash
    _after_view(monkeypatch, ev, "item_evidence",
                (lambda: demote(audit)) if promoted_first else (lambda: confirm(audit)))
    with pytest.raises(VerificationError) as caught:
        ask(audit, choice(viewed=seen))
    assert caught.value.code == "EVIDENCE_CHANGED"
    assert not [e for e in events(audit) if e["event_type"] == "decision_cell_option"]


def test_a_project_record_change_before_the_commit_records_nothing(audit, monkeypatch):
    seen = view(audit).evidence_hash
    _after_view(monkeypatch, ev, "item_evidence", lambda: write_project_record(
        OWNER, ProjectRecord("p1", "t1", "owner", delegate_subject_ids=frozenset({"dee"})),
        expected_version=1, audit=audit, now=NOW))
    with pytest.raises(VerificationError) as caught:
        ask(audit, choice(viewed=seen))
    assert caught.value.code == "RECORD_CHANGED"
    assert not [e for e in events(audit) if e["event_type"] == "decision_cell_option"]


def test_a_named_view_is_not_ignored_on_the_unlabelled_path(audit):
    result = request_project_option(OWNER, choice(viewed=view(audit).evidence_hash), tenant_id="t1",
                                    project_id="p1", audit=audit, study=STUDY, now=NOW)
    assert result.failures == ("item_labels_required", "evidence_not_supplied")


@pytest.mark.parametrize("name", ["evidence_hash", "audit_flags", "in_transaction"])
def test_a_caller_cannot_supply_the_bound_evidence(audit, name):
    for call in (lambda: request_project_option(OWNER, choice(), tenant_id="t1", project_id="p1",
                                                audit=audit, study=STUDY, **{name: None}),
                 lambda: ask(audit, choice(), **{name: None})):
        with pytest.raises(ProjectRecordError):
            call()


def test_a_malformed_evidence_hash_is_blocked(audit):
    from agora.decision_cell import evaluate_option
    result = evaluate_option(OWNER, choice(), record=ProjectRecord("p1", "t1", "owner"), study=STUDY,
                             evidence_hash="not-a-hash", now=NOW)
    assert "evidence_hash_invalid" in result.failures


@pytest.mark.parametrize("statements", [(), [PAIR], (PAIR, PAIR), ("st1",),
                                        tuple(replace(PAIR, statement_id=f"s{i}", judgments=())
                                              for i in range(101))])
def test_malformed_statement_lists_are_refused(audit, statements):
    with pytest.raises(VerificationError) as caught:
        view(audit, statements)
    assert caught.value.code == "EVIDENCE_INVALID"


# -- through the response window ----------------------------------------------

def respond(audit, request, statements=(PAIR,)):
    if statements is not None:
        listed(audit, statements)
    return respond_to_item(OWNER, request, tenant_id="t1", project_id="p1", study=STUDY, audit=audit,
                           approved_result_hash_for=lambda s: None, now=NOW, statements=statements)


def window(audit):
    return load_response_window(audit=audit, **KW)


def test_an_old_view_does_not_answer_the_window_and_the_current_one_does(audit):
    open_response_window(audit=audit, now=NOW, **KW)
    seen = view(audit).evidence_hash
    confirm(audit)
    result, state = respond(audit, choice(viewed=seen))
    assert not result.executable and state.status == "OPEN"
    result, state = respond(audit, choice(viewed=view(audit).evidence_hash))
    assert result.executable and state.status == "ANSWERED"


def test_a_label_change_before_the_answer_is_stored_leaves_the_window_open(audit, monkeypatch):
    open_response_window(audit=audit, now=NOW, **KW)
    seen = view(audit).evidence_hash
    _after_view(monkeypatch, rw, "request_labelled_option", lambda: confirm(audit))
    with pytest.raises(VerificationError) as caught:
        respond(audit, choice(viewed=seen))
    assert caught.value.code == "EVIDENCE_CHANGED"
    assert window(audit).status == "OPEN"


# -- the recorded statement list ----------------------------------------------

def plain(audit, request):
    return request_project_option(OWNER, request, tenant_id="t1", project_id="p1", audit=audit,
                                  study=STUDY, now=NOW, **run_context())


def options(audit):
    return [e for e in events(audit) if e["event_type"] == "decision_cell_option"]


def register(audit, statements, expected_version, **key):
    return register_item_statements(statements=statements, expected_version=expected_version,
                                    audit=audit, **{**KW, **key})


@pytest.mark.parametrize("option", [Option.IGNORE, Option.CONTINUE, Option.FORK_FROM_EVENT,
                                    Option.RERUN_FROM_START, Option.CHANGE_INPUTS])
def test_a_listed_item_cannot_be_decided_without_its_labels(audit, option):
    listed(audit)
    result = plain(audit, choice(option))
    assert not result.executable and "item_labels_required" in result.failures
    assert options(audit)[-1]["decision"] == "deny"


def test_the_low_level_gate_call_cannot_skip_the_labels_either(audit):
    listed(audit)
    result = request_option(OWNER, choice(), record=ProjectRecord("p1", "t1", "owner"), study=STUDY,
                            audit=audit, now=NOW)
    assert result.failures == ("item_labels_required",)


@pytest.mark.parametrize("option,extra", [(Option.HOLD, {"recheck_at": NOW + timedelta(hours=1)}),
                                          (Option.COMPARE, {})])
def test_a_listed_item_can_still_be_held_or_compared_without_labels(audit, option, extra):
    listed(audit)
    assert plain(audit, choice(option, **extra)).executable


def test_a_list_binds_only_its_own_item_and_study(audit):
    listed(audit)
    assert plain(audit, choice(event_id="e2")).executable
    other = request_project_option(OWNER, choice(), tenant_id="t1", project_id="p1", audit=audit,
                                   study=StudyState("s2", 3), now=NOW)
    assert other.executable


@pytest.mark.parametrize("event_id", ["e1 ", " e1", "e1\n"])
def test_a_padded_item_id_does_not_slip_past_the_list(audit, event_id):
    listed(audit)
    result = plain(audit, choice(event_id=event_id))
    assert "event_id_not_exact" in result.failures and not result.executable


def test_a_caller_cannot_say_that_labels_are_not_required(audit):
    listed(audit)
    with pytest.raises(PermissionError, match="read from the audit chain"):
        request_project_option(OWNER, choice(), tenant_id="t1", project_id="p1", audit=audit, study=STUDY,
                               now=NOW, labels_required=False)


def test_a_list_recorded_before_the_commit_stops_an_unlabelled_choice(audit, monkeypatch):
    from agora.decision_cell import options as gate_module
    _after_view(monkeypatch, gate_module, "evaluate_option", lambda: listed(audit))
    with pytest.raises(PermissionError, match="statement list"):
        plain(audit, choice())
    assert options(audit) == []


def test_a_list_recorded_before_the_answer_is_stored_leaves_the_window_open(audit, monkeypatch):
    open_response_window(audit=audit, now=NOW, **KW)
    _after_view(monkeypatch, rw, "request_project_option", lambda: listed(audit))
    with pytest.raises(PermissionError) as caught:
        respond(audit, choice(), None)
    assert caught.value.code == "WINDOW_CHANGED"
    assert window(audit).status == "OPEN"


def test_the_window_is_not_answered_without_labels(audit):
    open_response_window(audit=audit, now=NOW, **KW)
    listed(audit)
    result, state = respond(audit, choice(), None)
    assert result.failures == ("item_labels_required",) and state.status == "OPEN"


def test_labels_need_a_recorded_list(audit):
    with pytest.raises(VerificationError) as caught:
        item_evidence(statements=(PAIR,), audit=audit, **KW)
    assert caught.value.code == "STATEMENTS_NOT_REGISTERED"


@pytest.mark.parametrize("given", [(PAIR,), (SOLE,),
                                   (PAIR, replace(SOLE, statement_text="a notice was withdrawn")),
                                   (PAIR, SOLE, StatementEvidence("st3", "extra", (PRIMARY,)))])
def test_the_labelled_path_takes_exactly_the_listed_statements(audit, given):
    listed(audit, (PAIR, SOLE))
    with pytest.raises(VerificationError) as caught:
        request_labelled_option(OWNER, choice(), statements=given, tenant_id="t1", project_id="p1",
                                audit=audit, study=STUDY, now=NOW)
    assert caught.value.code == "STATEMENTS_MISMATCH"
    assert options(audit) == []


def test_a_statement_added_before_the_commit_records_nothing(audit, monkeypatch):
    seen = view(audit).evidence_hash
    _after_view(monkeypatch, ev, "item_evidence", lambda: listed(audit, (PAIR, SOLE)))
    with pytest.raises(StatementSetError) as caught:
        ask(audit, choice(viewed=seen))
    assert caught.value.code == "STATEMENTS_CHANGED"
    assert options(audit) == []


def test_a_statement_added_before_the_answer_is_stored_leaves_the_window_open(audit, monkeypatch):
    open_response_window(audit=audit, now=NOW, **KW)
    seen = view(audit).evidence_hash
    _after_view(monkeypatch, rw, "request_labelled_option", lambda: listed(audit, (PAIR, SOLE)))
    with pytest.raises(StatementSetError):
        respond(audit, choice(viewed=seen))
    assert window(audit).status == "OPEN"


def test_a_list_grows_and_reads_back(audit):
    assert load_item_statements(audit=audit, **KW) is None
    first = register(audit, {"a": "one"}, 0)
    second = register(audit, {"a": "one", "b": "two"}, 1)
    assert (first.version, second.version) == (1, 2)
    assert load_item_statements(audit=audit, **KW) == second
    assert "one" not in str(events(audit))


@pytest.mark.parametrize("statements,version,code", [
    ({"b": "two"}, 1, "STATEMENT_REMOVED"),
    ({"a": "reworded", "b": "two"}, 1, "STATEMENT_REMOVED"),
    ({"a": "one"}, 1, "NOTHING_ADDED"),
    ({"a": "one", "b": "two"}, 0, "VERSION_CONFLICT"),
    ({"a": "one", "b": "two"}, 2, "VERSION_CONFLICT"),
    ({}, 1, "STATEMENTS_INVALID"),
    ({"a ": "one"}, 1, "STATEMENTS_INVALID"),
    ({"a": "one", "b": "  "}, 1, "STATEMENTS_INVALID"),
    ({f"s{i}": "x" for i in range(101)}, 1, "STATEMENTS_INVALID"),
    ([("a", "one")], 1, "STATEMENTS_INVALID"),
])
def test_a_list_cannot_drop_reword_or_take_bad_entries(audit, statements, version, code):
    register(audit, {"a": "one"}, 0)
    before = len(events(audit))
    with pytest.raises(StatementSetError) as caught:
        register(audit, statements, version)
    assert caught.value.code == code and len(events(audit)) == before


def test_two_writers_of_one_version_cannot_both_win(audit, monkeypatch):
    from agora.decision_cell import statements as st
    register(audit, {"a": "one"}, 0)
    _after_view(monkeypatch, st, "load_item_statements",
                lambda: register(audit, {"a": "one", "b": "two"}, 1))
    with pytest.raises(StatementSetError) as caught:
        register(audit, {"a": "one", "c": "three"}, 1)
    assert caught.value.code == "VERSION_CONFLICT"


def test_a_chain_version_that_drops_a_statement_is_refused_on_read(audit):
    from agora.decision_cell.options import statement_set_event_id
    register(audit, {"a": "one"}, 0)
    audit.append({"event_id": statement_set_event_id("t1", "p1", "s1", "e1", 2),
                  "event_type": "decision_cell_item_statements", "sequence": 2,
                  "resource_ids": ["statement:" + "a" * 64 + ":b", "statement:" + "b" * 64 + ":c"]})
    with pytest.raises(StatementSetError) as caught:
        load_item_statements(audit=audit, **KW)
    assert caught.value.code == "STORE_INCONSISTENT"


def test_an_unanchored_chain_is_not_read_as_having_no_list(audit):
    register(audit, {"a": "one"}, 0)
    audit.chain.append({"event_id": "outside-the-anchor"})
    with pytest.raises(StatementSetError) as caught:
        load_item_statements(audit=audit, **KW)
    assert caught.value.code == "AUDIT_UNANCHORED"

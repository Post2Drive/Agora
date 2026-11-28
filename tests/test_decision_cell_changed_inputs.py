"""CHANGE_INPUTS over a fork from the event: some of one item's statements are left out. Synthetic data, mock backend."""
from __future__ import annotations

import shutil

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    Escalation,
    EscalationStatus,
    InputGrant,
    InputRef,
    Option,
    StatementRating,
    confirm_statement,
    execute_changed_inputs_fork,
    read_changed_inputs_fork,
    read_event_fork,
    register_item_statements,
    statement_input_id,
)
from agora.decision_cell import executor as ex
from conftest import make_project
from tests.test_decision_cell_evidence import PAIR, SOLE, choice, view
from tests.test_decision_cell_executor import STUDY, _run_source, added_events, files, go, left, recorded, refused
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import NOW, OWNER, PRIMARY, audit, events  # noqa: F401

BOTH = (PAIR, SOLE)


@pytest.fixture(scope="module")
def built_source(tmp_path_factory):
    project = make_project(tmp_path_factory.mktemp("built-inputs"), "source", rounds=6,
                           population={"llm_agents": 2, "crowd_agents": 20})
    _run_source(project)
    return project


@pytest.fixture
def source(built_source, tmp_path):
    copy = tmp_path / "source"
    shutil.copytree(built_source, copy)
    return copy


def ref(statement_id="st1", sensitivity="internal", owner=None, item="e1"):
    return InputRef(statement_input_id(item, statement_id), sensitivity, owner)


def request_for(audit, inputs=(ref("st1"),), **kw):
    kw.setdefault("budget_units", 100_000)
    kw.setdefault("event_round", 2)
    kw.setdefault("underlying", Option.FORK_FROM_EVENT)
    return choice(Option.CHANGE_INPUTS, view(audit, BOTH).evidence_hash, inputs=inputs, **kw)


def changed(audit, source, out, result="res1", **kw):
    request = kw.pop("request", None) or request_for(audit)
    kw.setdefault("study", STUDY)
    kw.setdefault("kill_switch_on", lambda: False)
    kw.setdefault("statements", BOTH)
    return execute_changed_inputs_fork(OWNER, request, tenant_id="t1", project_id="p1", result_id=result,
                                       source=source, out_dir=out, audit=audit, now=NOW, **kw)


def read(audit, out, result="res1"):
    return read_changed_inputs_fork(result_id=result, out_dir=out, audit=audit, **SCOPE)


def no_gate(audit, source, out, code, **kw):
    kw.setdefault("request", request_for(audit))
    before = len(events(audit))
    refused(code, lambda: changed(audit, source, out, **kw))
    assert len(events(audit)) == before and recorded(audit) is None and left(out) == []


def blocked(audit, source, out, request, **kw):
    error = refused("GATE_BLOCKED", lambda: changed(audit, source, out, request=request, **kw))
    assert recorded(audit) is None and left(out) == []
    return error.gate.failures


@pytest.mark.parametrize("kept,left_out", [(PAIR, SOLE), (SOLE, PAIR)])
def test_only_the_chosen_statement_is_added(audit, source, tmp_path, kept, left_out):
    before = files(source)
    done = changed(audit, source, tmp_path / "out",
                   request=request_for(audit, inputs=(ref(kept.statement_id),)))
    assert files(source) == before
    assert added_events(done.path / ex.WITH_EVENT) == [(3, {"round": 3, "text": kept.statement_text,
                                                           "type": "news"})]
    assert added_events(done.path / ex.WITHOUT_EVENT) == []
    manifest = done.manifest
    assert manifest["schema"] == ex.CHANGED_INPUTS_SCHEMA and manifest["underlying_option"] == "FORK_FROM_EVENT"
    assert manifest["included_statement_ids"] == [kept.statement_id]
    assert manifest["excluded_statement_ids"] == [left_out.statement_id]
    assert sorted(manifest["statement_labels"]) == ["st1", "st2"]  # the view the person decided on
    assert manifest["llm_backend"] == "mock" and manifest["validated_prediction_enabled"] is False
    gate = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    assert len(gate) == 1 and gate[0]["operation"] == Option.CHANGE_INPUTS.value
    assert gate[0]["event_id"] == done.basis.gate_event_id and gate[0]["count"] == manifest["cost_units"]
    assert done.basis == recorded(audit) and done.basis.item_ids == ("e1",)
    assert read(audit, tmp_path / "out") == done


def test_it_costs_the_same_as_the_fork_and_cannot_be_read_as_one(audit, source, tmp_path):
    done = changed(audit, source, tmp_path / "out")
    plain = go(audit, source, tmp_path / "out", result="fork1", statements=BOTH, request=choice(
        Option.FORK_FROM_EVENT, view(audit, BOTH).evidence_hash, event_round=2, budget_units=100_000))
    assert done.manifest["cost_units"] == plain.manifest["cost_units"] > 0
    assert done.manifest["branches"][ex.WITHOUT_EVENT] == plain.manifest["branches"][ex.WITHOUT_EVENT]
    assert done.manifest["branches"][ex.WITH_EVENT] != plain.manifest["branches"][ex.WITH_EVENT]
    assert "included_statement_ids" not in plain.manifest
    refused("WRONG_RESULT_KIND", lambda: read_event_fork(
        result_id="res1", out_dir=tmp_path / "out", audit=audit, **SCOPE))
    refused("WRONG_RESULT_KIND", lambda: read(audit, tmp_path / "out", "fork1"))


def test_a_retraction_stamps_the_result_whatever_was_left_out(audit, source, tmp_path):
    changed(audit, source, tmp_path / "out")
    new_item(audit, "r1")
    link(audit)
    assert read(audit, tmp_path / "out").stamps == (("e1", BASED_ON_RETRACTED_ITEM),)


@pytest.mark.parametrize("keep,expected", [("st2", ["st2"]), ("st1", [])])
def test_the_exception_flag_follows_the_statements_added(audit, source, tmp_path, keep, expected):
    view(audit, BOTH)
    confirm_statement(OWNER, expected_revision=0, reason_text="the notice itself", now=NOW, tenant_id="t1",
                      project_id="p1", study_id="s1", item_id="e1", statement_id="st2",
                      statement_text=SOLE.statement_text, sources=(PRIMARY,), judgments=(),
                      primary_source_id=PRIMARY.source_id, primary_reason_text="the official record", audit=audit)
    assert view(audit, BOTH).primary_source_exception_ids == ("st2",)
    done = changed(audit, source, tmp_path / "out", request=request_for(audit, inputs=(ref(keep),)))
    assert done.manifest["primary_source_exception_ids"] == expected


@pytest.mark.parametrize("underlying", [None, Option.CONTINUE, Option.FORK_FROM_EARLIER, Option.RERUN_FROM_START,
                                        Option.CHANGE_INPUTS])
def test_only_a_fork_from_the_event_runs_underneath(audit, source, tmp_path, underlying):
    no_gate(audit, source, tmp_path / "out", "OPTION_NOT_EXECUTABLE",
            request=request_for(audit, underlying=underlying))


def test_a_plain_fork_request_is_not_executed_by_this_call(audit, source, tmp_path):
    no_gate(audit, source, tmp_path / "out", "OPTION_NOT_EXECUTABLE",
            request=choice(Option.FORK_FROM_EVENT, view(audit, BOTH).evidence_hash, event_round=2))


@pytest.mark.parametrize("bad", [InputRef("st1", "internal"), ref("st9"), ref("st1", item="e2")])
def test_an_input_that_is_not_this_items_statement_is_refused(audit, source, tmp_path, bad):
    no_gate(audit, source, tmp_path / "out", "INPUT_NOT_A_STATEMENT",
            request=request_for(audit, inputs=(bad,)))


def test_choosing_every_statement_is_refused(audit, source, tmp_path):
    no_gate(audit, source, tmp_path / "out", "NOTHING_LEFT_OUT",
            request=request_for(audit, inputs=(ref("st1"), ref("st2"))))


@pytest.mark.parametrize("inputs", [[ref("st1")], ("st1",), (InputRef(["st1"], "internal"),)])
def test_malformed_inputs_are_refused(audit, source, tmp_path, inputs):
    no_gate(audit, source, tmp_path / "out", "INPUT_INVALID", request=request_for(audit, inputs=inputs))


def test_choosing_nothing_is_blocked_by_the_gate(audit, source, tmp_path):
    assert blocked(audit, source, tmp_path / "out", request_for(audit, inputs=())) == ("inputs_required",)


def test_a_repeated_choice_is_blocked_by_the_gate(audit, source, tmp_path):
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, inputs=(ref("st1"), ref("st1"))))
    assert failures == ("duplicate_input",)


def test_the_whole_recorded_list_must_still_be_given(audit, source, tmp_path):
    # Leaving a statement out is a choice in the request, never a shorter statement list.
    from agora.decision_cell import VerificationError

    request = request_for(audit, inputs=())
    with pytest.raises(VerificationError) as caught:
        changed(audit, source, tmp_path / "out", request=request, statements=(PAIR,))
    assert caught.value.code == "STATEMENTS_MISMATCH"
    assert recorded(audit) is None and left(tmp_path / "out") == []


def test_a_sensitive_statement_needs_the_grant_for_that_item(audit, source, tmp_path):
    register_item_statements(statements={"st1": PAIR.statement_text, "st2": SOLE.statement_text},
                             ratings={"st1": StatementRating("personal", "dana"), "st2": StatementRating("internal")},
                             expected_version=0, audit=audit, item_id="e1", **SCOPE)
    sensitive = ref("st1", "personal", "dana")
    request = request_for(audit, inputs=(sensitive,))
    missing = (f"data_owner_grant_missing:{sensitive.input_id}",)
    assert blocked(audit, source, tmp_path / "out", request) == missing
    # A grant for the same statement id of another item does not carry over.
    other = InputGrant("p1", "s1", statement_input_id("e2", "st1"), OWNER.subject_id, "dana")
    assert blocked(audit, source, tmp_path / "out", request, grants=(other,)) == missing
    grant = InputGrant("p1", "s1", sensitive.input_id, OWNER.subject_id, "dana")
    done = changed(audit, source, tmp_path / "out", request=request, grants=(grant,))
    assert done.manifest["included_statement_ids"] == ["st1"]


def test_item_and_statement_ids_cannot_run_together():
    assert statement_input_id("a:b", "c") != statement_input_id("a", "b:c")
    assert statement_input_id('a","b', "c") != statement_input_id("a", 'b","c')


def test_a_second_approval_covers_only_the_chosen_statements(audit, source, tmp_path):
    from agora.decision_cell import ProjectRecord, write_project_record

    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", second_approver_subject_id="second",
                                              requires_second_approval=True),
                         expected_version=1, audit=audit, now=NOW)
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, inputs=(ref("st1"),)))
    assert failures == ("second_approval_required",)
    fingerprint = [e for e in events(audit) if e["event_type"] == "decision_cell_option"][-1]["action_fingerprint"]
    approval = Escalation(EscalationStatus.APPROVED, "second", fingerprint)
    failures = blocked(audit, source, tmp_path / "out", request_for(audit, inputs=(ref("st2"),)),
                       escalation=approval)
    assert failures == ("second_approval_for_different_action",)
    done = changed(audit, source, tmp_path / "out", request=request_for(audit, inputs=(ref("st1"),)),
                   escalation=approval)
    assert done.manifest["action_fingerprint"] == fingerprint

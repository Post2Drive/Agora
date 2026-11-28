"""What each run result rests on, and the stamps that follow (DECISION_CELL_SPEC 2A). Synthetic data only."""
from __future__ import annotations

import pytest

from agora.decision_cell import (
    BASED_ON_RETRACTED_ITEM,
    CorrectionError,
    CorrectionKind,
    Option,
    load_run_result,
    record_run_result,
    run_result_stamps,
    run_results_resting_on,
)
from agora.decision_cell import run_results as rr
from tests.test_decision_cell_evidence import ask, choice, run_context, view
from tests.test_decision_cell_retractions import SCOPE, link, new_item
from tests.test_decision_cell_verification import audit, events  # noqa: F401

DIGEST = "ab" * 32
STAMPED = (("e1", BASED_ON_RETRACTED_ITEM),)


def gate_pass(audit, option=Option.CONTINUE, viewed="current", **kw):
    """Ask the gate about item e1 and return the id of the audit entry it wrote."""
    if viewed == "current":
        viewed = view(audit).evidence_hash
    ask(audit, choice(option, viewed), **(run_context() if option is Option.CONTINUE else {}), **kw)
    return events(audit)[-1]["event_id"]


@pytest.fixture
def run(audit):
    """An audit chain with an allowed run choice on e1, and items r1 and e2 registered."""
    entry = gate_pass(audit)
    assert events(audit)[-1]["decision"] == "allow"
    for item in ("r1", "e2"):
        new_item(audit, item)
    return audit, entry


def record(audit, gate, result="res1", **kw):
    kw.setdefault("result_hash", DIGEST)
    return record_run_result(result_id=result, gate_event_id=gate, audit=audit, **SCOPE, **kw)


def stamps(audit, result="res1"):
    return run_result_stamps(result_id=result, audit=audit, **SCOPE)


def loaded(audit, result="res1"):
    return load_run_result(result_id=result, audit=audit, **SCOPE)


def resting(audit, item="e1"):
    return [b.result_id for b in run_results_resting_on(item_id=item, audit=audit, **SCOPE)]


def refused(code, audit, call):
    before = len(events(audit))
    with pytest.raises(CorrectionError) as caught:
        call()
    assert caught.value.code == code, str(caught.value)
    assert len(events(audit)) == before


def test_the_choices_item_is_always_in_the_basis(run):
    audit, gate = run
    basis = record(audit, gate)
    assert basis == loaded(audit)
    assert (basis.item_ids, basis.parent_result_ids, basis.gate_event_id, basis.result_hash) == (
        ("e1",), (), gate, DIGEST)


def test_a_later_retraction_stamps_an_earlier_result_without_naming_its_items(run):
    audit, gate = run
    record(audit, gate)
    assert stamps(audit) == ()
    link(audit)
    assert stamps(audit) == STAMPED


def test_a_correction_does_not_stamp(run):
    audit, gate = run
    record(audit, gate)
    link(audit, kind=CorrectionKind.CORRECTION)
    assert stamps(audit) == ()


def test_other_items_are_stamped_too(run):
    audit, gate = run
    assert record(audit, gate, other_item_ids=("e2", "e2", "e1")).item_ids == ("e1", "e2")
    new_item(audit, "r3")
    link(audit, original="e2", by="r3")
    assert stamps(audit) == (("e2", BASED_ON_RETRACTED_ITEM),)


def test_a_child_inherits_every_ancestors_items(run):
    audit, gate = run
    record(audit, gate, "a", other_item_ids=("e2",))
    new_item(audit, "e3")
    record(audit, gate, "b", other_item_ids=("e3",))
    child = record(audit, gate, "c", parent_result_ids=("b", "a", "a"))
    assert child.parent_result_ids == ("a", "b") and child.item_ids == ("e1", "e2", "e3")
    grandchild = record(audit, gate, "d", parent_result_ids=("c",))
    assert grandchild.item_ids == ("e1", "e2", "e3")
    link(audit)
    assert stamps(audit, "d") == STAMPED
    assert resting(audit, "e2") == ["a", "c", "d"]


def test_affected_results_are_listed_in_order_and_per_study(run):
    audit, gate = run
    record(audit, gate, "z")
    record(audit, gate, "a", other_item_ids=("e2",))
    assert resting(audit) == ["z", "a"] and resting(audit, "e2") == ["a"] and resting(audit, "r1") == []
    other = dict(SCOPE, study_id="s2")
    assert run_results_resting_on(item_id="e1", audit=audit, **other) == ()
    assert load_run_result(result_id="z", audit=audit, **other) is None


def test_an_unrecorded_result_is_refused_not_reported_clean(run):
    audit, _ = run
    link(audit)
    refused("RESULT_NOT_RECORDED", audit, lambda: stamps(audit, "never"))


def test_a_basis_is_recorded_once(run):
    audit, gate = run
    first = record(audit, gate, other_item_ids=("e2",))
    refused("RESULT_ALREADY_RECORDED", audit, lambda: record(audit, gate))
    assert loaded(audit) == first


def test_a_missing_or_foreign_entry_is_not_a_run_choice(run):
    audit, _ = run
    refused("GATE_PASS_NOT_FOUND", audit, lambda: record(audit, "decision-cell-nope"))
    other = next(e["event_id"] for e in events(audit) if e["event_type"] == "decision_cell_item_statements")
    refused("GATE_PASS_NOT_FOUND", audit, lambda: record(audit, other))


def _forged(audit, event_id, **change):
    event = {"event_id": event_id, "event_type": "decision_cell_option", "operation": "CONTINUE",
             "decision": "allow", "subject_id": "x",
             "resource_ids": ["tenant:t1", "project:p1", "study:s1", "item:e1"]}
    audit.append({**event, **change})
    return event_id


@pytest.mark.parametrize("change,code", [
    (dict(event_type="something_else"), "NOT_A_RUN_CHOICE"),
    (dict(operation="IGNORE"), "NOT_A_RUN_CHOICE"),
    (dict(operation="HOLD"), "NOT_A_RUN_CHOICE"),
    (dict(decision="deny"), "GATE_PASS_BLOCKED"),
    (dict(resource_ids=[]), "GATE_PASS_UNLABELLED"),
    (dict(resource_ids=["tenant:t1", "project:p1", "study:s2", "item:e1"]), "GATE_PASS_OTHER_STUDY"),
    (dict(resource_ids=["tenant:t2", "project:p1", "study:s1", "item:e1"]), "GATE_PASS_OTHER_STUDY"),
])
def test_only_an_allowed_labelled_run_choice_in_this_study_counts(run, change, code):
    audit, _ = run
    entry = _forged(audit, "decision-cell-other", **change)
    refused(code, audit, lambda: record(audit, entry))


def test_an_entry_outside_the_gates_ids_is_not_a_choice(run):
    audit, _ = run
    entry = _forged(audit, "someone-elses-entry")
    refused("GATE_PASS_NOT_FOUND", audit, lambda: record(audit, entry))


def test_real_blocked_and_member_choices_have_no_result(run):
    audit, _ = run
    blocked = gate_pass(audit, viewed=None)
    refused("GATE_PASS_BLOCKED", audit, lambda: record(audit, blocked))
    ignored = gate_pass(audit, Option.IGNORE)
    refused("NOT_A_RUN_CHOICE", audit, lambda: record(audit, ignored))


def test_a_mistyped_item_is_refused(run):
    audit, gate = run
    refused("ITEM_NOT_REGISTERED", audit, lambda: record(audit, gate, other_item_ids=("e2", "typo")))


def test_a_parent_must_be_recorded_in_this_study(run):
    audit, gate = run
    refused("PARENT_NOT_RECORDED", audit, lambda: record(audit, gate, parent_result_ids=("missing",)))
    refused("PARENT_NOT_RECORDED", audit, lambda: record(audit, gate, parent_result_ids=("res1",)))


@pytest.mark.parametrize("kw,code", [
    (dict(other_item_ids=["e2"]), "BASIS_INVALID"),
    (dict(parent_result_ids="a"), "BASIS_INVALID"),
    (dict(other_item_ids=(" e2",)), "ID_INVALID"),
    (dict(parent_result_ids=("",)), "ID_INVALID"),
    (dict(result_hash="AB" * 32), "RESULT_HASH_INVALID"),
    (dict(result_hash="ab" * 31), "RESULT_HASH_INVALID"),
    (dict(result_hash=None), "RESULT_HASH_INVALID"),
    (dict(parent_result_ids=tuple(f"p{i}" for i in range(21))), "BASIS_TOO_LARGE"),
])
def test_unusable_input_records_nothing(run, kw, code):
    audit, gate = run
    refused(code, audit, lambda: record(audit, gate, **kw))


def test_a_basis_over_the_limit_is_refused_not_cut(run, monkeypatch):
    audit, gate = run
    monkeypatch.setattr(rr, "MAX_BASIS_ITEMS", 1)
    refused("BASIS_TOO_LARGE", audit, lambda: record(audit, gate, other_item_ids=("e2",)))


@pytest.mark.parametrize("change", [
    dict(event_type="something_else"), dict(decision="deny"), dict(count=2),
    dict(resource_ids=["tenant:t1", "project:p1", "study:s1", "result:other", "gate:g", "basis:e1"]),
    dict(resource_ids=["tenant:t1", "project:p1", "study:s1", "result:res1", "gate:g"], count=0),
    dict(resource_ids=["tenant:t9", "project:p1", "study:s1", "result:res1", "gate:g", "basis:e1"]),
])
def test_a_forged_record_is_refused(run, change):
    audit, _ = run
    event = {"event_id": rr._event_id("t1", "p1", "s1", "res1"), "event_type": "decision_cell_run_result",
             "decision": "allow", "subject_id": "x", "count": 1, "result_hash": DIGEST,
             "resource_ids": ["tenant:t1", "project:p1", "study:s1", "result:res1", "gate:g", "basis:e1"]}
    audit.append({**event, **change})
    refused("STORE_INCONSISTENT", audit, lambda: stamps(audit))


def test_an_unanchored_chain_is_refused(run):
    audit, gate = run
    record(audit, gate)
    audit.chain.append({"event_id": "unanchored", "event_type": "x"})
    for call in (lambda: loaded(audit), lambda: resting(audit), lambda: stamps(audit)):
        with pytest.raises(CorrectionError) as caught:
            call()
        assert caught.value.code == "AUDIT_UNANCHORED"
    with pytest.raises(CorrectionError):
        record(audit, gate, "res2")

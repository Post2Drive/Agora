"""The 15-minute response window (DECISION_CELL_SPEC section 3). Synthetic principals only."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decision_cell import (
    DecisionCellError, Escalation, EscalationStatus, Option, OptionRequest, ProjectRecord,
    ProjectRecordError, ResponseWindowError, StudyState, load_project_record, load_response_window,
    open_response_window, respond_to_item, sweep_response_windows, write_project_record,
)
from agora.decision_cell import response_window as rw
from agora.principal import SyntheticFixtureAdapter

T0 = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)
LIMIT = timedelta(minutes=15)
LATE = T0 + LIMIT + timedelta(seconds=30)
APPROVED = "a" * 64
STUDY = StudyState("s1", 3)


def _fx(subject, roles=("approver",), **kw):
    base = {"subject_id": subject, "tenant_id": "t1", "project_ids": ["p1"], "roles": list(roles),
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


AD = SyntheticFixtureAdapter({
    "owner": _fx("owner"), "member": _fx("mia", ["operator"]), "backup": _fx("bo", ["operator"]),
    "outsider": _fx("eve", project_ids=["p2"]),
})
OWNER = AD.issue("owner")
AD2 = SyntheticFixtureAdapter({"owner2": _fx("owner", project_ids=["p2"])})


@pytest.fixture
def audit(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.db")
    anchors = AnchorStore(tmp_path / "audit.anchor", "c1")
    bootstrap_anchor(chain, anchors, performed_by="test")
    writer = AnchoredAuditChain(chain, anchors)
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner"), expected_version=0,
                         audit=writer, now=T0)
    yield writer
    writer.close()


def ids(item="n1", study="s1", project="p1"):
    return {"tenant_id": "t1", "project_id": project, "study_id": study, "item_id": item}


def opened(audit, **kw):
    return open_response_window(**ids(**kw), audit=audit, now=T0)


def load(audit, **kw):
    return load_response_window(**ids(**kw), audit=audit)


def sweep(audit, now, lookup=lambda study: APPROVED, project="p1"):
    return sweep_response_windows(tenant_id="t1", project_id=project, audit=audit,
                                  approved_result_hash_for=lookup, now=now)


def respond(audit, principal=OWNER, option=Option.IGNORE, now=T0 + timedelta(minutes=2),
            lookup=lambda study: APPROVED, item="n1", **kw):
    request = OptionRequest(option=option, event_id=item, reason="reviewed", budget_units=0)
    return respond_to_item(principal, request, tenant_id="t1", project_id="p1", study=STUDY,
                           audit=audit, approved_result_hash_for=lookup, now=now, **kw)


def events(audit, kind=None):
    rows = [json.loads(r[0]) for r in
            audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]
    return [e for e in rows if kind is None or e["event_type"] == f"decision_cell_window_{kind}"]


def refused(code, call):
    with pytest.raises(ResponseWindowError) as caught:
        call()
    assert caught.value.code == code, str(caught.value)


def name_backup(audit, backup="bo"):
    return write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", backup_contact_subject_id=backup),
                                expected_version=1, audit=audit, now=T0)


# -- opening ------------------------------------------------------------------

def test_open_window_has_a_fifteen_minute_deadline(audit):
    window = opened(audit)
    assert window.deadline == T0 + LIMIT and window.status == "OPEN"
    assert load(audit) == window
    assert load(audit, item="other") is None


def test_a_window_cannot_be_reopened_to_restart_its_clock(audit):
    opened(audit)
    refused("WINDOW_EXISTS", lambda: open_response_window(**ids(), audit=audit, now=T0 + LIMIT))
    assert load(audit).opened_at == T0


def test_a_window_needs_a_recorded_owner(audit):
    refused("NO_PROJECT_RECORD", lambda: opened(audit, project="unrecorded"))
    assert events(audit, "opened") == []


@pytest.mark.parametrize("bad", ["", " n1", "n1\n", None])
def test_ids_must_be_exact(audit, bad):
    refused("ID_INVALID", lambda: opened(audit, item=bad))


def test_a_naive_clock_is_refused(audit):
    refused("CLOCK_INVALID", lambda: open_response_window(**ids(), audit=audit, now=datetime(2026, 11, 26)))
    opened(audit)
    refused("CLOCK_INVALID", lambda: sweep(audit, datetime(2026, 11, 27)))


def test_a_plain_chain_is_refused(audit):
    with pytest.raises(ProjectRecordError):
        open_response_window(**ids(), audit=audit.chain, now=T0)


# -- holding ------------------------------------------------------------------

def test_nothing_is_held_before_the_deadline(audit):
    opened(audit)
    assert sweep(audit, T0 + LIMIT - timedelta(milliseconds=1)) == ()
    assert load(audit).status == "OPEN" and events(audit, "held") == []


def test_expiry_holds_the_last_approved_result_and_records_elapsed_time(audit):
    opened(audit)
    (held,) = sweep(audit, T0 + LIMIT)
    assert (held.status, held.hold_reason) == ("HELD", rw.HELD_LAST_APPROVED)
    assert held.approved_result_hash == APPROVED and held.held_after_ms == 900_000
    assert held.alert_due_subject_ids == ("owner",)  # no backup is inferred
    assert load(audit) == held
    (event,) = events(audit, "held")
    assert event["approved_result_hash"] == APPROVED and event["duration_ms"] == 900_000
    assert "alert:owner" in event["resource_ids"] and audit.verify()["valid"]


def test_a_second_sweep_does_not_hold_or_alert_again(audit):
    opened(audit)
    sweep(audit, LATE)
    assert sweep(audit, LATE + LIMIT) == ()
    assert len(events(audit, "held")) == 1


def test_only_a_named_backup_is_also_alerted_and_gains_no_authority(audit):
    name_backup(audit)
    opened(audit)
    (held,) = sweep(audit, LATE)
    assert held.alert_due_subject_ids == ("owner", "bo")
    result, _ = respond(audit, AD.issue("backup"), Option.RERUN_FROM_START, now=LATE, branch_cost_units=1)
    assert not result.executable and "not_designated_approver" in result.failures


def test_without_an_approved_result_nothing_is_publishable(audit):
    opened(audit)
    (held,) = sweep(audit, LATE, lambda study: None)
    assert (held.hold_reason, held.approved_result_hash) == (rw.HELD_NO_APPROVED, None)


def _boom(study):
    raise RuntimeError("result store down")


@pytest.mark.parametrize("lookup", [_boom, lambda s: "latest", lambda s: "A" * 64, lambda s: 5,
                                    lambda s: APPROVED + "\n"])
def test_a_broken_result_lookup_still_holds_and_alerts_but_publishes_nothing(audit, lookup):
    opened(audit)
    (held,) = sweep(audit, LATE, lookup)
    assert (held.hold_reason, held.approved_result_hash) == (rw.HELD_LOOKUP_FAILED, None)
    assert held.alert_due_subject_ids == ("owner",)


def test_each_study_gets_its_own_approved_result_and_projects_are_separate(audit):
    write_project_record(AD2.issue("owner2"), ProjectRecord("p2", "t1", "owner"), expected_version=0,
                         audit=audit, now=T0)
    opened(audit)
    opened(audit, study="s2")
    opened(audit, project="p2")
    held = sweep(audit, LATE, {"s1": "1" * 64, "s2": "2" * 64}.get)
    assert {(w.study_id, w.approved_result_hash) for w in held} == {("s1", "1" * 64), ("s2", "2" * 64)}
    assert load(audit, project="p2").status == "OPEN"


# -- answering ----------------------------------------------------------------

def test_an_allowed_choice_in_time_answers_the_window(audit):
    opened(audit)
    result, window = respond(audit, AD.issue("member"))
    assert result.executable and window.status == "ANSWERED"
    assert (window.answered_by_subject_id, window.answered_option, window.answered_after_ms) == (
        "mia", "IGNORE", 120_000)
    assert sweep(audit, LATE) == () and events(audit, "held") == []


@pytest.mark.parametrize("principal, option", [
    (None, Option.IGNORE), (AD.issue("outsider"), Option.IGNORE),
    (AD.issue("member"), Option.RERUN_FROM_START),
])
def test_a_refused_attempt_does_not_stop_the_clock(audit, principal, option):
    opened(audit)
    result, window = respond(audit, principal, option, branch_cost_units=1)
    assert not result.executable and window.status == "OPEN"
    assert [w.status for w in sweep(audit, LATE)] == ["HELD"]


def test_comparing_does_not_answer(audit):
    opened(audit)
    result, window = respond(audit, option=Option.COMPARE)
    assert result.executable and window.status == "OPEN"


def test_escalating_does_not_answer(audit):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", second_approver_subject_id="sam"),
                         expected_version=1, audit=audit, now=T0)
    opened(audit)
    result, window = respond(audit, option=Option.ESCALATE, escalation=Escalation(EscalationStatus.NONE))
    assert result.executable and window.status == "OPEN"


@pytest.mark.parametrize("now", [T0 + LIMIT, LATE])
def test_a_late_answer_cannot_erase_the_hold_or_the_alert(audit, now):
    opened(audit)  # no sweep ran: the answer itself must record the hold first
    result, window = respond(audit, now=now)
    assert result.executable and window.status == "ANSWERED_AFTER_HOLD"
    assert window.alert_due_subject_ids == ("owner",) and window.approved_result_hash == APPROVED
    (answer,) = events(audit, "answered")
    assert answer["reason"] == "answered_after_hold"
    order = [e["event_type"] for e in events(audit)]
    assert order.index("decision_cell_window_held") < order.index("decision_cell_option")


def test_a_late_refused_attempt_still_records_the_hold(audit):
    opened(audit)
    result, window = respond(audit, AD.issue("outsider"), now=LATE)
    assert not result.executable and window.status == "HELD"


def test_only_the_first_answer_is_recorded(audit):
    opened(audit)
    respond(audit)
    result, window = respond(audit, AD.issue("member"), now=LATE)
    assert result.executable and window.answered_by_subject_id == "owner" and window.status == "ANSWERED"
    assert len(events(audit, "answered")) == 1 and events(audit, "held") == []


def test_an_item_with_no_window_cannot_be_answered(audit):
    refused("NO_WINDOW", lambda: respond(audit))
    assert [e["event_type"] for e in events(audit)] == ["decision_cell_project_record"]


def test_a_clock_before_the_opening_is_refused(audit):
    opened(audit)
    refused("CLOCK_INVALID", lambda: respond(audit, now=T0 - timedelta(seconds=1)))


def test_the_caller_cannot_supply_the_project_record(audit):
    opened(audit)
    with pytest.raises(DecisionCellError):
        respond(audit, record=ProjectRecord("p1", "t1", "mia"))
    assert load(audit).status == "OPEN"


# -- races --------------------------------------------------------------------

def test_an_answer_landing_during_a_sweep_wins_and_no_hold_is_written(audit):
    opened(audit)

    def answer_during_lookup(study):
        respond(audit, now=T0 + LIMIT - timedelta(seconds=1))
        return APPROVED

    assert sweep(audit, LATE, answer_during_lookup) == ()
    assert load(audit).status == "ANSWERED" and events(audit, "held") == []
    assert audit.verify()["valid"]


def test_a_hold_landing_during_an_in_time_answer_refuses_that_answer(audit, monkeypatch):
    opened(audit)
    real = rw.request_project_option

    def hold_then_judge(*args, **kwargs):
        sweep(audit, LATE)  # a sweeper with a later clock gets in between
        return real(*args, **kwargs)

    monkeypatch.setattr(rw, "request_project_option", hold_then_judge)
    refused("WINDOW_CHANGED", lambda: respond(audit))
    assert load(audit).status == "HELD" and events(audit, "answered") == []
    monkeypatch.setattr(rw, "request_project_option", real)
    assert respond(audit)[1].status == "ANSWERED_AFTER_HOLD"


def test_two_sweepers_record_one_hold(audit):
    opened(audit)
    inner = []

    def sweep_inside(study):
        if not inner:
            inner.append(None)
            inner[0] = sweep(audit, LATE)
        return APPROVED

    outer = sweep(audit, LATE, sweep_inside)
    assert outer == inner[0] and len(events(audit, "held")) == 1


# -- integrity ----------------------------------------------------------------

def test_an_unanchored_tail_stops_reads_sweeps_and_answers(audit):
    opened(audit)
    audit.chain.append({"event_id": "stray"})
    for call in (lambda: load(audit), lambda: sweep(audit, LATE)):
        refused("AUDIT_UNANCHORED", call)
    refused("AUDIT_UNANCHORED", lambda: respond(audit))


@pytest.mark.parametrize("change", [
    {"event_type": "decision_cell_window_answered"},
    {"resource_ids": ["tenant:t1", "project:p1", "study:s1", "item:another"]},
    {"resource_ids": ["tenant:t1", "project:p1", "study:s1"]},
])
def test_a_window_event_that_does_not_match_its_scope_is_refused(audit, change):
    key = rw._key_hash("t1", "p1", "s1", "n1")
    audit.append({"event_id": rw._event_id("opened", key), "event_type": "decision_cell_window_opened",
                  "resource_ids": rw._scope("t1", "p1", "s1", "n1"), **change})
    refused("STORE_INCONSISTENT", lambda: sweep(audit, LATE))


def test_a_hold_without_an_opening_is_refused(audit):
    key = rw._key_hash("t1", "p1", "s1", "n1")
    audit.append({"event_id": rw._event_id("held", key), "event_type": "decision_cell_window_held",
                  "resource_ids": rw._scope("t1", "p1", "s1", "n1")})
    refused("STORE_INCONSISTENT", lambda: load(audit))


def test_a_failed_anchor_write_is_reported_and_blocks_further_use(audit, monkeypatch):
    opened(audit)

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(audit.anchors, "advance", broken)
    refused("AUDIT_ANCHOR_WRITE_FAILED", lambda: sweep(audit, LATE))
    monkeypatch.undo()
    refused("AUDIT_UNANCHORED", lambda: load(audit))


# -- backup contact in the project record -------------------------------------

def test_the_backup_contact_round_trips_and_can_be_removed(audit):
    name_backup(audit)
    assert load_project_record(tenant_id="t1", project_id="p1", audit=audit
                               ).record.backup_contact_subject_id == "bo"
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner"), expected_version=2, audit=audit, now=T0)
    opened(audit)
    assert sweep(audit, LATE)[0].alert_due_subject_ids == ("owner",)


def test_a_record_without_a_backup_keeps_its_previous_stored_form(audit):
    (body,) = [r[0] for r in audit.chain.db.execute("SELECT body_json FROM decision_cell_project_records")]
    assert "backup" not in body


@pytest.mark.parametrize("bad", ["owner", "", " bo", 7])
def test_an_invalid_backup_contact_is_refused(audit, bad):
    with pytest.raises(ProjectRecordError) as caught:
        name_backup(audit, bad)
    assert caught.value.code == "RECORD_INVALID"


def test_the_alert_list_uses_the_record_current_at_expiry(audit):
    opened(audit)
    name_backup(audit)
    assert sweep(audit, LATE)[0].alert_due_subject_ids == ("owner", "bo")

"""Decision-cell option gate (DECISION_CELL_SPEC sections 3 and 3A). Synthetic principals only."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from agora import protection
from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decision_cell import (
    DecisionCellError, Escalation, EscalationStatus, InputGrant, InputRef, Option, OptionRequest,
    ProjectRecord, StudyState, evaluate_option, request_option,
)
from agora.decision_cell import MAX_RECHECK
from agora.decision_cell.options import _sha
from agora.principal import Principal, SyntheticFixtureAdapter

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(subject, roles, **kw):
    base = {"subject_id": subject, "tenant_id": "t1", "project_ids": ["p1"], "roles": roles,
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


AD = SyntheticFixtureAdapter({
    "owner": _fx("owner", ["approver"]),
    "other_approver": _fx("a2", ["approver"]),
    "reader": _fx("reader", ["reader"]),
    "reviewer": _fx("reviewer", ["reviewer"]),
    "operator": _fx("op", ["operator"]),
    "owner_no_role": _fx("owner", ["operator"]),
    "owner_low": _fx("owner", ["approver"], assurance="STANDARD"),
    "outsider": _fx("owner", ["approver"], project_ids=["p2"]),
    "other_tenant": _fx("owner", ["approver"], tenant_id="t2"),
    "expired": _fx("owner", ["approver"], expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
})
OWNER = AD.issue("owner")
RECORD = ProjectRecord("p1", "t1", "owner")
STUDY = StudyState("s1", current_round=10)
MEMBER = [Option.IGNORE, Option.HOLD, Option.COMPARE]
RUNS = [Option.CONTINUE, Option.FORK_FROM_EVENT, Option.FORK_FROM_EARLIER, Option.RERUN_FROM_START]


def req(option, **kw):
    base = {"option": option, "event_id": "ev-1", "reason": "because", "budget_units": 1000,
            "event_round": 6 if option is not Option.CONTINUE else None,
            "from_round": 3 if option is Option.FORK_FROM_EARLIER else None,
            "recheck_at": NOW + timedelta(hours=1) if option is Option.HOLD else None}
    base.update(kw)
    return OptionRequest(**base)


def gate(request, principal=OWNER, **kw):
    context = {"record": RECORD, "study": STUDY, "branch_cost_units": 100,
               "snapshot_verifies": lambda study, r: True, "now": NOW}
    context.update(kw)
    return evaluate_option(principal, request, **context)


@pytest.mark.parametrize("option", RUNS)
def test_owner_can_run_each_run_option(option):
    result = gate(req(option))
    assert result.executable and result.failures == ()


@pytest.mark.parametrize("option", MEMBER)
@pytest.mark.parametrize("who", ["reader", "reviewer", "operator", "owner"])
def test_any_member_can_use_member_options(option, who):
    assert gate(req(option), AD.issue(who), branch_cost_units=None, snapshot_verifies=None).executable


@pytest.mark.parametrize("who,reason", [("outsider", "cross_scope"), ("other_tenant", "cross_tenant"),
                                        ("expired", "principal_expired")])
@pytest.mark.parametrize("option", [Option.IGNORE, Option.CONTINUE])
def test_non_members_get_nothing(who, reason, option):
    assert f"not_project_member:{reason}" in gate(req(option), AD.issue(who)).failures


def test_missing_and_hand_built_principals_are_refused():
    forged = Principal("owner", "t1", frozenset({"p1"}), frozenset({"approver"}),
                       OWNER.assurance, OWNER.issuer, EXP)
    assert not gate(req(Option.IGNORE), None).executable
    assert "not_project_member:principal_not_adapter_issued" in gate(req(Option.IGNORE), forged).failures


@pytest.mark.parametrize("option", RUNS)
@pytest.mark.parametrize("who,code", [
    ("reader", "approver_required:role_not_permitted"),
    ("owner_no_role", "approver_required:role_not_permitted"),
    ("owner_low", "approver_required:assurance_insufficient"),
    ("other_approver", "not_designated_approver"),
])
def test_run_options_need_the_designated_approver(option, who, code):
    result = gate(req(option), AD.issue(who))
    assert not result.executable and code in result.failures


def test_delegate_works_only_when_recorded_and_still_needs_the_role():
    record = replace(RECORD, delegate_subject_ids=frozenset({"a2", "reader"}))
    assert gate(req(Option.CONTINUE), AD.issue("other_approver"), record=record).executable
    assert not gate(req(Option.CONTINUE), AD.issue("reader"), record=record).executable


@pytest.mark.parametrize("delegates", ["a2-and-others", ["a2"], None])
def test_delegates_must_be_a_set_so_text_cannot_match_by_substring(delegates):
    record = replace(RECORD, delegate_subject_ids=delegates)
    result = gate(req(Option.CONTINUE), AD.issue("other_approver"), record=record)
    assert "not_designated_approver" in result.failures


@pytest.mark.parametrize("option,wanted", [(Option.CONTINUE, 10), (Option.FORK_FROM_EVENT, 6),
                                           (Option.FORK_FROM_EARLIER, 3)])
def test_snapshot_is_checked_for_the_right_round(option, wanted):
    seen = []
    assert gate(req(option), snapshot_verifies=lambda s, r: seen.append((s, r)) or True).executable
    assert seen == [("s1", wanted)]


def _boom(study, r):
    raise OSError("unreadable")


@pytest.mark.parametrize("probe", [None, lambda s, r: False, lambda s, r: 1, lambda s, r: "yes", _boom])
@pytest.mark.parametrize("option", RUNS[:3])
def test_unverified_snapshot_blocks_the_option(option, probe):
    assert "snapshot_unavailable" in gate(req(option), snapshot_verifies=probe).failures


def test_rerun_needs_no_snapshot():
    assert gate(req(Option.RERUN_FROM_START), snapshot_verifies=None).executable


@pytest.mark.parametrize("bad", [None, -1, 11, True, 2.0])
def test_bad_event_round_is_refused(bad):
    assert "snapshot_round_invalid" in gate(req(Option.FORK_FROM_EVENT, event_round=bad)).failures


@pytest.mark.parametrize("from_round", [6, 7, None])
def test_earlier_fork_must_be_before_the_event(from_round):
    result = gate(req(Option.FORK_FROM_EARLIER, from_round=from_round))
    assert "from_round_not_before_event" in result.failures


def test_stray_from_round_is_refused():
    assert "from_round_not_allowed" in gate(req(Option.FORK_FROM_EVENT, from_round=2)).failures


@pytest.mark.parametrize("option,cost", [(Option.CONTINUE, 100), (Option.FORK_FROM_EVENT, 200),
                                         (Option.FORK_FROM_EARLIER, 200),
                                         (Option.RERUN_FROM_START, 100)])
def test_budget_uses_branch_count_and_exact_confirmation(option, cost):
    assert gate(req(option, budget_units=cost)).executable
    over = req(option, budget_units=cost - 1)
    assert "budget_confirmation_required" in gate(over).failures
    for wrong in (cost - 1, cost + 1, float(cost), True):
        assert not gate(replace(over, confirmed_cost_units=wrong)).executable
    ok = gate(replace(over, confirmed_cost_units=cost))
    assert ok.executable and ok.over_budget and ok.cost_units == cost


@pytest.mark.parametrize("cost", [None, 0, -5, 1.5, float("nan"), True])
def test_unusable_cost_estimate_blocks(cost):
    assert "cost_estimate_missing" in gate(req(Option.CONTINUE), branch_cost_units=cost).failures


@pytest.mark.parametrize("budget", [None, -1, float("inf"), True])
def test_unusable_budget_blocks(budget):
    assert "budget_invalid" in gate(req(Option.CONTINUE, budget_units=budget)).failures


@pytest.mark.parametrize("field,code", [("reason", "reason_missing"), ("event_id", "event_missing")])
@pytest.mark.parametrize("option", [Option.IGNORE, Option.CONTINUE])
def test_every_choice_needs_reason_and_event(option, field, code):
    assert code in gate(req(option, **{field: "  "})).failures


def change(*inputs, underlying=Option.FORK_FROM_EVENT, **kw):
    return req(Option.CHANGE_INPUTS, underlying=underlying, inputs=tuple(inputs), **kw)


PUBLIC = InputRef("news-1", "public")
SENSITIVE = InputRef("hr-1", "sensitive", "dpo")
GRANT = InputGrant("p1", "s1", "hr-1", "owner", "dpo")


def test_change_inputs_takes_the_underlying_rules():
    assert gate(change(PUBLIC)).cost_units == 200
    assert "snapshot_unavailable" in gate(change(PUBLIC), snapshot_verifies=None).failures
    assert not gate(change(PUBLIC), AD.issue("reader")).executable


@pytest.mark.parametrize("underlying", [None, Option.COMPARE, Option.CHANGE_INPUTS, Option.IGNORE])
def test_change_inputs_needs_a_run_underneath(underlying):
    assert "underlying_run_required" in gate(change(PUBLIC, underlying=underlying)).failures


def test_inputs_cannot_ride_on_a_plain_run():
    assert "inputs_not_allowed" in gate(req(Option.CONTINUE, inputs=(SENSITIVE,))).failures
    assert "underlying_not_allowed" in gate(req(Option.IGNORE, underlying=Option.CONTINUE)).failures


def test_change_inputs_needs_distinct_known_inputs():
    assert "inputs_required" in gate(change()).failures
    assert "duplicate_input" in gate(change(PUBLIC, PUBLIC)).failures
    assert "input_sensitivity_unknown" in gate(change(InputRef("x", "secretish"))).failures


@pytest.mark.parametrize("level", ["personal", "sensitive"])
def test_sensitive_input_needs_the_exact_owner_grant(level):
    item = InputRef("hr-1", level, "dpo")
    assert "data_owner_grant_missing:hr-1" in gate(change(item)).failures
    assert gate(change(item), grants=(GRANT,)).executable
    for wrong in (replace(GRANT, project_id="p2"), replace(GRANT, study_id="s2"),
                  replace(GRANT, input_id="hr-2"), replace(GRANT, grantee_subject_id="a2"),
                  replace(GRANT, granted_by_subject_id="owner")):
        assert not gate(change(item), grants=(wrong,)).executable
    assert not gate(change(InputRef("hr-1", level)), grants=(GRANT,)).executable


@pytest.mark.parametrize("option", [*MEMBER, Option.CONTINUE, Option.ESCALATE])
def test_pending_escalation_blocks_everything(option):
    record = replace(RECORD, second_approver_subject_id="second")
    pending = Escalation(EscalationStatus.PENDING)
    assert "escalation_pending" in gate(req(option), record=record, escalation=pending).failures


def test_escalate_needs_a_named_second_approver():
    assert "second_approver_not_named" in gate(req(Option.ESCALATE), AD.issue("reader")).failures
    record = replace(RECORD, second_approver_subject_id="second")
    assert gate(req(Option.ESCALATE), AD.issue("reader"), record=record).executable


def test_rejected_escalation_blocks_runs_but_not_member_options():
    rejected = Escalation(EscalationStatus.REJECTED, "second")
    assert "escalation_rejected" in gate(req(Option.CONTINUE), escalation=rejected).failures
    assert gate(req(Option.HOLD), escalation=rejected).executable


def test_second_approval_is_required_independent_and_action_bound():
    record = replace(RECORD, second_approver_subject_id="second", requires_second_approval=True)
    request = req(Option.FORK_FROM_EVENT)
    first = gate(request, record=record)
    assert first.failures == ("second_approval_required",)
    ok = Escalation(EscalationStatus.APPROVED, "second", first.action_fingerprint)
    assert gate(request, record=record, escalation=ok).executable
    wrong_person = replace(ok, answered_by_subject_id="a2")
    assert "second_approval_not_independent" in gate(request, record=record, escalation=wrong_person).failures
    self_record = replace(record, second_approver_subject_id="owner")
    own = Escalation(EscalationStatus.APPROVED, "owner",
                     gate(request, record=self_record).action_fingerprint)
    assert "second_approval_not_independent" in gate(request, record=self_record, escalation=own).failures
    for changed in (replace(request, event_id="ev-2"), replace(request, event_round=5),
                    req(Option.CONTINUE)):
        assert "second_approval_for_different_action" in gate(changed, record=record, escalation=ok).failures
    assert not gate(request, record=record, escalation=ok, branch_cost_units=101).executable
    assert not gate(request, record=record, escalation=ok,
                    study=replace(STUDY, current_round=11)).executable
    assert not gate(request, record=record, escalation=ok,
                    study=replace(STUDY, study_id="s2")).executable


@pytest.mark.parametrize("switch", [True, None])
def test_kill_switch_stops_runs_only(switch):
    study = replace(STUDY, kill_switch=switch)
    assert "kill_switch_on" in gate(req(Option.CONTINUE), study=study).failures
    assert gate(req(Option.IGNORE), study=study).executable


def test_all_failures_are_reported_together():
    result = gate(req(Option.FORK_FROM_EVENT, budget_units=0), AD.issue("reader"), snapshot_verifies=None)
    assert {"approver_required:role_not_permitted", "snapshot_unavailable",
            "budget_confirmation_required"} <= set(result.failures)


@pytest.mark.parametrize("second", [InputRef("hr-1", "sensitive"), InputRef(None, "public")])
def test_malformed_input_lists_are_refused_not_crashed(second):
    assert not gate(change(SENSITIVE, second)).executable


def _events(chain):
    return [json.loads(r[0]) for r in chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]


def test_allowed_and_blocked_attempts_are_both_in_the_anchored_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    writer = AnchoredAuditChain(chain, AnchorStore(tmp_path / "anchor.jsonl", "c1"))
    bootstrap_anchor(chain, AnchorStore(tmp_path / "anchor.jsonl", "c1"), performed_by="test")
    context = {"record": RECORD, "study": STUDY, "branch_cost_units": 100,
               "snapshot_verifies": lambda s, r: True, "now": NOW}
    allowed = request_option(OWNER, req(Option.CONTINUE, reason="private words"), audit=writer, **context)
    blocked = request_option(AD.issue("reader"), req(Option.CONTINUE), audit=writer, **context)
    assert allowed.executable and not blocked.executable
    events = _events(chain)[-2:]
    assert [e["decision"] for e in events] == ["allow", "deny"]
    assert events[0]["count"] == 100 and events[0]["reason"] == "gate_passed"
    assert events[1]["reason"] == "approver_required,not_designated_approver"
    assert events[0]["action_fingerprint"] == allowed.action_fingerprint
    assert len(events[0]["reason_text_hash"]) == 64 and "private words" not in json.dumps(events)
    assert "[REDACTED]" not in json.dumps(events)
    chain.close()


def test_protected_mode_refuses_unanchored_and_missing_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
    chain = AuditChainStore(tmp_path / "chain.sqlite3")
    context = {"record": RECORD, "study": STUDY, "now": NOW}
    with pytest.raises(DecisionCellError):
        request_option(OWNER, req(Option.IGNORE), audit=chain, **context)
    with pytest.raises(DecisionCellError, match="audit writer is required"):
        request_option(OWNER, req(Option.IGNORE), audit=None, **context)
    assert _events(chain) == []
    chain.close()


def test_failed_audit_write_means_no_result(monkeypatch):
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)

    class Broken:
        def append(self, event):
            raise OSError("disk full")

    with pytest.raises(DecisionCellError, match="could not be recorded"):
        request_option(OWNER, req(Option.IGNORE), audit=Broken(), record=RECORD, study=STUDY, now=NOW)


# -- HOLD re-check time -------------------------------------------------------

@pytest.mark.parametrize("value, code", [
    (None, "recheck_time_required"),
    ("2026-11-26T13:00:00+00:00", "recheck_time_invalid"),
    (datetime(2026, 11, 26, 13), "recheck_time_invalid"),
    (datetime.max.replace(tzinfo=timezone(-timedelta(hours=1))), "recheck_time_invalid"),
    (NOW, "recheck_time_not_in_future"),
    (NOW - timedelta(seconds=1), "recheck_time_not_in_future"),
    (NOW + MAX_RECHECK + timedelta(microseconds=1), "recheck_time_too_far"),
])
def test_a_hold_needs_a_usable_future_recheck_time(value, code):
    result = gate(req(Option.HOLD, recheck_at=value))
    assert not result.executable and result.failures == (code,)


@pytest.mark.parametrize("ahead", [timedelta(microseconds=1), MAX_RECHECK])
def test_the_recheck_time_limits_are_inclusive_of_the_maximum(ahead):
    assert gate(req(Option.HOLD, recheck_at=NOW + ahead)).executable


def test_a_hold_is_judged_against_the_real_clock_when_none_is_given():
    past = gate(req(Option.HOLD, recheck_at=datetime(2000, 1, 1, tzinfo=timezone.utc)), now=None)
    assert "recheck_time_not_in_future" in past.failures


@pytest.mark.parametrize("option", [o for o in Option if o is not Option.HOLD])
def test_only_a_hold_may_carry_a_recheck_time(option):
    assert "recheck_not_allowed" in gate(req(option, recheck_at=NOW + timedelta(hours=1))).failures


def test_the_recheck_time_is_part_of_the_action_fingerprint():
    one = gate(req(Option.HOLD, recheck_at=NOW + timedelta(hours=1)))
    two = gate(req(Option.HOLD, recheck_at=NOW + timedelta(hours=2)))
    same = gate(req(Option.HOLD, recheck_at=(NOW + timedelta(hours=1)).astimezone(
        timezone(timedelta(hours=5, minutes=30)))))
    assert one.action_fingerprint != two.action_fingerprint
    assert one.action_fingerprint == same.action_fingerprint


def test_other_actions_keep_the_fingerprint_they_had_before_the_recheck_field():
    expected = _sha({
        "project_id": "p1", "tenant_id": "t1", "study_id": "s1", "current_round": 10, "event_id": "ev-1",
        "option": Option.IGNORE, "underlying": None, "event_round": 6, "from_round": None,
        "inputs": [], "cost_units": 0,
    })
    assert gate(req(Option.IGNORE)).action_fingerprint == expected

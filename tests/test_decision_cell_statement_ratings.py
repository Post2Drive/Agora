"""Recorded sensitivity and data owner of each statement, and the grant check that uses them. Synthetic data."""
from __future__ import annotations

from datetime import timedelta

import pytest

from agora.decision_cell import (
    Escalation, EscalationStatus, InputGrant, InputRef, Option, OptionRequest, ProjectRecord,
    StatementRating, StatementSetError, execute_earlier_fork, execute_event_fork,
    execute_rerun, item_evidence,
    load_item_statements, register_item_statements, request_labelled_option, request_option,
    request_project_option, respond_to_item, statement_input_id, write_project_record,
)
from agora.decision_cell import evidence as ev
from agora.decision_cell import options as gate_module
from agora.decision_cell.statements import wording_hash
from tests.test_decision_cell_evidence import KW, PAIR, SOLE, STUDY, choice, run_context
from tests.test_decision_cell_executor import STUDY as RUN_STUDY, built_source, left, recorded, refused, source  # noqa: F401
from tests.test_decision_cell_verification import NOW, OWNER, audit, events  # noqa: F401

BOTH = (PAIR, SOLE)
WORDS = {"st1": PAIR.statement_text, "st2": SOLE.statement_text}
PERSONAL = StatementRating("personal", "dana")
PLAIN = StatementRating("internal")
RUNS = [Option.CONTINUE, Option.FORK_FROM_EVENT, Option.FORK_FROM_EARLIER, Option.RERUN_FROM_START]
ST1, ST2 = statement_input_id("e1", "st1"), statement_input_id("e1", "st2")
MISSING = f"data_owner_grant_missing:{ST1}"


def register(audit, st1=PERSONAL, st2=PLAIN, version=0):
    return register_item_statements(statements=WORDS, ratings={"st1": st1, "st2": st2},
                                    expected_version=version, audit=audit, **KW)


def legacy(audit, ratings=(), version=1, words=WORDS):
    """A list event written directly: with no rating tags it is what was recorded before ratings existed."""
    audit.append({
        "event_id": gate_module.statement_set_event_id(*KW.values(), version),
        "event_type": "decision_cell_item_statements", "subject_id": "system:decision-cell",
        "operation": "register_item_statements", "decision": "allow", "policy_version": "test",
        "sequence": version, "count": len(words),
        "resource_ids": [f"statement:{wording_hash(t)}:{i}" for i, t in words.items()] + list(ratings),
    })


def tag(statement_id, sensitivity, owner=None):
    import json
    return "rating:" + json.dumps([statement_id, sensitivity, owner], separators=(",", ":"))


def viewed(audit):
    return item_evidence(statements=BOTH, audit=audit, **KW).evidence_hash


def request_for(audit, option, **kw):
    if option is Option.FORK_FROM_EVENT:
        kw.setdefault("event_round", 2)
    if option is Option.FORK_FROM_EARLIER:
        kw.setdefault("event_round", 2)
        kw.setdefault("from_round", 1)
    if option is Option.CHANGE_INPUTS:
        kw.setdefault("underlying", Option.FORK_FROM_EVENT)
        kw.setdefault("event_round", 2)
    if option is Option.HOLD:
        kw.setdefault("recheck_at", NOW + timedelta(hours=1))
    return choice(option, viewed(audit), **kw)


def ask(audit, option, grants=(), escalation=Escalation(), **kw):
    context = run_context() if option in RUNS or option is Option.CHANGE_INPUTS else {}
    return request_labelled_option(
        OWNER, request_for(audit, option, **kw), statements=BOTH, tenant_id="t1", project_id="p1", audit=audit,
        study=STUDY, now=NOW, grants=grants, escalation=escalation, **context).gate


def grant(input_id=ST1, grantee=None, by="dana", project="p1", study="s1"):
    return InputGrant(project, study, input_id, grantee or OWNER.subject_id, by)


def code(expected, call):
    with pytest.raises(StatementSetError) as caught:
        call()
    assert caught.value.code == expected, str(caught.value)


# -- registering and loading ratings -------------------------------------------

def test_ratings_are_recorded_and_read_back(audit):
    made = register(audit)
    assert made.ratings == (("st1", PERSONAL), ("st2", PLAIN))
    assert load_item_statements(audit=audit, **KW) == made


@pytest.mark.parametrize("ratings", [
    None, {}, {"st1": PLAIN}, {"st1": PLAIN, "st2": PLAIN, "st3": PLAIN}, {"st1": PLAIN, "st2": "internal"},
    {"st1": PLAIN, "st2": StatementRating("secret")}, {"st1": PLAIN, "st2": StatementRating(["public"])},
    {"st1": PLAIN, "st2": StatementRating("personal")}, {"st1": PLAIN, "st2": StatementRating("sensitive", " ")},
    {"st1": PLAIN, "st2": StatementRating("internal", "")},
])
def test_every_statement_needs_a_usable_rating(audit, ratings):
    before = len(events(audit))
    code("RATINGS_INVALID", lambda: register_item_statements(
        statements=WORDS, ratings=ratings, expected_version=0, audit=audit, **KW))
    assert len(events(audit)) == before


@pytest.mark.parametrize("first,second,expected", [
    (PERSONAL, PLAIN, "RATING_LOWERED"),
    (StatementRating("sensitive", "dana"), PERSONAL, "RATING_LOWERED"),
    (PERSONAL, StatementRating("personal", "erin"), "DATA_OWNER_CHANGED"),
    (PERSONAL, StatementRating("sensitive", "erin"), "DATA_OWNER_CHANGED"),
    (StatementRating("internal", "dana"), PLAIN, "DATA_OWNER_CHANGED"),
    (PERSONAL, PERSONAL, "NOTHING_ADDED"),
])
def test_a_later_list_cannot_weaken_a_rating(audit, first, second, expected):
    register(audit, st1=first)
    code(expected, lambda: register(audit, st1=second, version=1))
    assert load_item_statements(audit=audit, **KW).version == 1


@pytest.mark.parametrize("first,second", [
    (PLAIN, PERSONAL), (PERSONAL, StatementRating("sensitive", "dana")),
    (PLAIN, StatementRating("internal", "dana")),
])
def test_a_later_list_may_only_raise_a_rating_or_name_an_owner(audit, first, second):
    register(audit, st1=first)
    assert register(audit, st1=second, version=1).version == 2
    assert dict(load_item_statements(audit=audit, **KW).ratings)["st1"] == second


@pytest.mark.parametrize("second", [
    [tag("st1", "internal", "dana")],                       # lowered
    [tag("st1", "personal", "erin")],                       # owner replaced
    [],                                                     # rating dropped
])
def test_a_stored_list_that_weakens_a_rating_is_not_trusted(audit, second):
    legacy(audit, [tag("st1", "personal", "dana")])
    legacy(audit, second, version=2, words={**WORDS, "st3": "a third"})
    code("STORE_INCONSISTENT", lambda: load_item_statements(audit=audit, **KW))


@pytest.mark.parametrize("ratings", [
    [tag("st1", "secret")], [tag("st1", "personal")], [tag("st9", "internal")],
    [tag("st1", "personal", "dana"), tag("st1", "internal")],
])
def test_a_stored_bad_rating_is_not_trusted(audit, ratings):
    legacy(audit, ratings)
    code("STORE_INCONSISTENT", lambda: load_item_statements(audit=audit, **KW))


# -- the grant check -----------------------------------------------------------

@pytest.mark.parametrize("option", RUNS)
def test_every_run_needs_the_owners_grant_for_a_personal_statement_it_adds(audit, option):
    register(audit)
    blocked = ask(audit, option)
    assert blocked.failures == (MISSING,) and not blocked.executable
    assert events(audit)[-1]["decision"] == "deny" and events(audit)[-1]["reason"] == "data_owner_grant_missing"
    assert ask(audit, option, grants=(grant(),)).executable


@pytest.mark.parametrize("wrong", [
    grant(input_id=ST2), grant(input_id=statement_input_id("e2", "st1")), grant(input_id="st1"),
    grant(grantee="someone-else"), grant(by="erin"), grant(project="p2"), grant(study="s2"),
])
def test_a_grant_for_something_else_does_not_count(audit, wrong):
    register(audit)
    assert ask(audit, Option.FORK_FROM_EVENT, grants=(wrong,)).failures == (MISSING,)


def test_each_personal_statement_needs_its_own_grant(audit):
    register(audit, st2=StatementRating("sensitive", "erin"))
    assert ask(audit, Option.CONTINUE, grants=(grant(),)).failures == (f"data_owner_grant_missing:{ST2}",)
    assert ask(audit, Option.CONTINUE, grants=(grant(), grant(ST2, by="erin"))).executable


@pytest.mark.parametrize("option", [Option.IGNORE, Option.HOLD, Option.COMPARE])
def test_a_choice_that_adds_nothing_needs_no_grant(audit, option):
    register(audit)
    assert ask(audit, option).executable


def test_changed_inputs_needs_grants_only_for_the_chosen_statements(audit):
    register(audit)
    assert ask(audit, Option.CHANGE_INPUTS, inputs=(InputRef(ST2, "internal"),)).executable
    chosen = (InputRef(ST1, "personal", "dana"),)
    assert ask(audit, Option.CHANGE_INPUTS, inputs=chosen).failures == (MISSING,)
    assert ask(audit, Option.CHANGE_INPUTS, inputs=chosen, grants=(grant(),)).executable


@pytest.mark.parametrize("claimed", [("internal", None), ("public", "dana"), ("personal", "erin"),
                                     ("sensitive", "dana")])
def test_the_request_cannot_restate_a_rating(audit, claimed):
    register(audit)
    # Even a grant from the owner the request names does not help: the recorded owner is the one asked.
    result = ask(audit, Option.CHANGE_INPUTS, inputs=(InputRef(ST1, *claimed),), grants=(grant(by="erin"),))
    assert result.failures == (f"input_rating_mismatch:{ST1}", MISSING)


def test_other_changed_inputs_keep_their_own_check(audit):
    register(audit)
    extra = InputRef("file:x", "personal", "erin")
    result = ask(audit, Option.CHANGE_INPUTS, inputs=(InputRef(ST2, "internal"), extra))
    assert result.failures == ("data_owner_grant_missing:file:x",)


@pytest.mark.parametrize("option", RUNS + [Option.CHANGE_INPUTS])
def test_an_unrated_list_cannot_enter_a_run(audit, option):
    legacy(audit)
    inputs = {"inputs": (InputRef(ST1, "public"),)} if option is Option.CHANGE_INPUTS else {}
    result = ask(audit, option, grants=(grant(),), **inputs)
    wanted = {f"statement_unrated:{ST1}"} | ({f"statement_unrated:{ST2}"} if not inputs else set())
    assert set(result.failures) == wanted and not result.executable


def test_an_unrated_list_can_still_be_ignored_and_can_be_rated_later(audit):
    legacy(audit)
    assert load_item_statements(audit=audit, **KW).ratings == ()
    assert ask(audit, Option.IGNORE).executable
    assert register(audit, st1=PLAIN, version=1).version == 2
    assert ask(audit, Option.CONTINUE).executable


# -- the ratings cannot be supplied, skipped or outrun ---------------------------

@pytest.mark.parametrize("path", ["labelled", "project", "respond"])
def test_no_caller_can_supply_the_ratings(audit, path):
    register(audit)
    request = request_for(audit, Option.CONTINUE)
    kw = dict(tenant_id="t1", project_id="p1", audit=audit, study=STUDY, now=NOW, item_statements=())
    if path == "respond":
        from agora.decision_cell import open_response_window
        open_response_window(audit=audit, now=NOW, **KW)
        call = lambda: respond_to_item(OWNER, request, approved_result_hash_for=lambda s: None, **kw)
    elif path == "project":
        call = lambda: request_project_option(OWNER, request, **kw)
    else:
        call = lambda: request_labelled_option(OWNER, request, statements=BOTH, **kw)
    with pytest.raises(PermissionError, match="supplied by the caller"):
        call()


def test_an_evidence_hash_without_the_ratings_does_not_pass_the_gate(audit):
    register(audit)
    result = request_option(OWNER, request_for(audit, Option.CONTINUE), record=ProjectRecord("p1", "t1", "owner"),
                            study=STUDY, audit=audit, now=NOW, evidence_hash=viewed(audit), **run_context())
    assert "item_labels_required" in result.failures and not result.executable


def test_a_rating_raised_before_the_commit_stops_the_attempt(audit, monkeypatch):
    register(audit, st1=PLAIN)
    request = request_for(audit, Option.CONTINUE)
    real = ev.request_option

    def raised_meanwhile(*args, **kwargs):
        register(audit, st1=PERSONAL, version=1)
        return real(*args, **kwargs)

    monkeypatch.setattr(ev, "request_option", raised_meanwhile)
    before = [e for e in events(audit) if e["event_type"] == "decision_cell_option"]
    with pytest.raises(PermissionError) as caught:
        request_labelled_option(OWNER, request, statements=BOTH, tenant_id="t1", project_id="p1", audit=audit,
                                study=STUDY, now=NOW, **run_context())
    assert caught.value.code == "STATEMENTS_CHANGED"
    assert [e for e in events(audit) if e["event_type"] == "decision_cell_option"] == before


def test_raising_a_rating_changes_the_view_and_lapses_a_second_approval(audit):
    write_project_record(OWNER, ProjectRecord("p1", "t1", "owner", second_approver_subject_id="second",
                                              requires_second_approval=True),
                         expected_version=1, audit=audit, now=NOW)
    register(audit, st1=PLAIN)
    old_view = viewed(audit)
    first = ask(audit, Option.CONTINUE)
    approval = Escalation(EscalationStatus.APPROVED, "second", first.action_fingerprint)
    assert ask(audit, Option.CONTINUE, escalation=approval).executable
    register(audit, st1=PERSONAL, version=1)
    assert viewed(audit) != old_view
    result = ask(audit, Option.CONTINUE, grants=(grant(),), escalation=approval)
    assert result.failures == ("second_approval_for_different_action",)


def test_an_unrated_list_keeps_the_view_hash_it_had(audit):
    legacy(audit)
    # Value computed by the code before ratings were added, for this evidence and an unrated list.
    assert viewed(audit) == "b0daebc249a1f8778a02b148453a6ba7aef104a1aa51742ce467727929d92f35"


@pytest.mark.parametrize("execute,option", [(execute_event_fork, Option.FORK_FROM_EVENT),
                                            (execute_earlier_fork, Option.FORK_FROM_EARLIER),
                                            (execute_rerun, Option.RERUN_FROM_START)])
def test_an_executor_releases_nothing_without_the_grant(audit, source, tmp_path, execute, option):  # noqa: F811
    register(audit)
    out = tmp_path / "out"

    def run(grants=()):
        # The shared source has one snapshot, at round 2.
        extra = {Option.RERUN_FROM_START: {"event_round": 2},
                 Option.FORK_FROM_EARLIER: {"event_round": 3, "from_round": 2}}.get(option, {})
        request = request_for(audit, option, budget_units=100_000, **extra)
        return execute(OWNER, request, statements=BOTH, tenant_id="t1", project_id="p1", result_id="res1",
                       source=source, out_dir=out, audit=audit, now=NOW, study=RUN_STUDY,
                       kill_switch_on=lambda: False, grants=grants)

    assert refused("GATE_BLOCKED", run).gate.failures == (MISSING,)
    assert recorded(audit) is None and left(out) == []
    assert run((grant(),)).path.is_dir() and recorded(audit) is not None

"""Policy checks at a proposal's own classification carry the caller's purpose and retention.

Every proposal here is ``sensitive``. The policy is the product's own decision rules, one role per
identity, so a check that is handed no purpose or retention is refused. All data is synthetic.
"""

from __future__ import annotations

import pytest

from agora.ontology import (
    OntologyError, action_proposal_state, admit_approved_action, co_approve_action_proposal,
    decide_action_proposal, list_action_proposals, propose_action, read_simulation_outcome,
    recheck_action_proposal, record_simulation_outcome, run_admitted_simulation, withdraw_approval,
)
from agora.policy import decide
from agora import protection

from test_ontology_action_approvals import _events, catalog  # noqa: F401
from test_ontology_action_proposals import _values, world  # noqa: F401

CALLER = {"purpose": "case-review", "retention": "7d"}
CATALOG = ("ontology_catalog", "project_lifetime")
MISSING = [
    {},
    {"purpose": "case-review"},
    {"retention": "7d"},
    {"purpose": " ", "retention": "7d"},
]


class _RolePolicy:
    """The central rules for one identity in one role; records what it is asked at ``sensitive``."""

    def __init__(self, project_id, subject, role):
        self.subject = {"subject_id": subject, "project_id": project_id}
        self.role = role
        self.asked = []

    def __call__(self, operation, resource):
        if operation not in {"ontology_read", "ontology_write", "ontology_action_propose",
                             "ontology_action_decide", "ontology_action_admit",
                             "ontology_action_outcome"}:
            # Source reads under the binding: not what these tests are about.
            return decide(self.subject, "operator", operation, resource)
        self.asked.append((operation, resource["source_sensitivity"],
                           resource.get("purpose"), resource.get("retention")))
        return decide(self.subject, self.role, operation, resource)


@pytest.fixture
def people(world, monkeypatch):
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", False)
    monkeypatch.setattr(protection, "RUNNER_ONLY_OUTCOMES", False)
    project_id = world.store.project_id
    roles = {"proposer": "operator", "approver": "approver", "second": "approver",
             "runner": "operator", "reader": "reader"}
    return {name: _RolePolicy(project_id, name, role) for name, role in roles.items()}


def _propose(w, people, **privacy):
    return propose_action(
        w.store, w.pack, "backup:FollowUp", "1.0.0", w.end("C-1"), w.end("C-2"), _values(),
        w.evidence, "missed appointment", policy=people["proposer"], audit=w.audit, **privacy)


def _args(w, proposal):
    return w.store, proposal.document, proposal.digest


def _recheck(w, people, p, **privacy):
    recheck_action_proposal(*_args(w, p), policy=people["reader"], audit=w.audit, **privacy)


def _decide(w, people, p, **privacy):
    return decide_action_proposal(*_args(w, p), "approve", "checked", policy=people["approver"],
                                  audit=w.audit, **privacy)


def _co(w, people, p, **privacy):
    return co_approve_action_proposal(*_args(w, p), "second look", policy=people["second"],
                                      audit=w.audit, **privacy)


def _withdraw(w, people, p, **privacy):
    return withdraw_approval(*_args(w, p), "stop", policy=people["approver"], audit=w.audit, **privacy)


def _admit(w, people, p, **privacy):
    return admit_approved_action(*_args(w, p), policy=people["runner"], audit=w.audit, **privacy)


def _record(w, people, p, **privacy):
    return record_simulation_outcome(*_args(w, p), "succeeded", "sha256:" + "0" * 64,
                                     policy=people["runner"], audit=w.audit, **privacy)


def _read_outcome(w, people, p, **privacy):
    return read_simulation_outcome(*_args(w, p), policy=people["reader"], audit=w.audit, **privacy)


def _state(w, people, p, **privacy):
    return action_proposal_state(*_args(w, p), policy=people["reader"], audit=w.audit, **privacy)


def _list(w, people, p, **privacy):
    return list_action_proposals(w.store, policy=people["reader"], audit=w.audit, **privacy)


# (call, the identity it uses, the operation it asks about, the steps that must already have happened)
CASES = {
    "recheck": (_recheck, "reader", "ontology_read", []),
    "decide": (_decide, "approver", "ontology_action_decide", []),
    "co_approve": (_co, "second", "ontology_action_decide", [_decide]),
    "withdraw": (_withdraw, "approver", "ontology_action_decide", [_decide]),
    "admit": (_admit, "runner", "ontology_action_admit", [_decide, _co]),
    "record": (_record, "runner", "ontology_action_outcome", [_decide, _co, _admit]),
    "read_outcome": (_read_outcome, "reader", "ontology_read", [_decide, _co, _admit, _record]),
    "state": (_state, "reader", "ontology_read", []),
    "list": (_list, "reader", "ontology_read", []),
}


def _prepared(world, people, steps):
    proposal = _propose(world, people, **CALLER)
    assert proposal.document["sensitivity"] == "sensitive"
    for step in steps:
        step(world, people, proposal, **CALLER)
    for policy in people.values():
        policy.asked.clear()
    return proposal


def _chain_types(w):
    rows = w.audit.chain.db.execute(
        "SELECT json_extract(event_json, '$.event_type') FROM audit_events ORDER BY seq").fetchall()
    return [r[0] for r in rows if r[0].startswith("ontology_action_")]


@pytest.mark.parametrize("privacy", MISSING)
def test_proposing_is_refused_without_purpose_and_retention(world, people, privacy):
    with pytest.raises(OntologyError, match="policy denied"):
        _propose(world, people, **privacy)
    assert people["proposer"].asked[-1][:2] == ("ontology_action_propose", "sensitive")
    assert _events(world, "ontology_action_proposed") == []


def test_proposing_asks_about_the_callers_purpose_and_keeps_the_first_check_on_the_catalog(world, people):
    _propose(world, people, **CALLER)
    asked = [x for x in people["proposer"].asked if x[0] == "ontology_action_propose"]
    assert asked == [("ontology_action_propose", "internal", *CATALOG),
                     ("ontology_action_propose", "sensitive", "case-review", "7d")]


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("privacy", MISSING)
def test_each_later_step_is_refused_without_purpose_and_retention(world, people, name, privacy):
    call, who, operation, steps = CASES[name]
    proposal = _prepared(world, people, steps)
    before = _chain_types(world)
    with pytest.raises(OntologyError, match="policy denied"):
        call(world, people, proposal, **privacy)
    # Refused at the check made at the proposal's classification, and nothing was recorded.
    assert people[who].asked[-1][:2] == (operation, "sensitive")
    assert _chain_types(world) == before


@pytest.mark.parametrize("name", list(CASES))
def test_each_later_step_asks_about_the_callers_purpose(world, people, name):
    call, who, operation, steps = CASES[name]
    proposal = _prepared(world, people, steps)
    call(world, people, proposal, **CALLER)
    sensitive = [x for x in people[who].asked if x[0] == operation and x[1] == "sensitive"]
    assert sensitive and {x[2:] for x in sensitive} == {("case-review", "7d")}


def test_the_runner_hands_its_purpose_to_the_outcome_check(world, people, monkeypatch):
    monkeypatch.setattr(protection, "RUNNER_ONLY_OUTCOMES", True)
    proposal = _prepared(world, people, [_decide, _co, _admit])
    out = run_admitted_simulation(*_args(world, proposal), policy=people["runner"],
                                  audit=world.audit, **CALLER)
    assert out["status"] == "succeeded"
    outcome = [x for x in people["runner"].asked if x[0] == "ontology_action_outcome"]
    assert outcome == [("ontology_action_outcome", "sensitive", "case-review", "7d")]

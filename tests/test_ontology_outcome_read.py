"""A recorded outcome is read back only when the chain's own record of it checks out; nothing runs."""
from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from agora.ontology import OntologyError, approvals, outcomes, read_simulation_outcome
from agora.policy import decide

from test_ontology_action_admission import _approved
from test_ontology_action_approvals import READER, _events, catalog, world  # noqa: F401
from test_ontology_action_outcomes import (
    _OTHER, _RESULT, _admitted, _forge, _hex, _record, _resources,
)
from test_ontology_action_proposals import _deny, _propose

_REPORT = b'{"run": "kept by the caller"}'
_REPORT_DIGEST = "sha256:" + hashlib.sha256(_REPORT).hexdigest()


def _read(w, proposal, policy=READER, document=None, **options):
    return read_simulation_outcome(
        w.store, document if document is not None else proposal.document, proposal.digest,
        policy=policy, audit=w.audit, **options)


def _outcome_event(w, proposal, **changes):
    """An outcome appended directly to the chain, as a faulty or hostile writer could."""
    event = {"event_id": "ontology-action-outcome-" + _hex(proposal),
             "event_type": "ontology_action_simulation_succeeded",
             "operation": "ontology_action_outcome", "decision": "allow", "subject_id": "runner-1",
             "policy_version": "v", "resource_ids": _resources(proposal), "result_hash": _RESULT,
             "reason": "policy_allow"}
    event.update(changes)
    w.audit.append({k: v for k, v in event.items() if v is not None})


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_a_recorded_outcome_is_read_back(world, status):
    proposal = _admitted(world)
    _record(world, proposal, status=status)
    found = _read(world, proposal)
    (event,) = _events(world, "ontology_action_simulation_" + status)
    assert found == {
        "digest": proposal.digest, "status": status, "result_digest": _RESULT,
        "result_checked": False, "proposed_by": "ontology-test-operator",
        "approved_by": "approver-1", "admitted_by": "runner-1", "recorded_by": "runner-1",
        "recorded_at": event["recorded_at"], "source": "reported_by_admitter"}
    assert _read(world, proposal) == found
    assert world.audit.verify()["valid"]


def test_the_kept_report_is_compared_with_the_recorded_digest(world):
    proposal = _admitted(world)
    _record(world, proposal, result=_REPORT_DIGEST)
    assert _read(world, proposal, result=_REPORT)["result_checked"] is True
    for wrong in (_REPORT + b" ", b""):
        with pytest.raises(OntologyError, match="does not match the recorded digest"):
            _read(world, proposal, result=wrong)


@pytest.mark.parametrize("result", [_REPORT.decode(), bytearray(_REPORT)])
def test_the_report_must_be_bytes(world, result):
    proposal = _admitted(world)
    _record(world, proposal, result=_REPORT_DIGEST)
    with pytest.raises(OntologyError, match="exact bytes"):
        _read(world, proposal, result=result)


@pytest.mark.parametrize("state,message", [
    ("proposed", "has not been decided"), ("approved", "has not been admitted"),
    ("admitted", "has no recorded outcome")])
def test_there_is_nothing_to_read_before_an_outcome(world, state, message):
    if state == "proposed":
        proposal = _propose(world)
    else:
        proposal = _approved(world) if state == "approved" else _admitted(world)
    with pytest.raises(OntologyError, match=message):
        _read(world, proposal)


@pytest.mark.parametrize("changes", [
    {"operation": "ontology_action_admit"}, {"decision": "deny"}, {"resource_ids": "short"},
    {"result_hash": None}, {"result_hash": "sha256:short"},
    {"event_id": "ontology-some-other-id"}, {"event_type": "ontology_action_other"}])
def test_a_malformed_outcome_event_is_refused(world, changes):
    proposal = _admitted(world)
    if changes.get("resource_ids") == "short":
        changes = {"resource_ids": ["p", proposal.digest]}
    _outcome_event(world, proposal, **changes)
    with pytest.raises(OntologyError, match="outcome event is not well formed"):
        _read(world, proposal)


def test_two_outcomes_are_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    _outcome_event(world, proposal, event_id="ontology-second-outcome",
                   event_type="ontology_action_simulation_failed", result_hash=_OTHER)
    with pytest.raises(OntologyError, match="more than one outcome"):
        _read(world, proposal)


@pytest.mark.parametrize("subject", ["runner-2", "approver-1", None])
def test_an_outcome_from_anyone_but_the_admitter_is_refused(world, subject):
    proposal = _admitted(world)
    _outcome_event(world, proposal, subject_id=subject)
    with pytest.raises(OntologyError, match="not from the identity that admitted"):
        _read(world, proposal)


def test_an_outcome_written_before_its_admission_is_refused(world):
    proposal = _approved(world)
    _outcome_event(world, proposal)
    _forge(world, proposal)
    with pytest.raises(OntologyError, match="not in that order"):
        _read(world, proposal)


def test_an_outcome_without_an_admission_is_refused(world):
    proposal = _approved(world)
    _outcome_event(world, proposal)
    with pytest.raises(OntologyError, match="has not been admitted"):
        _read(world, proposal)


def test_an_admission_written_before_its_approval_is_refused(world):
    proposal = _propose(world)
    _forge(world, proposal)
    world.audit.append({
        "event_id": "ontology-action-decision-" + _hex(proposal),
        "event_type": "ontology_action_approved", "operation": "ontology_action_decide",
        "decision": "allow", "subject_id": "approver-1", "policy_version": "v",
        "resource_ids": _resources(proposal), "reason": "policy_allow"})
    _outcome_event(world, proposal)
    with pytest.raises(OntologyError, match="not in that order"):
        _read(world, proposal)


def test_a_later_change_or_expiry_does_not_hide_the_outcome(world, monkeypatch):
    proposal = _admitted(world)
    _record(world, proposal)
    later = datetime.now(timezone.utc) + timedelta(days=30)
    monkeypatch.setattr(approvals, "_now", lambda: later)

    def no_reread(*args, **kwargs):
        raise AssertionError("objects must not be re-read")

    monkeypatch.setattr(approvals, "recheck_action_proposal", no_reread)
    assert _read(world, proposal)["status"] == "succeeded"


def test_the_read_is_decided_before_the_chain_is_searched(world, monkeypatch):
    proposal = _admitted(world)
    _record(world, proposal)
    seen = []

    def deny(operation, resource):
        seen.append((operation, resource["source_sensitivity"]))
        return _deny(operation, resource)

    def unread(*args, **kwargs):
        raise AssertionError("chain searched before the decision")

    monkeypatch.setattr(outcomes, "_admission", unread)
    with pytest.raises(OntologyError, match="policy denied"):
        _read(world, proposal, policy=deny)
    assert seen == [("ontology_read", "sensitive")]


def test_a_changed_proposal_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    changed = {**proposal.document, "sensitivity": "public"}
    with pytest.raises(OntologyError, match="does not match the expected digest"):
        _read(world, proposal, document=changed)


def test_an_unanchored_writer_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    anchored, world.audit = world.audit, world.audit.chain
    try:
        with pytest.raises(OntologyError, match="anchored audit writer"):
            _read(world, proposal)
    finally:
        world.audit = anchored


def test_a_tail_that_was_never_anchored_is_refused(world):
    proposal = _admitted(world)
    _record(world, proposal)
    world.audit.chain.append({"event_id": "unanchored-tail", "event_type": "x", "reason": "policy_allow"})
    with pytest.raises((OntologyError, PermissionError), match="not cleanly anchored"):
        _read(world, proposal)


def test_the_central_roles_that_can_read_outcomes():
    resource = {"project_id": "p", "resource_ids": ["x"], "source_sensitivity": "internal"}
    allowed = {role for role in ("operator", "reviewer", "approver", "reader")
               if decide({"subject_id": "s", "project_id": "p"}, role,
                         "ontology_read", resource)["decision"] == "allow"}
    assert allowed == {"operator", "reviewer", "reader"}

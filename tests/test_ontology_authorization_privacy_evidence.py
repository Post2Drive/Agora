"""The ontology authorization audit event carries digests of the purpose and retention checked.

The expected values are the strings the policy was actually handed, recorded by the policy itself,
so the event is compared with what was decided on, not with what a caller says it sent. All data
is synthetic.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from agora.ontology import OntologyError, propose_action
from agora.ontology.store import _privacy_evidence

from test_ontology_action_approvals import _events, catalog  # noqa: F401
from test_ontology_action_proposals import _values, world  # noqa: F401

PURPOSE = "case-review ticket for jane.doe@example.test"
RETENTION = "7d"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Recorder:
    """Allows everything except what ``deny`` selects; keeps what each check was handed."""

    def __init__(self, deny=None):
        self.asked = []
        self.deny = deny

    def __call__(self, operation, resource):
        self.asked.append((operation, resource.get("purpose"), resource.get("retention")))
        denied = self.deny is not None and self.deny(operation, resource)
        return {"decision": "deny" if denied else "allow", "subject_id": "recorder",
                "policy_version": "test", "reason": "test"}


def _authorizations(w):
    return _events(w, "ontology_operation_authorized")


def _propose(w, policy, purpose=PURPOSE, retention=RETENTION):
    return propose_action(
        w.store, w.pack, "backup:FollowUp", "1.0.0", w.end("C-1"), w.end("C-2"), _values(),
        w.evidence, "missed appointment", policy=policy, audit=w.audit,
        purpose=purpose, retention=retention)


def test_each_authorization_event_matches_what_the_policy_was_handed(world):
    before = len(_authorizations(world))
    policy = _Recorder()
    world.store.verify_integrity(policy=policy, audit=world.audit)
    events = _authorizations(world)[before:]
    assert len(events) == len(policy.asked) >= 1
    assert policy.asked[0] == ("ontology_read", "ontology_catalog", "project_lifetime")
    for event, (_, purpose, retention) in zip(events, policy.asked):
        # A value that was not given leaves no digest.
        assert event.get("purpose_hash") == (None if purpose is None else _sha(purpose))
        assert event.get("retention_hash") == (None if retention is None else _sha(retention))


def test_a_record_level_check_records_the_callers_values_as_digests_only(world):
    before = len(_authorizations(world))
    _propose(world, _Recorder())
    events = _authorizations(world)[before:]
    proposing = [e for e in events if e["operation"] == "ontology_action_propose"]
    # The pre-lookup check carries the catalog labels, the record-level one the caller's.
    assert [(e["purpose_hash"], e["retention_hash"]) for e in proposing] == [
        (_sha("ontology_catalog"), _sha("project_lifetime")),
        (_sha(PURPOSE), _sha(RETENTION)),
    ]
    stored = [row[0] for row in world.audit.chain.db.execute("SELECT event_json FROM audit_events")]
    assert not any("jane.doe" in raw for raw in stored)
    assert world.audit.chain.verify()["valid"]


def test_a_refused_record_level_check_leaves_no_authorization_for_those_values(world):
    policy = _Recorder(deny=lambda operation, resource: resource.get("purpose") == PURPOSE)
    with pytest.raises(OntologyError, match="policy denied"):
        _propose(world, policy)
    assert _sha(PURPOSE) not in {e.get("purpose_hash") for e in _authorizations(world)}


@pytest.mark.parametrize("privacy, expected", [
    (("a", "b"), {"purpose_hash": _sha("a"), "retention_hash": _sha("b")}),
    ((None, None), {}),
    (("a", None), {"purpose_hash": _sha("a")}),
    ((None, "b"), {"retention_hash": _sha("b")}),
    ((7, ["b"]), {}),
    (("", " a "), {"purpose_hash": _sha(""), "retention_hash": _sha(" a ")}),
])
def test_only_strings_leave_a_digest_and_they_are_hashed_exactly_as_sent(privacy, expected):
    assert _privacy_evidence(privacy) == expected


def test_a_lone_surrogate_is_digested_instead_of_raising_after_the_allow():
    digest = hashlib.sha256("\ud800".encode("utf-8", "surrogatepass")).hexdigest()
    assert _privacy_evidence(("\ud800", None)) == {"purpose_hash": digest}


def test_the_digests_survive_in_the_hashed_event(world):
    """They are part of what the chain hashes: changing one breaks verification."""
    _propose(world, _Recorder())
    seq, raw = world.audit.chain.db.execute(
        "SELECT seq, event_json FROM audit_events WHERE instr(event_json, ?) > 0",
        (_sha(PURPOSE),)).fetchone()
    event = json.loads(raw)
    event["purpose_hash"] = _sha("something else")
    db = world.audit.chain.db
    db.execute("DROP TRIGGER protect_audit_event_update")
    db.execute("UPDATE audit_events SET event_json=? WHERE seq=?",
               (json.dumps(event, sort_keys=True, separators=(",", ":")), seq))
    db.commit()
    assert world.audit.chain.verify() == {"valid": False, "first_broken_sequence": seq}

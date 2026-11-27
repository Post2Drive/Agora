"""Admission of an approved action requires a signed approval statement checked by a receipt gate (test keys only)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agora import protection
from agora.ontology import OntologyError, admit_approved_action, approvals
from agora.ontology.approvals import SignedApproval
from agora.security import approval_receipt as ap
from agora.security import key_list as kl
from agora.security import receipt_gate as rg
from agora.security import signed_receipt as sr

from test_ontology_action_admission import _admit, _endings, _later, RUNNER  # noqa: F401
from test_ontology_action_approvals import APPROVER, _as, _decide, _events, catalog  # noqa: F401
from test_ontology_action_proposals import _propose, world  # noqa: F401

TK = json.loads((Path(__file__).parent / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))["test_key"]
SEED = bytes.fromhex(TK["seed_hex"])
ROOT_SEED, STANDBY_SEED = bytes([7]) * 32, bytes([8]) * 32
TENANT, RELEASE = "tenant-test", "release-test"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def _text(moment):
    return moment.strftime(FMT)


class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def __call__(self):
        return self.now


def _config(w, key_mode="test"):
    return rg.GateConfig(TENANT, RELEASE, key_mode, sr.public_key(ROOT_SEED), sr.public_key(STANDBY_SEED),
                         Path("/unused/audit.sqlite3"), Path("/unused/anchor.jsonl"), "ontology-approval-test")


def _list(clock, *, version=1, test=True, status="active"):
    return kl.make_key_list(ROOT_SEED, {
        "type": "key_list", "v": 1, "alg": "ed25519", "list_version": version,
        "issued_at": _text(clock.now - timedelta(minutes=1)), "expires_at": _text(clock.now + timedelta(minutes=14)),
        "root_key_id": kl.fingerprint(sr.public_key(ROOT_SEED)),
        "keys": [{"key_id": TK["key_id"], "public": "ed25519:" + sr.public_key(SEED).hex(),
                  "not_before": _text(clock.now - timedelta(days=1)), "not_after": _text(clock.now + timedelta(days=30)),
                  "status": status, "test": test}]})


def _gate(w, clock, **options):
    gate = rg.ReceiptGate(_config(w, options.pop("key_mode", "test")), w.audit,
                          clock=clock, monotonic=lambda: 100.0)
    gate.refresh_key_list(_list(clock, **options))
    return gate


def _statement(w, proposal, clock, **changes):
    body = {"type": "action_approval", "v": 1, "alg": "ed25519", "tenant": TENANT, "release_id": RELEASE,
            "project": w.store.project_id, "proposal_digest": proposal.digest,
            "proposed_by": "ontology-test-operator", "approved_by": "approver-1", "key_id": TK["key_id"],
            "issued_at": _text(clock.now - timedelta(seconds=10)),
            "expires_at": _text(clock.now + timedelta(seconds=120))}
    body.update(changes)
    return ap.make_approval_statement(SEED, body)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(approvals, "_now", c)
    return c


def _signed(w, proposal, clock, gate=None, **changes):
    return SignedApproval(gate or _gate(w, clock), _statement(w, proposal, clock, **changes))


def _approved(w):
    proposal = _propose(w)
    _decide(w, proposal)
    return proposal


def test_a_signed_statement_admits_the_action(world, clock):
    proposal = _approved(world)
    result = _admit(world, proposal, signed_approval=_signed(world, proposal, clock))
    assert result["admitted_by"] == "runner-1" and result["approved_by"] == "approver-1"
    assert len(_endings(world)) == 1


def test_protected_defaults_refuse_admission_without_a_statement(world, clock, monkeypatch):
    proposal = _approved(world)
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", True)
    with pytest.raises(OntologyError, match="requires a signed approval statement"):
        _admit(world, proposal)
    assert _endings(world) == []
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", False)
    _admit(world, proposal)  # the relaxed test default still works without one


def test_a_supplied_statement_is_checked_even_when_not_required(world, clock):
    proposal = _approved(world)
    bad = _signed(world, proposal, clock, approved_by="someone-else")
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=bad)
    assert _endings(world) == []


@pytest.mark.parametrize("field,value", [
    ("tenant", "tenant-other"), ("release_id", "release-other"), ("project", "other-project"),
    ("proposal_digest", "sha256:" + "b" * 64), ("proposed_by", "someone-else"), ("approved_by", "someone-else"),
])
def test_every_scope_field_must_match_the_chain(world, clock, field, value):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="SCOPE|refused"):
        _admit(world, proposal, signed_approval=_signed(world, proposal, clock, **{field: value}))
    assert _endings(world) == []


def test_a_statement_for_another_proposal_cannot_admit_this_one(world, clock):
    first, second = _approved(world), _propose(world, reason="second")
    _decide(world, second)
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, first, signed_approval=_signed(world, second, clock))
    assert _endings(world) == []


def test_a_statement_signed_by_an_unknown_key_is_refused(world, clock):
    proposal = _approved(world)
    forged = ap.make_approval_statement(bytes([9]) * 32, json.loads(
        _statement(world, proposal, clock)["statement"]))
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=SignedApproval(_gate(world, clock), forged))


def test_an_expired_or_future_statement_is_refused(world, clock):
    proposal = _approved(world)
    gate = _gate(world, clock)
    old = _statement(world, proposal, clock, issued_at=_text(clock.now - timedelta(seconds=400)),
                     expires_at=_text(clock.now - timedelta(seconds=100)))
    future = _statement(world, proposal, clock, issued_at=_text(clock.now + timedelta(seconds=100)),
                        expires_at=_text(clock.now + timedelta(seconds=200)))
    for envelope in (old, future):
        with pytest.raises(OntologyError, match="refused"):
            _admit(world, proposal, signed_approval=SignedApproval(gate, envelope))
    assert _endings(world) == []


def test_no_gate_key_list_means_no_admission(world, clock):
    proposal = _approved(world)
    gate = rg.ReceiptGate(_config(world), world.audit, clock=clock, monotonic=lambda: 100.0)
    with pytest.raises(OntologyError, match="KEY_LIST_NOT_LOADED"):
        _admit(world, proposal, signed_approval=SignedApproval(gate, _statement(world, proposal, clock)))


def test_a_test_key_is_refused_in_production_mode(world, clock):
    proposal = _approved(world)
    gate = _gate(world, clock, key_mode="production", test=False)
    # the list is accepted as production keys, so the same key now verifies; a test-marked key must not
    with pytest.raises(sr.ReceiptError):
        _gate(world, clock, key_mode="production", test=True)
    _admit(world, proposal, signed_approval=SignedApproval(gate, _statement(world, proposal, clock)))


def test_a_revoked_key_is_refused(world, clock):
    proposal = _approved(world)
    gate = _gate(world, clock, status="revoked")
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=SignedApproval(gate, _statement(world, proposal, clock)))


def test_a_superseded_key_list_stops_an_older_gate(world, clock):
    proposal = _approved(world)
    old = _gate(world, clock)
    _gate(world, clock, version=2, status="revoked")  # another worker accepts a newer list that revokes the key
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=SignedApproval(old, _statement(world, proposal, clock)))
    assert _endings(world) == []


def test_a_stale_key_list_is_refused(world, clock):
    proposal = _approved(world)
    gate = _gate(world, clock)
    envelope = _statement(world, proposal, clock, expires_at=_text(clock.now + timedelta(seconds=290)))
    clock.now += timedelta(minutes=15)
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=SignedApproval(gate, envelope))


def test_a_statement_is_not_a_second_use(world, clock):
    proposal = _approved(world)
    signed = _signed(world, proposal, clock)
    _admit(world, proposal, signed_approval=signed)
    with pytest.raises(OntologyError, match="already used"):
        _admit(world, proposal, policy=_as("runner-2"), signed_approval=signed)
    assert len(_endings(world)) == 1


def test_the_statement_expiry_is_checked_again_at_the_write(world, clock, monkeypatch):
    proposal = _approved(world)
    signed = _signed(world, proposal, clock)
    expiry = clock.now + timedelta(seconds=120)
    times = iter([clock.now, expiry + timedelta(seconds=1)])
    original = approvals._now
    monkeypatch.setattr(approvals, "_now", lambda: next(times, expiry + timedelta(seconds=1)))
    with pytest.raises(OntologyError, match="expired before admission"):
        _admit(world, proposal, signed_approval=signed)
    assert _endings(world) == []
    monkeypatch.setattr(approvals, "_now", original)
    _admit(world, proposal, signed_approval=_signed(world, proposal, clock))


def test_a_non_statement_argument_is_refused(world, clock):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="signed approval statement"):
        _admit(world, proposal, signed_approval=object())


def test_self_admission_is_still_refused_with_a_statement(world, clock):
    proposal = _approved(world)
    with pytest.raises(OntologyError, match="someone other than its approver"):
        _admit(world, proposal, policy=APPROVER, signed_approval=_signed(world, proposal, clock))


def test_verify_approval_requires_exact_request_fields(world, clock):
    gate = _gate(world, clock)
    proposal = _approved(world)
    envelope = _statement(world, proposal, clock)
    good = {"project": world.store.project_id, "proposal_digest": proposal.digest,
            "proposed_by": "ontology-test-operator", "approved_by": "approver-1"}
    assert gate.verify_approval(envelope, request=good)["approved_by"] == "approver-1"
    for bad in ({**good, "tenant": TENANT}, {k: v for k, v in good.items() if k != "project"}, {**good, "project": 1}):
        with pytest.raises(sr.ReceiptError) as err:
            gate.verify_approval(envelope, request=bad)
        assert err.value.code == "BAD_REQUEST"


def test_verifying_consumes_nothing(world, clock):
    gate = _gate(world, clock)
    proposal = _approved(world)
    before = world.audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    request = {"project": world.store.project_id, "proposal_digest": proposal.digest,
               "proposed_by": "ontology-test-operator", "approved_by": "approver-1"}
    envelope = _statement(world, proposal, clock)
    gate.verify_approval(envelope, request=request)
    gate.verify_approval(envelope, request=request)
    assert world.audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == before


@pytest.mark.protected_defaults
def test_the_flag_is_on_under_protected_defaults():
    assert protection.SIGNED_APPROVAL_REQUIRED is True


def test_the_approver_in_the_scope_is_the_one_the_chain_recorded(world, clock):
    proposal = _propose(world)
    _decide(world, proposal, policy=_as("approver-2"))
    with pytest.raises(OntologyError, match="refused"):
        _admit(world, proposal, signed_approval=_signed(world, proposal, clock))  # names approver-1
    _admit(world, proposal, signed_approval=_signed(world, proposal, clock, approved_by="approver-2"))

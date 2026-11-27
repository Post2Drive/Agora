"""Admission under the protected default needs a signed approval statement checked with the worker's trust.

Test keys only. The other protections stay relaxed here, as in the other ontology action tests; only
``SIGNED_APPROVAL_REQUIRED`` is turned on.
"""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from agora import protection
from agora.ontology import OntologyError
from agora.security import approval_receipt as ap
from agora.security import key_list as kl
from agora.security import receipt_gate as rg
from agora.security import signed_receipt as sr

from test_ontology_action_admission import _admit, _approved, _endings
from test_ontology_action_approvals import catalog, world  # noqa: F401

SEED, ROOT_SEED, STANDBY_SEED = bytes([5]) * 32, bytes([7]) * 32, bytes([8]) * 32  # test keys only
KEY_ID, TENANT, RELEASE, CHAIN = "approval-key-1", "tenant-test", "release-test", "ontology-approval-test"
SHAPE = "admission requires a signed approval statement"


def _z(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _required(monkeypatch, _unprotected_fixture_defaults):
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", True)


def _key_list(version=1, status="active", test=True):
    now = _now()
    return kl.make_key_list(ROOT_SEED, {
        "type": "key_list", "v": 1, "alg": "ed25519", "list_version": version,
        "issued_at": _z(now), "expires_at": _z(now + timedelta(seconds=600)),
        "root_key_id": kl.fingerprint(sr.public_key(ROOT_SEED)),
        "keys": [{"key_id": KEY_ID, "public": "ed25519:" + sr.public_key(SEED).hex(),
                  "not_before": _z(now - timedelta(days=1)), "not_after": _z(now + timedelta(days=30)),
                  "status": status, "test": test}],
    })


def _config(tmp_path, db, anchor, name="gate.json", **changes):
    document = {
        "type": "receipt_gate_config", "v": 2, "tenant": TENANT, "release_id": RELEASE, "key_mode": "test",
        "root_public": "ed25519:" + sr.public_key(ROOT_SEED).hex(),
        "standby_root_public": "ed25519:" + sr.public_key(STANDBY_SEED).hex(),
        "audit_db": str(db), "audit_anchor": str(anchor), "chain_id": CHAIN, **changes}
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class _Clock:
    """The gate's clock; ``times`` are returned first, one per reading."""

    def __init__(self):
        self.times = []

    def __call__(self):
        return self.times.pop(0) if self.times else datetime.now(timezone.utc)


@pytest.fixture
def clock():
    return _Clock()


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "ops" / "audit.sqlite3", tmp_path / "ops" / "anchor.jsonl"


@pytest.fixture
def gate(tmp_path, world, paths, clock):
    with rg.open_receipt_gate(_config(tmp_path, *paths), clock=clock, monotonic=lambda: 100.0) as opened:
        yield opened


@pytest.fixture
def loaded(gate):
    gate.refresh_key_list(_key_list())
    return gate


def _statement(w, proposal, seed=SEED, issued=None, lifetime=300, **changes):
    issued = issued or _now()
    return ap.make_approval_statement(seed, {
        "type": "action_approval", "v": 1, "alg": "ed25519", "tenant": TENANT, "release_id": RELEASE,
        "project": w.store.project_id, "proposal_digest": proposal.digest,
        "proposed_by": "ontology-test-operator", "approved_by": "approver-1", "key_id": KEY_ID,
        "issued_at": _z(issued), "expires_at": _z(issued + timedelta(seconds=lifetime)), **changes})


def _refused(match, w, proposal, **options):
    with pytest.raises(OntologyError, match=match):
        _admit(w, proposal, **options)
    assert _endings(w) == []
    assert w.audit.verify()["valid"]


def test_a_signed_statement_admits_once_and_its_hash_is_recorded(world, loaded):
    proposal = _approved(world)
    statement = _statement(world, proposal)
    result = _admit(world, proposal, gate=loaded, statement=statement)
    expected = "sha256:" + hashlib.sha256(ap.DOMAIN + statement["statement"].encode("ascii")).hexdigest()
    assert result["admitted_by"] == "runner-1" and result["approval_statement_hash"] == expected
    (event,) = _endings(world)
    assert event["approval_statement_hash"] == expected
    with pytest.raises(OntologyError, match="already used"):
        _admit(world, proposal, gate=loaded, statement=statement)


def test_a_forged_chain_alone_admits_nothing(world):
    """The proposal and approval are in the anchored chain; without a statement that is not enough."""
    _refused(SHAPE, world, _approved(world))


@pytest.mark.parametrize("which", ["gate", "statement"])
@pytest.mark.parametrize("required", [True, False])
def test_one_of_the_two_is_never_ignored(world, loaded, monkeypatch, which, required):
    proposal = _approved(world)
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", required)
    value = loaded if which == "gate" else _statement(world, proposal)
    _refused("must be given together", world, proposal, **{which: value})


def test_a_statement_is_still_checked_when_not_required(world, loaded, monkeypatch):
    proposal = _approved(world)
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", False)
    _refused("BAD_SIGNATURE", world, proposal, gate=loaded,
             statement=_statement(world, proposal, seed=bytes([6]) * 32))


def test_a_gate_look_alike_is_refused(world, loaded):
    proposal = _approved(world)

    class Agreeable:
        def check_approval_statement(self, envelope, *, request):
            return rg.CheckedApproval(_now(), "sha256:" + "0" * 64, lambda db: None)

    _refused("must be a ReceiptGate", world, proposal, gate=Agreeable(), statement={"x": "y"})


@pytest.mark.parametrize("changes", [
    {"approved_by": "approver-2"}, {"proposed_by": "someone-else"}, {"project": "other-project"},
    {"tenant": "other-tenant"}, {"release_id": "other-release"}, {"proposal_digest": "sha256:" + "b" * 64}])
def test_the_scope_comes_from_the_chain_and_the_configuration(world, loaded, changes):
    proposal = _approved(world)
    _refused("SCOPE_MISMATCH", world, proposal, gate=loaded, statement=_statement(world, proposal, **changes))


def test_a_gate_without_a_key_list_is_refused(world, gate):
    proposal = _approved(world)
    _refused("KEY_LIST_NOT_LOADED", world, proposal, gate=gate, statement=_statement(world, proposal))


def test_test_keys_are_refused_in_production_key_mode(tmp_path, world, paths):
    proposal = _approved(world)
    config = _config(tmp_path, *paths, name="production.json", key_mode="production")
    with rg.open_receipt_gate(config, clock=_Clock(), monotonic=lambda: 100.0) as gate:
        with pytest.raises(sr.ReceiptError, match="TEST_KEY_REFUSED"):
            gate.refresh_key_list(_key_list())
        _refused("KEY_LIST_NOT_LOADED", world, proposal, gate=gate, statement=_statement(world, proposal))


def test_a_statement_may_not_outlive_the_approval(world, loaded):
    proposal = _approved(world)
    statement = _statement(world, proposal)
    _refused("outlives the approval", world, proposal, gate=loaded, statement=statement, max_age_seconds=200)
    assert _admit(world, proposal, gate=loaded, statement=statement, max_age_seconds=400)["admitted_by"]


def test_an_expired_statement_is_refused(world, loaded):
    proposal = _approved(world)
    old = _statement(world, proposal, issued=_now() - timedelta(seconds=400))
    _refused("EXPIRED", world, proposal, gate=loaded, statement=old)


@pytest.mark.parametrize("first,second,code", [(0, 301, "EXPIRED"), (10, 5, "BAD_CLOCK")])
def test_the_statement_is_checked_again_under_the_write_lock(world, loaded, clock, first, second, code):
    """The second clock case stays after the key list's acceptance, so only the gate's own check sees it."""
    proposal = _approved(world)
    statement = _statement(world, proposal)
    start = datetime.now(timezone.utc)
    clock.times[:] = [start + timedelta(seconds=first), start + timedelta(seconds=second)]
    _refused(code, world, proposal, gate=loaded, statement=statement)
    assert clock.times == []


def test_the_key_list_is_checked_again_under_the_write_lock(world, loaded, clock):
    """A newer list accepted after the signature check, before the append, stops the admission."""
    proposal = _approved(world)
    statement = _statement(world, proposal)
    revoked = _key_list(2, status="revoked")
    real = rg.ReceiptGate.check_approval_statement

    def then_revoke(self, envelope, *, request):
        checked = real(self, envelope, request=request)
        kl.accept_key_list(
            revoked, tenant=TENANT, root=kl.RootKey(sr.public_key(ROOT_SEED), test=True),
            audit=world.audit, clock=clock, monotonic=lambda: 100.0, allow_test_keys=True)
        return checked

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rg.ReceiptGate, "check_approval_statement", then_revoke)
        _refused("KEY_LIST_SUPERSEDED", world, proposal, gate=loaded, statement=statement)


def test_keys_must_be_accepted_in_the_store_being_written(tmp_path, world, clock):
    """A gate over another store verifies the signature, but this store never accepted its key list."""
    from agora.audit_anchor import AnchorStore, bootstrap_anchor
    from agora.audit_chain import AuditChainStore

    proposal = _approved(world)
    db, anchor = tmp_path / "elsewhere.sqlite3", tmp_path / "elsewhere.jsonl"
    chain = AuditChainStore(db)
    bootstrap_anchor(chain, AnchorStore(anchor, CHAIN), performed_by="maint-1")
    chain.close()
    with rg.open_receipt_gate(_config(tmp_path, db, anchor, name="other.json"), clock=clock,
                              monotonic=lambda: 100.0) as other:
        other.refresh_key_list(_key_list())
        _refused("KEY_LIST_NOT_ACCEPTED", world, proposal, gate=other,
                 statement=_statement(world, proposal))


@pytest.mark.parametrize("request_change", [{"tenant": TENANT}, {"project": 5}])
def test_the_gate_refuses_a_request_that_names_its_own_trust(world, loaded, request_change):
    proposal = _approved(world)
    request = {"project": world.store.project_id, "proposal_digest": proposal.digest,
               "proposed_by": "ontology-test-operator", "approved_by": "approver-1", **request_change}
    with pytest.raises(sr.ReceiptError, match="BAD_REQUEST"):
        loaded.check_approval_statement(_statement(world, proposal), request=request)


def test_the_requirement_is_on_in_a_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "from agora import protection as p; print(p.SIGNED_APPROVAL_REQUIRED)"],
        capture_output=True, text=True, timeout=60)
    assert result.stdout.strip() == "True", result.stderr

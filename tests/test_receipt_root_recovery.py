"""Threshold root recovery and trust-epoch rollover (public test keys only)."""
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from agora.security import key_list as kl
from agora.security import signed_receipt as sr
from test_receipt_gate import NOW, RECEIPTS, ROOT_SEED, SEED, STANDBY_SEED, opened, paths, settings, write

NEW_SEED = bytes([10]) * 32
RECOVERY_SEEDS = (bytes([11]) * 32, bytes([12]) * 32, bytes([13]) * 32)
TENANT = "tenant-a"
ONLINE = "ed25519:" + sr.public_key(SEED).hex()


def root(seed):
    return kl.RootKey(sr.public_key(seed), test=True)


ROOT_A = root(ROOT_SEED)
ROOT_B = root(STANDBY_SEED)
ROOT_C = root(NEW_SEED)
RECOVERY_KEYS = {kl.fingerprint(sr.public_key(seed)): kl.RootKey(sr.public_key(seed), test=True) for seed in RECOVERY_SEEDS}
RECOVERY_SIGNERS = {kl.fingerprint(sr.public_key(seed)): seed for seed in RECOVERY_SEEDS}


def online():
    return {
        "key_id": RECEIPTS["test_key"]["key_id"],
        "public": ONLINE,
        "not_before": "2026-11-01T00:00:00Z",
        "not_after": "2026-12-31T00:00:00Z",
        "status": "active",
        "test": True,
    }


def key_list(signer, version):
    signer_root = {"A": ROOT_A, "B": ROOT_B, "C": ROOT_C}[signer]
    seed = {"A": ROOT_SEED, "B": STANDBY_SEED, "C": NEW_SEED}[signer]
    return kl.make_key_list(seed, {
        "type": "key_list",
        "v": 1,
        "alg": "ed25519",
        "list_version": version,
        "issued_at": "2026-11-24T12:00:00Z",
        "expires_at": "2026-11-24T12:15:00Z",
        "root_key_id": signer_root.key_id,
        "keys": [online()],
    })


def recovery_body(listed, *, epoch=1, old=ROOT_A, new=ROOT_C, tenant=TENANT):
    raw = listed["key_list"].encode("ascii")
    return {
        "type": "root_recovery",
        "v": 1,
        "alg": "ed25519",
        "tenant": tenant,
        "old_root_key_id": old.key_id,
        "new_root_key_id": new.key_id,
        "trust_epoch": epoch,
        "key_list_hash": "sha256:" + hashlib.sha256(kl.DOMAIN + raw).hexdigest(),
        "issued_at": "2026-11-24T12:00:00Z",
        "expires_at": "2026-11-24T12:05:00Z",
    }


def recovery(listed, *, signers=None, **changes):
    body = recovery_body(listed, **changes)
    return kl.make_root_recovery(RECOVERY_SIGNERS if signers is None else signers, body)


def event_count(gate):
    return gate._audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]


@pytest.fixture
def config(tmp_path, paths):
    return write(tmp_path, settings(paths))


def apply_recovery(gate, listed, certificate, *, recovery_keys=RECOVERY_KEYS, threshold=2, root_key=ROOT_A,
                   new_root=ROOT_C, now=NOW):
    return kl.accept_root_recovery(
        certificate,
        listed,
        tenant=TENANT,
        root=root_key,
        new_root=new_root,
        recovery_keys=recovery_keys,
        threshold=threshold,
        audit=gate._audit,
        clock=lambda: now,
        monotonic=lambda: 100.0,
        allow_test_keys=True,
    )


def refused(code, call, *args, **kwargs):
    with pytest.raises(sr.ReceiptError) as error:
        call(*args, **kwargs)
    assert error.value.code == code, str(error.value)


def test_threshold_recovery_resets_exhausted_list_version_without_old_root_signature(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", kl.MAX_LIST_VERSION))
        before = event_count(gate)
        listed = key_list("C", 1)
        certificate = recovery(listed)
        accepted = apply_recovery(gate, listed, certificate)
        assert (accepted.list_version, accepted.trust_epoch) == (1, 1)
        assert event_count(gate) == before + 1
        event = gate._audit.find_event("key-list-accept-e000001-v000000000001")
        assert event["trust_epoch"] == 1
        assert event["root_recovery_hash"].startswith("sha256:")
        assert event["recovery_threshold"] == 2
        assert len(event["recovery_signers"]) == 3
        assert gate._audit.verify()["status"] == "anchored_verified"

        # A normal list in the new epoch advances from 1 to 2.
        next_list = kl.accept_key_list(
            key_list("C", 2), tenant=TENANT, root=ROOT_A, standby=ROOT_C, audit=gate._audit,
            clock=lambda: NOW, monotonic=lambda: 100.0, allow_test_keys=True,
        )
        assert (next_list.list_version, next_list.trust_epoch) == (2, 1)

        # The old root cannot authorise a new list after recovery.
        refused("BAD_SIGNATURE", kl.accept_key_list, key_list("A", 3), tenant=TENANT, root=ROOT_A,
                standby=ROOT_C, audit=gate._audit, clock=lambda: NOW, monotonic=lambda: 100.0,
                allow_test_keys=True)


def test_recovery_requires_threshold_and_changes_nothing(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        before = event_count(gate)
        listed = key_list("C", 1)
        one_signer = {next(iter(RECOVERY_SIGNERS)): next(iter(RECOVERY_SIGNERS.values()))}
        certificate = recovery(listed, signers=one_signer)
        refused("ROOT_RECOVERY_THRESHOLD", apply_recovery, gate, listed, certificate)
        assert event_count(gate) == before


@pytest.mark.parametrize("change,code", [
    ({"tenant": "tenant-other"}, "TENANT_MISMATCH"),
    ({"epoch": 2}, "ROOT_RECOVERY_EPOCH"),
    ({"old": ROOT_B}, "ROOT_RECOVERY_ROOTS"),
])
def test_recovery_certificate_is_bound_to_tenant_epoch_and_old_root(config, change, code):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        certificate = recovery(listed, **change)
        refused(code, apply_recovery, gate, listed, certificate)
        assert event_count(gate) == 1


def test_recovery_certificate_is_bound_to_exact_first_key_list(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        certificate = recovery(listed)
        different_list = key_list("C", 2)
        refused("ROOT_RECOVERY_LIST", apply_recovery, gate, different_list, certificate)
        assert event_count(gate) == 1


def test_recovery_certificate_rejects_invalid_signature_and_unknown_authority(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        certificate = recovery(listed)
        bad = {**certificate, "signatures": dict(certificate["signatures"])}
        signer = next(iter(bad["signatures"]))
        bad["signatures"][signer] = "00" * 64
        refused("ROOT_RECOVERY_SIGNATURE", apply_recovery, gate, listed, bad)
        unknown = {**certificate, "signatures": {**certificate["signatures"], "sha256:" + "0" * 64: "00" * 64}}
        refused("ROOT_RECOVERY_THRESHOLD", apply_recovery, gate, listed, unknown)
        assert event_count(gate) == 1


def test_recovery_authorities_must_be_independent_of_both_roots(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        compromised = {ROOT_A.key_id: ROOT_A, **RECOVERY_KEYS}
        refused("ROOT_RECOVERY_KEYS", apply_recovery, gate, listed, recovery(listed),
                recovery_keys=compromised)
        duplicated = dict(RECOVERY_KEYS)
        # A duplicate public key under a second fingerprint cannot pass the fingerprint check.
        duplicated["sha256:" + "f" * 64] = next(iter(duplicated.values()))
        refused("ROOT_RECOVERY_KEYS", apply_recovery, gate, listed, recovery(listed),
                recovery_keys=duplicated)
        # An online receipt key already present in the accepted list cannot double as recovery custody.
        online_root = kl.RootKey(sr.public_key(SEED), test=True)
        historical_online = {online_root.key_id: online_root, **dict(list(RECOVERY_KEYS.items())[:2])}
        refused("ROOT_RECOVERY_KEYS", apply_recovery, gate, listed, recovery(listed),
                recovery_keys=historical_online)
        assert event_count(gate) == 1


def test_recovery_statement_is_short_lived(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        certificate = recovery(listed)
        refused("ROOT_RECOVERY_STALE", apply_recovery, gate, listed, certificate,
                now=NOW + timedelta(minutes=6))
        assert event_count(gate) == 1


def test_recovery_cannot_bootstrap_an_empty_store(config):
    with opened(config) as gate:
        listed = key_list("C", 1)
        refused("ROOT_RECOVERY_NO_HISTORY", apply_recovery, gate, listed, recovery(listed))
        assert event_count(gate) == 0


def test_recovery_certificate_cannot_be_replayed_after_epoch_advance(config):
    with opened(config) as gate:
        gate.refresh_key_list(key_list("A", 1))
        listed = key_list("C", 1)
        certificate = recovery(listed)
        apply_recovery(gate, listed, certificate)
        before = event_count(gate)
        refused("ROOT_RECOVERY_ROOTS", apply_recovery, gate, listed, certificate)
        assert event_count(gate) == before


VECTORS = json.loads((Path(__file__).parent / "vectors" / "root_recovery_vectors.json").read_text("utf-8"))


def test_fixed_threshold_recovery_vector():
    listed = bytes.fromhex(VECTORS["key_list_canonical_hex"])
    statement = bytes.fromhex(VECTORS["recovery_canonical_hex"])
    old = kl.RootKey(bytes.fromhex(VECTORS["old_root_public_hex"]), test=True)
    new = kl.RootKey(bytes.fromhex(VECTORS["new_root_public_hex"]), test=True)
    recovery_keys = {
        item["key_id"]: kl.RootKey(bytes.fromhex(item["public_hex"]), test=True)
        for item in VECTORS["recovery_authorities"]
    }
    envelope = {"recovery": statement.decode("ascii"), "signatures": VECTORS["signatures"]}
    assert sr.canonical_bytes(sr.parse_canonical(listed)) == listed
    assert sr.canonical_bytes(sr.parse_canonical(statement)) == statement
    refused(
        "TEST_KEY_REFUSED", kl.verify_root_recovery, envelope, old=old, new=new, tenant="tenant-a",
        trust_epoch=1, list_bytes=listed, recovery_keys=recovery_keys, threshold=VECTORS["threshold"], now=NOW,
    )
    assert kl.verify_root_recovery(
        envelope, old=old, new=new, tenant="tenant-a", trust_epoch=1,
        list_bytes=listed, recovery_keys=recovery_keys, threshold=VECTORS["threshold"], now=NOW,
        allow_test_keys=True,
    ) == statement

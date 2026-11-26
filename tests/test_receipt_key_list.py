"""Signed receipt key list: pinned root, freshness, durable rollback protection (test keys only)."""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agora.audit_anchor import AnchorStore, bootstrap_anchor, open_anchored_audit
from agora.audit_chain import AuditChainStore
from agora.security import key_list as kl
from agora.security import signed_receipt as sr

VEC = json.loads((Path(__file__).parent / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))
TK = VEC["test_key"]
SEED = bytes.fromhex(TK["seed_hex"])
BASE = VEC["base_receipt"]
TENANT = BASE["tenant"]
ROOT_SEED = bytes([7]) * 32  # test root, never a production key
ROOT = kl.RootKey(sr.public_key(ROOT_SEED), test=True)
NOW = datetime(2026, 11, 24, 12, 1, tzinfo=timezone.utc)
OTHER_SEED = bytes([9]) * 32


def key(key_id=TK["key_id"], seed=SEED, status="active", **changes):
    return {"key_id": key_id, "public": "ed25519:" + sr.public_key(seed).hex(),
            "not_before": "2026-11-01T00:00:00Z", "not_after": "2026-12-31T00:00:00Z",
            "status": status, "test": True, **changes}


def body(version=1, keys=None, **changes):
    return {"type": "key_list", "v": 1, "alg": "ed25519", "list_version": version,
            "issued_at": "2026-11-24T12:00:00Z", "expires_at": "2026-11-24T12:15:00Z",
            "root_key_id": ROOT.key_id, "keys": [key()] if keys is None else keys, **changes}


def raw_envelope(document, seed=ROOT_SEED, domain=kl.DOMAIN):
    """Sign without the signer's own validation, so the verifier's checks are what is tested."""
    raw = sr.canonical_bytes(document)
    return {"key_list": raw.decode("ascii"), "sig": sr.sign(seed, domain + raw).hex()}


@pytest.fixture
def store(tmp_path):
    db_path, anchor_path = tmp_path / "audit.sqlite3", tmp_path / "anchors" / "a.jsonl"
    chain = AuditChainStore(db_path)
    bootstrap_anchor(chain, AnchorStore(anchor_path, "tenant-a-chain"), performed_by="maint-1")
    chain.close()
    with open_anchored_audit(db_path, anchor_path, "tenant-a-chain") as writer:
        yield writer


def accept(writer, document=None, *, envelope=None, tenant=TENANT, root=ROOT, now=NOW, clock=None,
           monotonic=lambda: 100.0, allow=True):
    envelope = raw_envelope(body() if document is None else document) if envelope is None else envelope
    return kl.accept_key_list(envelope, tenant=tenant, root=root, audit=writer, clock=clock or (lambda: now),
                              monotonic=monotonic, allow_test_keys=allow)


def admit(writer, trusted, n=0, *, seed=SEED, now=NOW, clock=None, monotonic=lambda: 100.0, **changes):
    receipt = {**BASE, "nonce": f"{n:032x}", **changes}
    return kl.admit_receipt_with_key_list(
        sr.make_receipt(seed, receipt), key_list=trusted, tenant=TENANT, audit=writer,
        clock=clock or (lambda: now), monotonic=monotonic,
        expected={name: receipt[name] for name in sr.SCOPE_FIELDS}, allow_test_keys=True)


def refused(code, call, *args, **kwargs):
    with pytest.raises(sr.ReceiptError) as err:
        call(*args, **kwargs)
    assert err.value.code == code, str(err.value)


def events(writer):
    return writer.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]


def test_accepting_records_one_anchored_event_and_the_key_admits_a_receipt(store):
    trusted = accept(store)
    assert events(store) == 1 and store.verify()["status"] == "anchored_verified"
    event = store.find_event("key-list-accept-000000000001")
    assert event["key_list_hash"] == trusted.list_hash
    assert "[REDACTED]" not in json.dumps(event)
    assert admit(store, trusted).receipt["key_id"] == TK["key_id"]
    assert events(store) == 2


def test_signer_and_verifier_agree_on_the_domain_separated_bytes():
    envelope = kl.make_key_list(ROOT_SEED, body())
    assert envelope == raw_envelope(body())
    assert kl.verify_key_list(envelope, root=ROOT, now=NOW, allow_test_keys=True) == sr.canonical_bytes(body())


@pytest.mark.parametrize("envelope", [
    raw_envelope(body(), seed=OTHER_SEED),
    raw_envelope(body(), domain=sr.DOMAIN),
    {**raw_envelope(body()), "key_list": raw_envelope(body(2))["key_list"]},
], ids=["other-signer", "receipt-domain", "swapped-body"])
def test_a_list_not_signed_by_the_pinned_root_is_refused(store, envelope):
    refused("BAD_SIGNATURE", accept, store, envelope=envelope)
    assert events(store) == 0


def test_list_naming_another_root_is_refused(store):
    refused("KEY_LIST_ROOT", accept, store, body(root_key_id=kl.fingerprint(sr.public_key(OTHER_SEED))))


def test_test_root_and_test_keys_are_refused_by_default(store):
    refused("TEST_KEY_REFUSED", accept, store, allow=False)
    production_root = kl.RootKey(ROOT.public, test=False)
    refused("TEST_KEY_REFUSED", accept, store, root=production_root, allow=False)
    assert events(store) == 0


def test_test_root_is_refused_even_when_it_lists_no_test_keys():
    envelope = raw_envelope(body(keys=[key(test=False)]))
    refused("TEST_KEY_REFUSED", kl.verify_key_list, envelope, root=ROOT, now=NOW)


def test_verify_alone_refuses_a_stale_list():
    refused("KEY_LIST_STALE", kl.verify_key_list, raw_envelope(body()), root=ROOT,
            now=NOW + timedelta(hours=1), allow_test_keys=True)


@pytest.mark.parametrize("code,document", [
    ("KEY_LIST_FIELDS", body(extra="x")),
    ("KEY_LIST_TYPE", body(type="release_manifest")),
    ("BAD_VERSION", body(v=2)),
    ("BAD_VERSION", body(v=True)),
    ("BAD_ALGORITHM", body(alg="none")),
    ("KEY_LIST_VERSION", body(0)),
    ("KEY_LIST_VERSION", body(True)),
    ("KEY_LIST_VERSION", body(10**12)),
    ("KEY_LIST_LIFETIME", body(expires_at="2026-11-24T12:15:01Z")),
    ("KEY_LIST_LIFETIME", body(expires_at="2026-11-24T12:00:00Z")),
    ("KEY_LIST_KEYS", body(keys=[])),
    ("KEY_LIST_KEYS", body(keys=[key(extra=1)])),
    ("KEY_LIST_KEYS", body(keys=[key(key_id="bad id")])),
    ("KEY_LIST_KEYS", body(keys=[key(public="ed25519:" + "01" + "00" * 31)])),  # identity point
    ("KEY_LIST_KEYS", body(keys=[key(seed=ROOT_SEED)])),
    ("KEY_LIST_KEYS", body(keys=[key(status="unknown")])),
    ("KEY_LIST_KEYS", body(keys=[key(test=1)])),
    ("KEY_LIST_KEYS", body(keys=[key(not_after="2027-01-31T00:00:00Z")])),
    ("KEY_LIST_KEYS", body(keys=[key("a"), key("a", seed=OTHER_SEED)])),
    ("KEY_LIST_KEYS", body(keys=[key("b"), key("a", seed=OTHER_SEED)])),
    ("KEY_LIST_KEYS", body(keys=[key("a"), key("b")])),
])
def test_malformed_lists_are_refused_even_with_a_valid_root_signature(store, code, document):
    refused(code, accept, store, document)
    assert events(store) == 0


def test_non_canonical_bytes_are_refused(store):
    raw = json.dumps(body(), indent=1).encode()
    envelope = {"key_list": raw.decode(), "sig": sr.sign(ROOT_SEED, kl.DOMAIN + raw).hex()}
    refused("NON_CANONICAL", accept, store, envelope=envelope)


@pytest.mark.parametrize("envelope", [None, {}, {"key_list": 1, "sig": "00"}, {"key_list": "{}", "sig": "zz"},
                                      {"key_list": "x" * (kl.MAX_BYTES + 1), "sig": "00"}])
def test_malformed_envelopes_are_refused(envelope):
    refused("MALFORMED", kl.verify_key_list, envelope, root=ROOT, now=NOW, allow_test_keys=True)


@pytest.mark.parametrize("code,now", [
    ("KEY_LIST_NOT_YET_VALID", datetime(2026, 11, 24, 11, 59, 29, tzinfo=timezone.utc)),
    ("KEY_LIST_STALE", datetime(2026, 11, 24, 12, 15, tzinfo=timezone.utc)),
    ("BAD_CLOCK", datetime(2026, 11, 24, 12, 1)),
])
def test_lists_outside_their_signed_time_are_refused(store, code, now):
    refused(code, accept, store, now=now)
    assert events(store) == 0


def test_list_that_expires_while_waiting_for_the_lock_is_not_recorded(store):
    readings = iter([NOW, NOW + timedelta(minutes=20)])
    refused("KEY_LIST_STALE", accept, store, clock=lambda: next(readings))
    assert events(store) == 0


def test_lower_version_is_refused_after_a_newer_one(store):
    accept(store, body(5))
    refused("KEY_LIST_ROLLBACK", accept, store, body(4))
    assert events(store) == 1


def test_rollback_is_still_refused_after_reopening_the_store(tmp_path):
    db_path, anchor_path = tmp_path / "audit.sqlite3", tmp_path / "anchors" / "a.jsonl"
    chain = AuditChainStore(db_path)
    bootstrap_anchor(chain, AnchorStore(anchor_path, "c"), performed_by="maint-1")
    chain.close()
    with open_anchored_audit(db_path, anchor_path, "c") as writer:
        accept(writer, body(1))
        accept(writer, body(2))
    with open_anchored_audit(db_path, anchor_path, "c") as writer:
        refused("KEY_LIST_SUPERSEDED", accept, writer, body(1))
        assert accept(writer, body(2)).list_version == 2


def test_newest_identical_list_can_be_loaded_again_without_a_new_event(store):
    first = accept(store)
    assert accept(store).list_hash == first.list_hash
    assert events(store) == 1


def test_same_version_with_different_content_is_refused(store):
    accept(store)
    refused("KEY_LIST_SUPERSEDED", accept, store, body(keys=[key(status="revoked")]))
    assert events(store) == 1


@pytest.mark.parametrize("earlier,later", [("revoked", "active"), ("revoked", "retired"), ("retired", "active")])
def test_key_status_never_moves_backwards(store, earlier, later):
    accept(store, body(1, [key(status=earlier)]))
    refused("KEY_STATUS_REGRESSION", accept, store, body(2, [key(status=later)]))


def test_revoked_key_cannot_return_after_being_omitted_from_a_list(store):
    accept(store, body(1, [key(status="revoked")]))
    accept(store, body(2, [key("other", seed=OTHER_SEED)]))
    refused("KEY_STATUS_REGRESSION", accept, store, body(3, [key()]))


@pytest.mark.parametrize("rebound", [key("fresh-name"), key(seed=OTHER_SEED)], ids=["new-id", "new-public"])
def test_key_id_and_public_key_stay_bound_together(store, rebound):
    accept(store, body(1, [key(status="revoked")]))
    refused("KEY_REBOUND", accept, store, body(2, [rebound]))


def test_second_tenant_in_the_same_store_is_refused(store):
    accept(store)
    refused("TENANT_MISMATCH", accept, store, body(2), tenant="tenant-other")


def test_unanchored_writer_is_refused(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.sqlite3")
    try:
        refused("AUDIT_REQUIRED", accept, chain)
    finally:
        chain.close()


@pytest.mark.parametrize("event", [
    {"event_id": "key-list-accept-000000000009", "event_type": "other",
     "resource_ids": [json.dumps([TENANT, ROOT.key_id, 9])], "key_list_hash": "sha256:0"},
    {"event_id": "key-list-accept-000000000009", "event_type": "key_list_accepted",
     "resource_ids": [json.dumps([TENANT, ROOT.key_id, 8])], "key_list_hash": "sha256:0"},
    {"event_id": "key-list-accept-junk", "event_type": "key_list_accepted", "resource_ids": ["["]},
])
def test_unreadable_history_stops_further_acceptance(store, event):
    store.append(event)
    refused("KEY_LIST_HISTORY", accept, store, body(20))


def test_anchor_write_failure_means_the_list_must_not_be_used(store, monkeypatch):
    monkeypatch.setattr(store.anchors, "advance", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    refused("AUDIT_ANCHOR_WRITE_FAILED", accept, store)
    monkeypatch.undo()
    refused("AUDIT_UNANCHORED", accept, store)


def test_revocation_stops_an_older_list_still_held_in_memory(store):
    old = accept(store, body(1))
    new = accept(store, body(2, [key(status="revoked")]))
    before = events(store)
    refused("KEY_LIST_SUPERSEDED", admit, store, old)
    refused("KEY_NOT_ACTIVE", admit, store, new)
    assert events(store) == before


def test_unaccepted_list_object_cannot_admit(store):
    forged = kl.TrustedKeyList(sr.canonical_bytes(body()), NOW, 100.0)
    refused("KEY_LIST_NOT_ACCEPTED", admit, store, forged)
    accept(store, body(1, [key("other", seed=OTHER_SEED)]))
    refused("KEY_LIST_SUPERSEDED", admit, store, forged)
    assert events(store) == 1


@pytest.mark.parametrize("elapsed", [900.001, -1.0, math.nan])
def test_monotonic_age_is_bounded(store, elapsed):
    trusted = accept(store)
    refused("KEY_LIST_STALE", admit, store, trusted, monotonic=lambda: 100.0 + elapsed)
    assert events(store) == 1


def test_clock_rolled_back_since_verification_is_refused(store):
    trusted = accept(store)
    refused("BAD_CLOCK", admit, store, trusted, now=NOW - timedelta(seconds=1))


def test_stale_list_refuses_new_receipts(store):
    trusted = accept(store)
    late = datetime(2026, 11, 24, 12, 15, tzinfo=timezone.utc)
    refused("KEY_LIST_STALE", admit, store, trusted, now=late,
            issued_at="2026-11-24T12:14:00Z", expires_at="2026-11-24T12:19:00Z")


@pytest.mark.parametrize("late_clock,late_mono", [(True, False), (False, True)])
def test_list_that_goes_stale_while_waiting_for_the_lock_consumes_nothing(store, late_clock, late_mono):
    trusted = accept(store, body(expires_at="2026-11-24T12:02:00Z"))
    wall = iter([NOW, NOW, NOW + timedelta(minutes=2) if late_clock else NOW])
    mono = iter([100.0, 2000.0 if late_mono else 100.0])
    refused("KEY_LIST_STALE", admit, store, trusted, clock=lambda: next(wall), monotonic=lambda: next(mono))
    assert events(store) == 1


def test_list_superseded_between_key_load_and_commit_consumes_nothing(store):
    trusted = accept(store)
    calls = []

    def clock():
        calls.append(1)
        if len(calls) == 2:  # after the keys were read, before the consumption transaction
            accept(store, body(2, [key(status="revoked")]))
        return NOW

    refused("KEY_LIST_SUPERSEDED", admit, store, trusted, clock=clock)
    assert events(store) == 2

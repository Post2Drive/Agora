"""Phase 1 signed receipts: format, verifier and forged-receipt refusals (test keys only, no engine wiring)."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agora.security import signed_receipt as sr

VEC = json.loads((Path(__file__).parent / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))
TK = VEC["test_key"]
SEED = bytes.fromhex(TK["seed_hex"])
BASE = VEC["base_receipt"]
SCOPE = {k: BASE[k] for k in ("tenant", "subject", "project", "import_id", "binding_id", "manifest_hash",
                              "scenario_hash", "purpose")}


def ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def keys(status="active", test=True, not_before=None, not_after=None):
    entry = sr.KeyEntry(TK["key_id"], bytes.fromhex(TK["public_hex"]), not_before or TK["not_before"],
                        not_after or TK["not_after"], status=status, test=test)
    return {TK["key_id"]: entry}


def signed(**changes):
    receipt = {**BASE, **changes}
    return sr.make_receipt(SEED, receipt)


def check(envelope, now="2026-11-24T12:01:00Z", expected=None, nonces=None, **kw):
    return sr.verify_receipt(envelope, keys=kw.pop("keys", keys()), now=ts(now), expected=SCOPE if expected is None else expected,
                             nonces=nonces or sr.NonceStore(), allow_test_keys=kw.pop("allow", True), **kw)


# ---- primitive
@pytest.mark.parametrize("vec", VEC["rfc8032"])
def test_ed25519_matches_rfc8032_vector(vec):
    seed, msg = bytes.fromhex(vec["seed_hex"]), bytes.fromhex(vec["message_hex"])
    assert sr.public_key(seed).hex() == vec["public_hex"]
    assert sr.sign(seed, msg).hex() == vec["signature_hex"]
    assert sr.verify_signature(bytes.fromhex(vec["public_hex"]), msg, bytes.fromhex(vec["signature_hex"]))


def test_signature_with_a_flipped_bit_or_wrong_message_is_refused():
    pub = sr.public_key(SEED)
    sig = sr.sign(SEED, b"m")
    assert sr.verify_signature(pub, b"m", sig)
    assert not sr.verify_signature(pub, b"n", sig)
    flipped = bytes([sig[0] ^ 1]) + sig[1:]
    assert not sr.verify_signature(pub, b"m", flipped)


def test_signature_with_s_at_or_above_group_order_is_refused():
    pub = sr.public_key(SEED)
    sig = sr.sign(SEED, b"m")
    s = int.from_bytes(sig[32:], "little") + sr._Q
    assert not sr.verify_signature(pub, b"m", sig[:32] + (s % 2**256).to_bytes(32, "little"))


def test_malformed_public_key_or_signature_lengths_are_refused():
    assert not sr.verify_signature(b"\x00" * 31, b"m", b"\x00" * 64)
    assert not sr.verify_signature(sr.public_key(SEED), b"m", b"\x00" * 63)


# ---- vectors made by an independent implementation
@pytest.mark.parametrize("case", VEC["cases"], ids=lambda c: c["name"])
def test_independent_vectors(case):
    if case["verdict"] == "ok":
        assert check(case["envelope"], now=case["now"], expected=case["expected"])["nonce"] == BASE["nonce"]
    else:
        with pytest.raises(sr.ReceiptError) as err:
            check(case["envelope"], now=case["now"], expected=case["expected"])
        assert err.value.code == case["verdict"]


# ---- refusals that must hold
def refused(code, *args, **kw):
    with pytest.raises(sr.ReceiptError) as err:
        check(*args, **kw)
    assert err.value.code == code


def test_valid_receipt_is_accepted_once_and_replay_is_refused():
    nonces, env = sr.NonceStore(), signed()
    assert check(env, nonces=nonces)["tenant"] == "tenant-a"
    refused("REPLAY", env, nonces=nonces)


def test_failed_checks_do_not_burn_the_nonce():
    nonces, env = sr.NonceStore(), signed()
    refused("SCOPE_MISMATCH", env, expected={**SCOPE, "tenant": "tenant-b"}, nonces=nonces)
    refused("EXPIRED", env, now="2026-11-24T12:06:00Z", nonces=nonces)
    assert check(env, nonces=nonces)  # still usable for the right scope and time


def test_test_keys_are_refused_unless_explicitly_allowed():
    refused("TEST_KEY_REFUSED", signed(), allow=False)


@pytest.mark.parametrize("status", ["revoked", "retired", "pending"])
def test_inactive_keys_are_refused(status):
    refused("KEY_NOT_ACTIVE", signed(), keys=keys(status=status))


def test_receipt_outside_key_validity_window_is_refused():
    refused("KEY_OUT_OF_WINDOW", signed(), keys=keys(not_before="2026-11-25T00:00:00Z", not_after="2027-01-01T00:00:00Z"))


def test_expiry_boundary_and_future_issue_with_skew():
    refused("EXPIRED", signed(), now="2026-11-24T12:05:00Z")
    assert check(signed(), now="2026-11-24T12:04:59Z")
    assert check(signed(nonce="1" * 32), now="2026-11-24T11:59:31Z")  # within 30 s skew of issue time
    refused("NOT_YET_VALID", signed(nonce="2" * 32), now="2026-11-24T11:59:29Z")


def test_every_scope_field_is_enforced():
    for name in SCOPE:
        refused("SCOPE_MISMATCH", signed(nonce="3" * 32), expected={**SCOPE, name: "other"})


def test_empty_scope_is_refused_so_a_caller_cannot_skip_the_scope_check():
    refused("NO_SCOPE", signed(), expected={})


def test_unknown_expected_field_is_a_scope_mismatch_not_ignored():
    refused("SCOPE_MISMATCH", signed(), expected={**SCOPE, "not_a_field": "x"})


def test_forged_signature_from_another_key_is_refused():
    other = bytes(range(32, 64))
    forged = sr.make_receipt(other, BASE)
    refused("BAD_SIGNATURE", forged)


def test_signature_does_not_transfer_between_receipts():
    a, b = signed(), signed(purpose="export", nonce="4" * 32)
    refused("BAD_SIGNATURE", {"receipt": b["receipt"], "sig": a["sig"]}, expected={**SCOPE, "purpose": "export"})


def test_non_canonical_floats_and_duplicate_keys_are_refused():
    refused("NON_CANONICAL", {"receipt": json.dumps(BASE, sort_keys=True), "sig": "00" * 64})
    refused("NON_CANONICAL", {"receipt": '{"v":1,"v":1}', "sig": "00" * 64})
    refused("NON_CANONICAL", {"receipt": '{"v":1.0}', "sig": "00" * 64})
    with pytest.raises(sr.ReceiptError) as err:
        sr.canonical_bytes({"v": 1.5})
    assert err.value.code == "NON_CANONICAL"


def test_wrong_version_type_and_unknown_fields_are_refused():
    for bad in ({"v": True}, {"v": 2}, {"alg": "Ed25519"}):
        with pytest.raises(sr.ReceiptError):
            sr.validate_shape({**BASE, **bad})
    with pytest.raises(sr.ReceiptError):
        sr.validate_shape({**BASE, "extra": "x"})
    missing = dict(BASE)
    del missing["nonce"]
    with pytest.raises(sr.ReceiptError):
        sr.validate_shape(missing)


def test_bad_field_formats_and_lifetime_are_refused():
    for change in ({"tenant": "has space"}, {"manifest_hash": "sha256:xyz"}, {"nonce": "short"},
                   {"issued_at": "2026-11-24T12:00:00+00:00"}, {"expires_at": "2026-11-24T12:10:00Z"},
                   {"expires_at": "2026-11-24T11:00:00Z"}):
        with pytest.raises(sr.ReceiptError):
            sr.validate_shape({**BASE, **change})


def test_malformed_envelopes_are_refused():
    for env in ({}, {"receipt": "x"}, {"receipt": 1, "sig": "00"}, {"receipt": "é", "sig": "00"},
                {"receipt": "{}", "sig": "zz"}, {"receipt": "{}", "sig": "00", "extra": 1}):
        with pytest.raises(sr.ReceiptError):
            check(env)


def test_naive_clock_is_refused():
    with pytest.raises(sr.ReceiptError) as err:
        sr.verify_receipt(signed(), keys=keys(), now=datetime(2026, 11, 24, 12, 1), expected=SCOPE,
                          nonces=sr.NonceStore(), allow_test_keys=True)
    assert err.value.code == "BAD_CLOCK"


def test_concurrent_replay_has_exactly_one_winner():
    env, nonces, wins = signed(), sr.NonceStore(), []
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        try:
            check(env, nonces=nonces)
            wins.append(1)
        except sr.ReceiptError:
            pass

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1

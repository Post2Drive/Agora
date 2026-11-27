"""Signed approval statements: format, verifier and refusals (test keys only; nothing calls them)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agora.security import approval_receipt as ap
from agora.security import signed_receipt as sr

TK = json.loads((Path(__file__).parent / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))["test_key"]
SEED = bytes.fromhex(TK["seed_hex"])
BASE = {
    "type": "action_approval", "v": 1, "alg": "ed25519", "tenant": "tenant-test", "release_id": "release-test",
    "project": "project-1", "proposal_digest": "sha256:" + "a" * 64, "proposed_by": "operator-1",
    "approved_by": "approver-1", "key_id": TK["key_id"], "issued_at": "2026-11-24T12:00:00Z",
    "expires_at": "2026-11-24T12:05:00Z",
}
SCOPE = {name: BASE[name] for name in ap.SCOPE_FIELDS}


def ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def keys(status="active", test=True, not_before=None, not_after=None):
    return {TK["key_id"]: sr.KeyEntry(
        TK["key_id"], bytes.fromhex(TK["public_hex"]), not_before or TK["not_before"],
        not_after or TK["not_after"], status=status, test=test)}


def signed(**changes):
    return ap.make_approval_statement(SEED, {**BASE, **changes})


def raw_signed(statement, domain=ap.DOMAIN):
    """Sign without the shape check, to reach the verifier's own checks."""
    body = sr.canonical_bytes(statement)
    return {"statement": body.decode("ascii"), "sig": sr.sign(SEED, domain + body).hex()}


def check(envelope, now="2026-11-24T12:01:00Z", expected=None, trusted=None, allow=True):
    return ap.verify_approval_statement(
        envelope, keys=keys() if trusted is None else trusted, now=ts(now),
        expected=SCOPE if expected is None else expected, allow_test_keys=allow)


def refused(code, *args, **kwargs):
    with pytest.raises(sr.ReceiptError) as err:
        check(*args, **kwargs)
    assert err.value.code == code


def test_a_matching_statement_verifies_and_is_not_single_use():
    envelope = signed()
    assert check(envelope) == BASE
    assert check(envelope) == BASE


@pytest.mark.parametrize("domain", [sr.DOMAIN, b""])
def test_a_signature_made_under_another_domain_is_refused(domain):
    refused("BAD_SIGNATURE", raw_signed(BASE, domain))


def test_the_approval_domain_does_not_validate_as_a_run_receipt():
    assert ap.DOMAIN != sr.DOMAIN


def test_a_changed_statement_is_refused():
    envelope = signed()
    envelope["statement"] = envelope["statement"].replace("approver-1", "approver-2")
    refused("BAD_SIGNATURE", envelope, expected={**SCOPE, "approved_by": "approver-2"})


@pytest.mark.parametrize("name", ap.SCOPE_FIELDS)
def test_every_scope_field_must_match(name):
    other = "sha256:" + "b" * 64 if name == "proposal_digest" else "someone-else"
    refused("SCOPE_MISMATCH", signed(), expected={**SCOPE, name: other})


@pytest.mark.parametrize("expected", [
    {}, {k: v for k, v in SCOPE.items() if k != "approved_by"}, {**SCOPE, "extra": "x"}])
def test_the_caller_must_name_the_whole_scope(expected):
    refused("INCOMPLETE_SCOPE", signed(), expected=expected)


def test_a_proposer_cannot_be_stated_as_their_own_approver():
    with pytest.raises(sr.ReceiptError, match="SELF_APPROVAL"):
        signed(approved_by="operator-1")
    refused("SELF_APPROVAL", raw_signed({**BASE, "approved_by": "operator-1"}),
            expected={**SCOPE, "approved_by": "operator-1"})


@pytest.mark.parametrize("changes,code", [
    ({"type": "receipt"}, "BAD_TYPE"), ({"v": 2}, "BAD_VERSION"), ({"v": True}, "BAD_VERSION"),
    ({"alg": "none"}, "BAD_ALGORITHM"), ({"tenant": "two words"}, "BAD_FIELD"),
    ({"approved_by": ""}, "BAD_FIELD"), ({"proposal_digest": "a" * 64}, "BAD_FIELD"),
    ({"expires_at": "2026-11-24T12:05:01Z"}, "BAD_LIFETIME"),
    ({"expires_at": "2026-11-24T12:00:00Z"}, "BAD_LIFETIME"), ({"note": "x"}, "BAD_FIELDS")])
def test_the_shape_is_checked_on_both_sides(changes, code):
    with pytest.raises(sr.ReceiptError) as err:
        signed(**changes)
    assert err.value.code == code
    refused(code, raw_signed({**BASE, **changes}))


def test_non_canonical_bytes_are_refused():
    body = json.dumps(BASE).encode("ascii")
    refused("NON_CANONICAL", {"statement": body.decode(), "sig": sr.sign(SEED, ap.DOMAIN + body).hex()})


@pytest.mark.parametrize("envelope", [
    None, {}, {"statement": "{}"}, {"statement": "{}", "sig": 1}, {"statement": "{}", "sig": "zz"},
    {"statement": "é", "sig": "00"}, {"statement": "{}", "sig": "00", "key": "x"}])
def test_a_malformed_envelope_is_refused(envelope):
    refused("MALFORMED", envelope)


@pytest.mark.parametrize("kwargs,code", [
    ({"trusted": {}}, "UNKNOWN_KEY"), ({"allow": False}, "TEST_KEY_REFUSED"),
    ({"trusted": keys(status="retired")}, "KEY_NOT_ACTIVE"),
    ({"trusted": keys(status="revoked")}, "KEY_NOT_ACTIVE"),
    ({"trusted": keys(not_before="2026-11-24T12:00:01Z")}, "KEY_OUT_OF_WINDOW"),
    ({"trusted": keys(not_after="2026-11-24T11:59:59Z")}, "KEY_OUT_OF_WINDOW"),
    ({"now": "2026-11-24T11:59:29Z"}, "NOT_YET_VALID"), ({"now": "2026-11-24T12:05:00Z"}, "EXPIRED")])
def test_key_and_time_refusals(kwargs, code):
    refused(code, signed(), **kwargs)


def test_test_keys_are_refused_unless_asked_for():
    with pytest.raises(sr.ReceiptError, match="TEST_KEY_REFUSED"):
        ap.verify_approval_statement(signed(), keys=keys(), now=ts("2026-11-24T12:01:00Z"), expected=SCOPE)


def test_a_clock_without_a_timezone_is_refused():
    with pytest.raises(sr.ReceiptError, match="BAD_CLOCK"):
        ap.verify_approval_statement(signed(), keys=keys(), now=datetime(2026, 11, 24, 12, 1),
                                     expected=SCOPE, allow_test_keys=True)


def test_only_the_receipt_gate_uses_the_verifier():
    """Admission reaches statements through the gate, which supplies the trust. A second caller would
    have to choose its own keys; whoever adds one must update the documents and this test."""
    package = Path(ap.__file__).resolve().parents[1]
    users = [p.name for p in package.rglob("*.py")
             if p.name != "approval_receipt.py" and "approval_receipt" in p.read_text(encoding="utf-8")]
    assert users == ["receipt_gate.py"]

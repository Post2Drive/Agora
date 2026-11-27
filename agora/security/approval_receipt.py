"""Signed approval statements for ontology action proposals: format and local verifier, test keys only.

An approval in the audit chain (``agora.ontology.approvals``) rests on a local file: whoever can rewrite
the chain and its anchor can forge one. This statement is the start of a second root of trust: the holder
of a signing key states that one identity approved one proposal digest that another identity proposed, in
one tenant, project and release, for at most five minutes.

Nothing calls this module. No admission requires a statement yet, so it protects nothing today. The caller
passes the trusted keys and the clock. A verified statement can be verified again until it expires; it is
not single-use by itself (an admission in the chain is). No production key exists, and the signer used here
is not constant-time. The format reuses the canonical bytes, key entry and Ed25519 verifier of
``signed_receipt`` under its own domain tag, so neither kind of signature validates as the other.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3A and 3B.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

from agora.security import signed_receipt as sr

DOMAIN = b"agora.approval.v1\x00"
OBJECT_TYPE = "action_approval"
VERSION = 1
FIELDS = (
    "type", "v", "alg", "tenant", "release_id", "project", "proposal_digest", "proposed_by",
    "approved_by", "key_id", "issued_at", "expires_at",
)
SCOPE_FIELDS = ("tenant", "release_id", "project", "proposal_digest", "proposed_by", "approved_by")
_TOKEN_FIELDS = ("tenant", "release_id", "project", "proposed_by", "approved_by", "key_id")


def validate_shape(statement: Mapping[str, Any]) -> None:
    if set(statement) != set(FIELDS):
        extra, missing = sorted(set(statement) - set(FIELDS)), sorted(set(FIELDS) - set(statement))
        raise sr.ReceiptError("BAD_FIELDS", f"unknown={extra} missing={missing}")
    if statement["type"] != OBJECT_TYPE:
        raise sr.ReceiptError("BAD_TYPE")
    if type(statement["v"]) is not int or statement["v"] != VERSION:
        raise sr.ReceiptError("BAD_VERSION")
    if statement["alg"] != sr.ALGORITHM:
        raise sr.ReceiptError("BAD_ALGORITHM")
    for name in _TOKEN_FIELDS:
        value = statement[name]
        if not isinstance(value, str) or not sr._TOKEN.match(value):
            raise sr.ReceiptError("BAD_FIELD", name)
    digest = statement["proposal_digest"]
    if not isinstance(digest, str) or not sr._HASH.match(digest):
        raise sr.ReceiptError("BAD_FIELD", "proposal_digest")
    if statement["proposed_by"] == statement["approved_by"]:
        raise sr.ReceiptError("SELF_APPROVAL")
    issued, expires = sr._parse_time(statement["issued_at"]), sr._parse_time(statement["expires_at"])
    if expires <= issued or (expires - issued).total_seconds() > sr.MAX_LIFETIME_SECONDS:
        raise sr.ReceiptError("BAD_LIFETIME")


def make_approval_statement(seed: bytes, statement: Mapping[str, Any]) -> dict[str, str]:
    """Sign a statement (test keys only)."""
    validate_shape(statement)
    body = sr.canonical_bytes(statement)
    return {"statement": body.decode("ascii"), "sig": sr.sign(seed, DOMAIN + body).hex()}


def verify_approval_statement(
    envelope: Mapping[str, Any], *, keys: Mapping[str, sr.KeyEntry], now: datetime,
    expected: Mapping[str, str], allow_test_keys: bool = False,
) -> dict[str, Any]:
    """Return the verified statement or raise ``signed_receipt.ReceiptError``.

    ``expected`` must contain exactly the ``SCOPE_FIELDS``. The caller must take them from what it is
    about to act on (its own configuration, and the approval it verified in its own chain), never from
    the statement.
    """
    if not isinstance(expected, Mapping) or set(expected) != set(SCOPE_FIELDS):
        raise sr.ReceiptError("INCOMPLETE_SCOPE", "expected must name exactly the statement's scope")
    if (not isinstance(envelope, Mapping) or set(envelope) != {"statement", "sig"}
            or not all(isinstance(v, str) for v in envelope.values())):
        raise sr.ReceiptError("MALFORMED", "envelope must be exactly {statement, sig}")
    try:
        body = envelope["statement"].encode("ascii")
        signature = bytes.fromhex(envelope["sig"])
    except (UnicodeEncodeError, ValueError) as exc:
        raise sr.ReceiptError("MALFORMED", "statement must be ASCII and sig hex") from exc
    statement = sr.parse_canonical(body)
    validate_shape(statement)
    entry = keys.get(statement["key_id"])
    if entry is None:
        raise sr.ReceiptError("UNKNOWN_KEY")
    if entry.test and not allow_test_keys:
        raise sr.ReceiptError("TEST_KEY_REFUSED")
    if entry.status != "active":
        raise sr.ReceiptError("KEY_NOT_ACTIVE", entry.status)
    if not sr.verify_signature(entry.public, DOMAIN + body, signature):
        raise sr.ReceiptError("BAD_SIGNATURE")
    if now.tzinfo is None:
        raise sr.ReceiptError("BAD_CLOCK", "now must be timezone-aware")
    issued, expires = sr._parse_time(statement["issued_at"]), sr._parse_time(statement["expires_at"])
    if not (entry.not_before <= issued <= entry.not_after):
        raise sr.ReceiptError("KEY_OUT_OF_WINDOW")
    if issued > now + timedelta(seconds=sr.CLOCK_SKEW_SECONDS):
        raise sr.ReceiptError("NOT_YET_VALID")
    if now >= expires:
        raise sr.ReceiptError("EXPIRED")
    for name in SCOPE_FIELDS:
        if statement[name] != expected[name]:
            raise sr.ReceiptError("SCOPE_MISMATCH", name)
    return statement


__all__ = ["DOMAIN", "FIELDS", "SCOPE_FIELDS", "make_approval_statement", "validate_shape",
           "verify_approval_statement"]

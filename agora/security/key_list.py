"""Signed key list for receipt keys: pinned root, bounded freshness and durable rollback protection.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3A and 3B (items 1, 3 and 4).

Online receipt keys are trusted only through a list signed by ONE pinned root key. Accepting a list appends a
``key_list_accepted`` event to the tenant's anchored audit chain; that history is the rollback state. A list is
refused when its version is lower than one already accepted, when the same version has different bytes, when
a key's status moves backwards (active -> retired -> revoked), or when a key id or public key is re-bound.

``admit_receipt_with_key_list`` also checks, inside the transaction that consumes the nonce, that the list in
use is still the newest accepted one and is still fresh, so an older list held in memory cannot admit a receipt
after a revocation has been accepted in that store.

Test keys only. NOT wired into the engine. Not built: root rollover or root revocation, list distribution,
a trusted time source (the caller passes ``clock`` and ``monotonic``). Not a boundary against code in the same
process (which can append events or call ``admit_receipt`` with its own keys) or an owner of both the audit
database and the anchor.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from agora.audit_anchor import AnchoredAuditChain, AnchorRequiredError, AnchorWriteError, require_anchored
from agora.audit_chain import AuditReplayError
from agora.security import receipt_ledger as ledger
from agora.security import signed_receipt as sr

DOMAIN = b"agora.keylist.v1\x00"
OBJECT_TYPE = "key_list"
VERSION = 1
MAX_LIST_AGE_SECONDS = 900
MAX_KEY_LIFETIME = timedelta(days=90)
MAX_KEYS = 64
MAX_BYTES = 64 * 1024
MAX_LIST_VERSION = 10**12 - 1
EVENT_PREFIX = "key-list-accept-"
EVENT_TYPE = "key_list_accepted"
_FIELDS = {"type", "v", "alg", "list_version", "issued_at", "expires_at", "root_key_id", "keys"}
_KEY_FIELDS = {"key_id", "public", "not_before", "not_after", "status", "test"}
_STATUS_RANK = {"active": 0, "retired": 1, "revoked": 2}


def fingerprint(public: bytes) -> str:
    return "sha256:" + hashlib.sha256(public).hexdigest()


@dataclass(frozen=True)
class RootKey:
    """The one pinned root public key, from the worker's own configuration, never from a request."""

    public: bytes
    test: bool = False

    @property
    def key_id(self) -> str:
        return fingerprint(self.public)


def _refuse(code: str, detail: str = "") -> sr.ReceiptError:
    return sr.ReceiptError(code, detail)


def _usable_point(public: bytes) -> bool:
    point = sr._decompress(public)
    return point is not None and sr._compress(point) == public and sr._is_prime_order_nonidentity(point)


def _validate(body: Mapping[str, Any]) -> None:
    if set(body) != _FIELDS:
        raise _refuse("KEY_LIST_FIELDS")
    if body["type"] != OBJECT_TYPE:
        raise _refuse("KEY_LIST_TYPE")
    if type(body["v"]) is not int or body["v"] != VERSION:
        raise _refuse("BAD_VERSION")
    if body["alg"] != sr.ALGORITHM:
        raise _refuse("BAD_ALGORITHM")
    version = body["list_version"]
    if type(version) is not int or not 1 <= version <= MAX_LIST_VERSION:
        raise _refuse("KEY_LIST_VERSION")
    issued, expires = sr._parse_time(body["issued_at"]), sr._parse_time(body["expires_at"])
    if not timedelta(0) < expires - issued <= timedelta(seconds=MAX_LIST_AGE_SECONDS):
        raise _refuse("KEY_LIST_LIFETIME")
    keys = body["keys"]
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_KEYS:
        raise _refuse("KEY_LIST_KEYS", "between 1 and 64 keys")
    ids: list[str] = []
    publics: set[str] = set()
    for key in keys:
        if not isinstance(key, dict) or set(key) != _KEY_FIELDS:
            raise _refuse("KEY_LIST_KEYS", "unknown or missing key field")
        if not isinstance(key["key_id"], str) or not sr._TOKEN.match(key["key_id"]):
            raise _refuse("KEY_LIST_KEYS", "key_id")
        text = key["public"]
        if not isinstance(text, str) or len(text) != 72 or not text.startswith("ed25519:") \
                or any(c not in "0123456789abcdef" for c in text[8:]):
            raise _refuse("KEY_LIST_KEYS", "public")
        public = bytes.fromhex(text[8:])
        if not _usable_point(public):
            raise _refuse("KEY_LIST_KEYS", "public key is not a usable Ed25519 point")
        if fingerprint(public) == body["root_key_id"]:
            raise _refuse("KEY_LIST_KEYS", "the offline root key must not be an online key")
        if not isinstance(key["status"], str) or key["status"] not in _STATUS_RANK:
            raise _refuse("KEY_LIST_KEYS", "status")
        if type(key["test"]) is not bool:
            raise _refuse("KEY_LIST_KEYS", "test")
        window = sr._parse_time(key["not_after"]) - sr._parse_time(key["not_before"])
        if not timedelta(0) < window <= MAX_KEY_LIFETIME:
            raise _refuse("KEY_LIST_KEYS", "key validity window")
        ids.append(key["key_id"])
        publics.add(text)
    if ids != sorted(set(ids)) or len(publics) != len(ids):
        raise _refuse("KEY_LIST_KEYS", "key ids must be sorted and unique, public keys unique")


def make_key_list(seed: bytes, body: Mapping[str, Any]) -> dict[str, str]:
    """Sign a key list with a TEST root seed. Returns the wire envelope {key_list, sig}."""
    _validate(body)
    raw = sr.canonical_bytes(body)
    return {"key_list": raw.decode("ascii"), "sig": sr.sign(seed, DOMAIN + raw).hex()}


def _check_fresh(body: Mapping[str, Any], now: datetime) -> None:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise _refuse("BAD_CLOCK", "now must be timezone-aware")
    issued, expires = sr._parse_time(body["issued_at"]), sr._parse_time(body["expires_at"])
    if issued > now + timedelta(seconds=sr.CLOCK_SKEW_SECONDS):
        raise _refuse("KEY_LIST_NOT_YET_VALID")
    if now >= expires or now - issued > timedelta(seconds=MAX_LIST_AGE_SECONDS):
        raise _refuse("KEY_LIST_STALE")


def verify_key_list(envelope: Mapping[str, Any], *, root: RootKey, now: datetime,
                    allow_test_keys: bool = False) -> bytes:
    """Signature, shape and freshness only. Returns the signed canonical bytes.

    This does NOT check rollback; use ``accept_key_list`` before trusting any key.
    """
    if not isinstance(envelope, Mapping) or set(envelope) != {"key_list", "sig"}:
        raise _refuse("MALFORMED", "envelope must be exactly {key_list, sig}")
    text, sig = envelope["key_list"], envelope["sig"]
    if not isinstance(text, str) or not isinstance(sig, str) or len(text) > MAX_BYTES:
        raise _refuse("MALFORMED", "key_list and sig must be strings of bounded size")
    try:
        raw, signature = text.encode("ascii"), bytes.fromhex(sig)
    except (UnicodeEncodeError, ValueError) as exc:
        raise _refuse("MALFORMED", "key_list must be ASCII and sig hex") from exc
    if root.test and not allow_test_keys:
        raise _refuse("TEST_KEY_REFUSED", "test root")
    # Verify the signature over the received bytes before interpreting them.
    if not sr.verify_signature(root.public, DOMAIN + raw, signature):
        raise _refuse("BAD_SIGNATURE")
    body = sr.parse_canonical(raw)
    _validate(body)
    if body["root_key_id"] != root.key_id:
        raise _refuse("KEY_LIST_ROOT")
    if not allow_test_keys and any(key["test"] for key in body["keys"]):
        raise _refuse("TEST_KEY_REFUSED", "list contains test keys")
    _check_fresh(body, now)
    return raw


@dataclass(frozen=True)
class TrustedKeyList:
    """An accepted list. Holding one proves nothing: admission re-checks its bytes against the audit chain."""

    signed_bytes: bytes
    verified_at: datetime
    verified_monotonic: float

    @property
    def list_hash(self) -> str:
        return "sha256:" + hashlib.sha256(DOMAIN + self.signed_bytes).hexdigest()

    @property
    def list_version(self) -> int:
        return json.loads(self.signed_bytes)["list_version"]

    def check_fresh(self, now: datetime, monotonic_now: float) -> None:
        _check_fresh(json.loads(self.signed_bytes), now)
        if now < self.verified_at:
            raise _refuse("BAD_CLOCK", "trusted time moved backwards since the list was verified")
        elapsed = monotonic_now - self.verified_monotonic
        if not 0 <= elapsed <= MAX_LIST_AGE_SECONDS:  # also false for NaN
            raise _refuse("KEY_LIST_STALE", "monotonic age")

    def keys(self, now: datetime, monotonic_now: float) -> dict[str, sr.KeyEntry]:
        self.check_fresh(now, monotonic_now)
        return {
            k["key_id"]: sr.KeyEntry(k["key_id"], bytes.fromhex(k["public"][8:]), k["not_before"],
                                     k["not_after"], status=k["status"], test=k["test"])
            for k in json.loads(self.signed_bytes)["keys"]
        }


def _event_id(version: int) -> str:
    return f"{EVENT_PREFIX}{version:012d}"


def _history(db: sqlite3.Connection, *, excluding: str | None = None) -> list[dict[str, Any]]:
    """Accepted-list records in chain order. Any record this module cannot read refuses (fail closed)."""
    rows = db.execute(
        "SELECT event_id, event_json FROM audit_events WHERE substr(event_id, 1, ?)=? ORDER BY seq",
        (len(EVENT_PREFIX), EVENT_PREFIX),
    ).fetchall()
    records = []
    for event_id, raw in rows:
        if event_id == excluding:
            continue
        try:
            event = json.loads(raw)
            head, *entries = [json.loads(item) for item in event["resource_ids"]]
            tenant, root_key_id, version = head
            if event["event_type"] != EVENT_TYPE or _event_id(version) != event_id:
                raise ValueError("not an acceptance record")
            keys = [(str(i), str(f), _STATUS_RANK[s]) for i, f, s in entries]
            records.append({"tenant": tenant, "root": root_key_id, "version": version,
                            "hash": event["key_list_hash"], "keys": keys})
        except (ValueError, TypeError, KeyError) as exc:
            raise _refuse("KEY_LIST_HISTORY", "an acceptance record cannot be read") from exc
    return records


def _check_against_history(records, *, tenant: str, body: Mapping[str, Any]) -> None:
    if any(r["tenant"] != tenant for r in records):
        raise _refuse("TENANT_MISMATCH", "this store holds another tenant's key lists")
    if any(r["version"] >= body["list_version"] for r in records):
        raise _refuse("KEY_LIST_ROLLBACK", "a list of this or a higher version was already accepted")
    seen = [item for r in records for item in r["keys"]]
    for key in body["keys"]:
        public_print = fingerprint(bytes.fromhex(key["public"][8:]))
        for old_id, old_print, old_rank in seen:
            if (old_id == key["key_id"]) != (old_print == public_print):
                raise _refuse("KEY_REBOUND", key["key_id"])
            if old_id == key["key_id"] and _STATUS_RANK[key["status"]] < old_rank:
                raise _refuse("KEY_STATUS_REGRESSION", key["key_id"])


def _require_newest(db: sqlite3.Connection, tenant: str, list_hash: str) -> None:
    records = _history(db)
    if not records:
        raise _refuse("KEY_LIST_NOT_ACCEPTED", "this store has accepted no key list")
    newest = max(records, key=lambda r: r["version"])
    if newest["tenant"] != tenant or newest["hash"] != list_hash:
        raise _refuse("KEY_LIST_SUPERSEDED", "not the newest key list accepted in this store")


def accept_key_list(
    envelope: Mapping[str, Any], *, tenant: str, root: RootKey, audit: AnchoredAuditChain,
    clock: Callable[[], datetime], monotonic: Callable[[], float], allow_test_keys: bool = False,
) -> TrustedKeyList:
    """Verify, check against the accepted history and record the acceptance, in one anchored transaction.

    Presenting the newest accepted list again (same bytes) is allowed and appends nothing. ``root`` and
    ``tenant`` come from the worker's own configuration. On any exception the caller must keep no new keys.
    ``AUDIT_ANCHOR_WRITE_FAILED`` means the acceptance is committed but unanchored: the chain refuses further
    appends until an operator reconciles it.
    """
    try:
        writer = require_anchored(audit)
    except AnchorRequiredError as exc:
        raise _refuse("AUDIT_REQUIRED", "an anchored audit writer is required") from exc
    first, first_monotonic = clock(), monotonic()
    raw = verify_key_list(envelope, root=root, now=first, allow_test_keys=allow_test_keys)
    body = json.loads(raw)
    trusted = TrustedKeyList(raw, first, first_monotonic)
    event_id = _event_id(body["list_version"])
    entries = [[tenant, root.key_id, body["list_version"]]] + [
        [k["key_id"], fingerprint(bytes.fromhex(k["public"][8:])), k["status"]] for k in body["keys"]
    ]
    event = {
        "event_id": event_id, "event_type": EVENT_TYPE, "decision": "allow", "key_list_hash": trusted.list_hash,
        "resource_ids": [json.dumps(item, separators=(",", ":")) for item in entries],
    }

    def within_transaction(db: sqlite3.Connection) -> None:
        trusted.check_fresh(clock(), monotonic())
        _check_against_history(_history(db, excluding=event_id), tenant=tenant, body=body)

    try:
        writer.append(event, in_transaction=within_transaction)
    except sr.ReceiptError:
        raise
    except AuditReplayError:
        # This version is already recorded. Only the identical, still newest list may be loaded again.
        try:
            if writer.find_event(event_id) is None:
                raise _refuse("KEY_LIST_ERROR", "the recorded acceptance cannot be read")
            _require_newest(writer.chain.db, tenant, trusted.list_hash)
        except AnchorRequiredError as exc:
            raise _refuse("AUDIT_UNANCHORED", str(exc)) from exc
    except AnchorRequiredError as exc:
        raise _refuse("AUDIT_UNANCHORED", str(exc)) from exc
    except AnchorWriteError as exc:
        raise _refuse("AUDIT_ANCHOR_WRITE_FAILED", "do not use this list") from exc
    except Exception as exc:
        raise _refuse("KEY_LIST_ERROR", "the acceptance could not be committed") from exc
    return trusted


def admit_receipt_with_key_list(
    envelope: Mapping[str, Any], *, key_list: TrustedKeyList, tenant: str, audit: AnchoredAuditChain,
    clock: Callable[[], datetime], monotonic: Callable[[], float], expected: Mapping[str, str],
    allow_test_keys: bool = False,
) -> ledger.AdmittedReceipt:
    """``admit_receipt`` with keys taken only from the newest accepted, fresh key list of the same store."""
    keys = key_list.keys(clock(), monotonic())

    def still_current(db: sqlite3.Connection, now: datetime) -> None:
        _require_newest(db, tenant, key_list.list_hash)
        key_list.check_fresh(now, monotonic())

    return ledger.admit_receipt(
        envelope, tenant=tenant, audit=audit, keys=keys, clock=clock, expected=expected,
        allow_test_keys=allow_test_keys, guard=still_current,
    )


__all__ = ["RootKey", "TrustedKeyList", "accept_key_list", "admit_receipt_with_key_list", "fingerprint",
           "make_key_list", "verify_key_list"]

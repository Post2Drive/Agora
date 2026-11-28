"""Signed key list for receipt keys: pinned root, bounded freshness and durable rollback protection.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3A and 3B (items 1, 3 and 4).

Online receipt keys are trusted only through a list signed by the ACTIVE root: one of at most two pinned roots
(current and standby). Until a root change is accepted the active root is the configured current one; after
that it is the root recorded by the newest accepted list in the store. Accepting a list appends a
``key_list_accepted`` event to the tenant's anchored audit chain; that history is the rollback state. A list is
refused when its version rolls back within the current trust epoch, when the same version has different bytes, when
a key's status moves backwards (active -> retired -> revoked), or when a key id or public key is re-bound.

``admit_receipt_with_key_list`` also checks, inside the transaction that consumes the nonce, that the list in
use is still the newest accepted one and is still fresh, so an older list held in memory cannot admit a receipt
after a revocation has been accepted in that store.

Planned root rollover (accept_root_change) moves a store to the other pinned root and requires the active
root to sign the exact first list of the new root. The old root is then retired for that store. A standby root
cannot unilaterally revoke or replace the active root; emergency replacement uses accept_root_recovery and an
independent threshold of recovery authorities.

Threshold recovery (accept_root_recovery) binds the tenant, old and new roots, next trust epoch, and exact
first key list. The new root signs that first list; at least the configured threshold of independent recovery
keys signs the short-lived recovery statement. The first list starts at version 1 in the next trust epoch.
Epoch and list version are recorded in the anchored audit history, so recovery does not erase rollback
protection or require the compromised root to cooperate. Key identity and revocation history carry across
epochs.

This remains a local library primitive with test keys. The caller must supply recovery public keys and the
threshold from an independently protected trust configuration. Not built: a production recovery-key custody
service, distribution, a re-provisioning/restore workflow, a recovery drill, or a trusted time source (the
caller passes clock and monotonic). Not a boundary against code in the same process or an owner of both the
audit database and its external anchor.

Test keys only. Reached by the engine only through ``Simulation(signed_input=...)`` (a signed start).
No production recovery-key custody service, recovery distribution, restore workflow, recovery drill, or trusted
time source is built. This is not a boundary against code in the same process or an owner of both the audit
database and its external anchor."""
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
ROLLOVER_DOMAIN = b"agora.rootrollover.v1\x00"
REVOCATION_DOMAIN = b"agora.rootrevocation.v1\x00"
RECOVERY_DOMAIN = b"agora.rootrecovery.v1\x00"
MAX_RECOVERY_LIFETIME_SECONDS = 300
MAX_RECOVERY_KEYS = 16
MAX_TRUST_EPOCH = 999999
ROLLOVER_TYPE = "root_rollover"
REVOCATION_TYPE = "root_revocation"
_CHANGE_FIELDS = {"type", "v", "alg", "old_root_key_id", "new_root_key_id", "key_list_hash"}
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


def _pinned(root: RootKey, standby: RootKey | None) -> dict[str, RootKey]:
    if standby is None:
        return {root.key_id: root}
    if standby.key_id == root.key_id:
        raise _refuse("ROOT_PINS", "the standby root must differ from the current root")
    if not _usable_point(standby.public):
        raise _refuse("ROOT_PINS", "the standby root is not a usable Ed25519 point")
    return {root.key_id: root, standby.key_id: standby}


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
    trust_epoch: int = 0

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


def _event_id(version: int, trust_epoch: int = 0) -> str:
    # Preserve original epoch-zero IDs; later recovery epochs use a separate namespace.
    if trust_epoch == 0:
        return f"{EVENT_PREFIX}{version:012d}"
    return f"{EVENT_PREFIX}e{trust_epoch:06d}-v{version:012d}"


def _current_epoch(records: list[dict[str, Any]]) -> int:
    return max((record["epoch"] for record in records), default=0)


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
            epoch = event.get("trust_epoch", 0)
            if type(epoch) is not int or not 0 <= epoch <= MAX_TRUST_EPOCH:
                raise ValueError("bad trust epoch")
            if event["event_type"] != EVENT_TYPE or _event_id(version, epoch) != event_id:
                raise ValueError("not an acceptance record")
            keys = [(str(i), str(f), _STATUS_RANK[s]) for i, f, s in entries]
            records.append({"tenant": tenant, "root": root_key_id, "version": version, "epoch": epoch,
                            "hash": event["key_list_hash"], "keys": keys})
        except (ValueError, TypeError, KeyError) as exc:
            raise _refuse("KEY_LIST_HISTORY", "an acceptance record cannot be read") from exc
    return records


def _check_against_history(records, *, tenant: str, body: Mapping[str, Any], trust_epoch: int,
                           allow_epoch_advance: bool = False) -> None:
    if any(r["tenant"] != tenant for r in records):
        raise _refuse("TENANT_MISMATCH", "this store holds another tenant's key lists")
    current_epoch = _current_epoch(records)
    if allow_epoch_advance:
        if not records or trust_epoch != current_epoch + 1 or body["list_version"] != 1:
            raise _refuse("ROOT_RECOVERY_EPOCH", "recovery must advance exactly one epoch and start at list version 1")
    else:
        if trust_epoch != current_epoch:
            raise _refuse("KEY_LIST_EPOCH", "the list is not in the store's current trust epoch")
        if any(r["epoch"] == trust_epoch and r["version"] >= body["list_version"] for r in records):
            raise _refuse("KEY_LIST_ROLLBACK", "a list of this or a higher version was already accepted in this epoch")
    seen = [item for r in records for item in r["keys"]]
    for key in body["keys"]:
        public_print = fingerprint(bytes.fromhex(key["public"][8:]))
        for old_id, old_print, old_rank in seen:
            if (old_id == key["key_id"]) != (old_print == public_print):
                raise _refuse("KEY_REBOUND", key["key_id"])
            if old_id == key["key_id"] and _STATUS_RANK[key["status"]] < old_rank:
                raise _refuse("KEY_STATUS_REGRESSION", key["key_id"])


def _active_root_id(records, current_id: str) -> str:
    """The store's own history decides which root is active; configuration only decides an empty store."""
    return max(records, key=lambda r: (r["epoch"], r["version"]))["root"] if records else current_id


def _check_roots(records, *, old_id: str, new_id: str, body: Mapping[str, Any],
                 pinned: Mapping[str, RootKey]) -> None:
    """Runs inside the append transaction. ``old_id == new_id`` for an ordinary list."""
    if _active_root_id(records, next(iter(pinned))) != old_id:  # the first pin is the current root
        raise _refuse("KEY_LIST_ROOT_CHANGED", "the active root of this store is not the one this was checked for")
    used = {r["root"] for r in records}
    if new_id != old_id and new_id in used:
        raise _refuse("ROOT_RETIRED", "this store has already moved away from the new root")
    roots = used | set(pinned)
    if any(fingerprint(bytes.fromhex(key["public"][8:])) in roots for key in body["keys"]):
        raise _refuse("KEY_LIST_KEYS", "a root key must not be an online key")


def _read_active(writer, pinned: Mapping[str, RootKey]) -> RootKey:
    """A first look, to choose the verifying key. The append transaction checks the history again."""
    try:
        records = _history(writer.chain.db)
    except sqlite3.Error as exc:
        raise _refuse("KEY_LIST_ERROR", "the accepted history cannot be read") from exc
    active_id = _active_root_id(records, next(iter(pinned)))
    if active_id not in pinned:
        raise _refuse("KEY_LIST_ROOT_UNPINNED", "the active root of this store is not pinned")
    return pinned[active_id]


def _require_newest(db: sqlite3.Connection, tenant: str, list_hash: str) -> None:
    records = _history(db)
    if not records:
        raise _refuse("KEY_LIST_NOT_ACCEPTED", "this store has accepted no key list")
    newest = max(records, key=lambda r: (r["epoch"], r["version"]))
    if newest["tenant"] != tenant or newest["hash"] != list_hash:
        raise _refuse("KEY_LIST_SUPERSEDED", "not the newest key list accepted in this store")


def _writer(audit: AnchoredAuditChain) -> AnchoredAuditChain:
    try:
        return require_anchored(audit)
    except AnchorRequiredError as exc:
        raise _refuse("AUDIT_REQUIRED", "an anchored audit writer is required") from exc


def _record_acceptance(
    writer: AnchoredAuditChain, trusted: TrustedKeyList, *, tenant: str, old_id: str, new_id: str,
    pinned: Mapping[str, RootKey], clock: Callable[[], datetime], monotonic: Callable[[], float],
    change_hash: str | None = None, trust_epoch: int = 0, allow_epoch_advance: bool = False,
    recovery_hash: str | None = None, recovery_signers: list[str] | None = None,
    recovery_threshold: int | None = None,
) -> TrustedKeyList:
    """Append the one acceptance event, with every history check inside its transaction."""
    body = json.loads(trusted.signed_bytes)
    event_id = _event_id(body["list_version"], trust_epoch)
    entries = [[tenant, new_id, body["list_version"]]] + [
        [k["key_id"], fingerprint(bytes.fromhex(k["public"][8:])), k["status"]] for k in body["keys"]
    ]
    event = {
        "event_id": event_id, "event_type": EVENT_TYPE, "decision": "allow", "key_list_hash": trusted.list_hash,
        "resource_ids": [json.dumps(item, separators=(",", ":")) for item in entries],
        "trust_epoch": trust_epoch,
    }
    if recovery_hash is not None:
        event["root_recovery_hash"] = recovery_hash
        event["recovery_signers"] = sorted(recovery_signers or [])
        event["recovery_threshold"] = recovery_threshold
    if change_hash is not None:
        event["root_change_hash"] = change_hash

    def within_transaction(db: sqlite3.Connection) -> None:
        trusted.check_fresh(clock(), monotonic())
        records = _history(db, excluding=event_id)
        _check_against_history(records, tenant=tenant, body=body, trust_epoch=trust_epoch,
                               allow_epoch_advance=allow_epoch_advance)
        _check_roots(records, old_id=old_id, new_id=new_id, body=body, pinned=pinned)

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


def accept_key_list(
    envelope: Mapping[str, Any], *, tenant: str, root: RootKey, audit: AnchoredAuditChain,
    clock: Callable[[], datetime], monotonic: Callable[[], float], allow_test_keys: bool = False,
    standby: RootKey | None = None,
) -> TrustedKeyList:
    """Verify, check against the accepted history and record the acceptance, in one anchored transaction.

    The list must be signed by the store's active root; this function never changes it (see
    ``accept_root_change``). Presenting the newest accepted list again (same bytes) is allowed and appends
    nothing. ``root`` (the current root), ``standby`` and ``tenant`` come from the worker's own configuration.
    On any exception the caller must keep no new keys. ``AUDIT_ANCHOR_WRITE_FAILED`` means the acceptance is
    committed but unanchored: the chain refuses further appends until an operator reconciles it.
    """
    writer = _writer(audit)
    pinned = _pinned(root, standby)
    active = _read_active(writer, pinned)
    first, first_monotonic = clock(), monotonic()
    raw = verify_key_list(envelope, root=active, now=first, allow_test_keys=allow_test_keys)
    try:
        records = _history(writer.chain.db)
    except sqlite3.Error as exc:
        raise _refuse("KEY_LIST_ERROR", "the accepted history cannot be read") from exc
    epoch = _current_epoch(records)
    return _record_acceptance(
        writer, TrustedKeyList(raw, first, first_monotonic, epoch), tenant=tenant, old_id=active.key_id,
        new_id=active.key_id, pinned=pinned, clock=clock, monotonic=monotonic, trust_epoch=epoch,
    )


def _validate_change(body: Mapping[str, Any]) -> None:
    if set(body) != _CHANGE_FIELDS:
        raise _refuse("ROOT_CHANGE_FIELDS")
    if body["type"] not in (ROLLOVER_TYPE, REVOCATION_TYPE):
        raise _refuse("ROOT_CHANGE_TYPE")
    if type(body["v"]) is not int or body["v"] != VERSION:
        raise _refuse("BAD_VERSION")
    if body["alg"] != sr.ALGORITHM:
        raise _refuse("BAD_ALGORITHM")
    for name in ("old_root_key_id", "new_root_key_id", "key_list_hash"):
        if not isinstance(body[name], str) or not sr._HASH.match(body[name]):
            raise _refuse("ROOT_CHANGE_FIELDS", name)
    if body["old_root_key_id"] == body["new_root_key_id"]:
        raise _refuse("ROOT_CHANGE_ROOTS", "old and new root are the same")


def _change_domain(kind: str) -> bytes:
    return ROLLOVER_DOMAIN if kind == ROLLOVER_TYPE else REVOCATION_DOMAIN


def make_root_change(seed: bytes, body: Mapping[str, Any]) -> dict[str, str]:
    """Sign a root change statement with a TEST root seed. Returns the wire envelope {root_change, sig}."""
    _validate_change(body)
    raw = sr.canonical_bytes(body)
    return {"root_change": raw.decode("ascii"),
            "sig": sr.sign(seed, _change_domain(body["type"]) + raw).hex()}


def verify_root_change(envelope: Mapping[str, Any], *, old: RootKey, new: RootKey, list_bytes: bytes) -> bytes:
    """Signature, shape and binding only, for a change from ``old`` to ``new``. Returns the signed bytes.

    A planned rollover must be signed by ``old`` under its own domain tag. Standby-only revocation is disabled;
    emergency recovery uses the independent threshold path. This does NOT check store history; use
    ``accept_root_change`` before trusting the new root.
    """
    if not isinstance(envelope, Mapping) or set(envelope) != {"root_change", "sig"}:
        raise _refuse("MALFORMED", "envelope must be exactly {root_change, sig}")
    text, sig = envelope["root_change"], envelope["sig"]
    if not isinstance(text, str) or not isinstance(sig, str) or len(text) > MAX_BYTES:
        raise _refuse("MALFORMED", "root_change and sig must be strings of bounded size")
    try:
        raw, signature = text.encode("ascii"), bytes.fromhex(sig)
    except (UnicodeEncodeError, ValueError) as exc:
        raise _refuse("MALFORMED", "root_change must be ASCII and sig hex") from exc
    body = sr.parse_canonical(raw)
    _validate_change(body)
    if body["type"] != ROLLOVER_TYPE:
        raise _refuse("ROOT_CHANGE_TYPE", "standby-only revocation is disabled; use threshold root recovery")
    if not sr.verify_signature(old.public, ROLLOVER_DOMAIN + raw, signature):
        raise _refuse("BAD_SIGNATURE")
    if body["old_root_key_id"] != old.key_id or body["new_root_key_id"] != new.key_id:
        raise _refuse("ROOT_CHANGE_ROOTS", "the statement must move the active root to the other pinned root")
    if body["key_list_hash"] != "sha256:" + hashlib.sha256(DOMAIN + list_bytes).hexdigest():
        raise _refuse("ROOT_CHANGE_LIST", "the statement names a different key list")
    return raw


def accept_root_change(
    change_envelope: Mapping[str, Any], list_envelope: Mapping[str, Any], *, tenant: str, root: RootKey,
    standby: RootKey, audit: AnchoredAuditChain, clock: Callable[[], datetime],
    monotonic: Callable[[], float], allow_test_keys: bool = False,
) -> TrustedKeyList:
    """Move the store to the other pinned root, accepting that root's first list in the same audit event.

    The new list obeys every ordinary rule (higher version, no key status regression or re-binding). After
    this returns, the old root is refused by this store for good. A change this store has already applied is
    not applied again: load the new root's newest list with ``accept_key_list``.
    """
    writer = _writer(audit)
    if standby is None:
        raise _refuse("ROOT_PINS", "a root change needs a pinned standby root")
    pinned = _pinned(root, standby)
    old = _read_active(writer, pinned)
    new = next(item for key_id, item in pinned.items() if key_id != old.key_id)
    if old.test and not allow_test_keys:
        raise _refuse("TEST_KEY_REFUSED", "test root")
    first, first_monotonic = clock(), monotonic()
    list_bytes = verify_key_list(list_envelope, root=new, now=first, allow_test_keys=allow_test_keys)
    change = verify_root_change(change_envelope, old=old, new=new, list_bytes=list_bytes)
    kind = json.loads(change)["type"]
    try:
        records = _history(writer.chain.db)
    except sqlite3.Error as exc:
        raise _refuse("KEY_LIST_ERROR", "the accepted history cannot be read") from exc
    epoch = _current_epoch(records)
    return _record_acceptance(
        writer, TrustedKeyList(list_bytes, first, first_monotonic, epoch), tenant=tenant, old_id=old.key_id,
        new_id=new.key_id, pinned=pinned, clock=clock, monotonic=monotonic, trust_epoch=epoch,
        change_hash="sha256:" + hashlib.sha256(_change_domain(kind) + change).hexdigest(),
    )



def _validate_recovery(body: Mapping[str, Any]) -> None:
    fields = {"type", "v", "alg", "tenant", "old_root_key_id", "new_root_key_id",
              "trust_epoch", "key_list_hash", "issued_at", "expires_at"}
    if set(body) != fields:
        raise _refuse("ROOT_RECOVERY_FIELDS")
    if body["type"] != "root_recovery":
        raise _refuse("ROOT_RECOVERY_TYPE")
    if type(body["v"]) is not int or body["v"] != VERSION:
        raise _refuse("BAD_VERSION")
    if body["alg"] != sr.ALGORITHM:
        raise _refuse("BAD_ALGORITHM")
    if not isinstance(body["tenant"], str) or not sr._TOKEN.fullmatch(body["tenant"]):
        raise _refuse("ROOT_RECOVERY_FIELDS", "tenant")
    for name in ("old_root_key_id", "new_root_key_id", "key_list_hash"):
        if not isinstance(body[name], str) or not sr._HASH.fullmatch(body[name]):
            raise _refuse("ROOT_RECOVERY_FIELDS", name)
    if body["old_root_key_id"] == body["new_root_key_id"]:
        raise _refuse("ROOT_RECOVERY_ROOTS")
    if type(body["trust_epoch"]) is not int or not 1 <= body["trust_epoch"] <= MAX_TRUST_EPOCH:
        raise _refuse("ROOT_RECOVERY_EPOCH")
    issued, expires = sr._parse_time(body["issued_at"]), sr._parse_time(body["expires_at"])
    if not timedelta(0) < expires - issued <= timedelta(seconds=MAX_RECOVERY_LIFETIME_SECONDS):
        raise _refuse("ROOT_RECOVERY_LIFETIME")


def make_root_recovery(signers: Mapping[str, bytes], body: Mapping[str, Any]) -> dict[str, Any]:
    """Create a recovery envelope with TEST seeds only; production signing belongs in an independent service."""
    _validate_recovery(body)
    raw = sr.canonical_bytes(body)
    signatures: dict[str, str] = {}
    for key_id, seed in sorted(signers.items()):
        if fingerprint(sr.public_key(seed)) != key_id:
            raise _refuse("ROOT_RECOVERY_SIGNER", "seed does not match its declared recovery key id")
        signatures[key_id] = sr.sign(seed, RECOVERY_DOMAIN + raw).hex()
    return {"recovery": raw.decode("ascii"), "signatures": signatures}


def verify_root_recovery(
    envelope: Mapping[str, Any], *, old: RootKey, new: RootKey, tenant: str, trust_epoch: int,
    list_bytes: bytes, recovery_keys: Mapping[str, RootKey], threshold: int, now: datetime,
    allow_test_keys: bool = False,
) -> bytes:
    """Verify a threshold recovery certificate. Recovery keys must be independently pinned by the worker."""
    if not isinstance(envelope, Mapping) or set(envelope) != {"recovery", "signatures"}:
        raise _refuse("MALFORMED", "recovery envelope must contain exactly recovery and signatures")
    text, signatures = envelope["recovery"], envelope["signatures"]
    if not isinstance(text, str) or len(text) > MAX_BYTES or not isinstance(signatures, Mapping):
        raise _refuse("MALFORMED", "recovery statement or signatures have the wrong shape")
    if not isinstance(recovery_keys, Mapping) or not 2 <= len(recovery_keys) <= MAX_RECOVERY_KEYS:
        raise _refuse("ROOT_RECOVERY_KEYS", "between 2 and 16 recovery authorities are required")
    if type(threshold) is not int or threshold < 2 or threshold > len(recovery_keys):
        raise _refuse("ROOT_RECOVERY_THRESHOLD")
    if (old.test or new.test) and not allow_test_keys:
        raise _refuse("TEST_KEY_REFUSED", "test root")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise _refuse("BAD_CLOCK")
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise _refuse("MALFORMED", "recovery statement must be ASCII") from exc
    body = sr.parse_canonical(raw)
    _validate_recovery(body)
    if body["tenant"] != tenant:
        raise _refuse("TENANT_MISMATCH")
    if body["old_root_key_id"] != old.key_id or body["new_root_key_id"] != new.key_id:
        raise _refuse("ROOT_RECOVERY_ROOTS")
    if body["trust_epoch"] != trust_epoch:
        raise _refuse("ROOT_RECOVERY_EPOCH")
    expected_hash = "sha256:" + hashlib.sha256(DOMAIN + list_bytes).hexdigest()
    if body["key_list_hash"] != expected_hash:
        raise _refuse("ROOT_RECOVERY_LIST")
    issued, expires = sr._parse_time(body["issued_at"]), sr._parse_time(body["expires_at"])
    if issued > now + timedelta(seconds=sr.CLOCK_SKEW_SECONDS):
        raise _refuse("ROOT_RECOVERY_NOT_YET_VALID")
    if now >= expires or now - issued > timedelta(seconds=MAX_RECOVERY_LIFETIME_SECONDS):
        raise _refuse("ROOT_RECOVERY_STALE")

    trusted: dict[str, bytes] = {}
    seen_public: set[bytes] = set()
    for key_id, recovery_root in recovery_keys.items():
        if not isinstance(key_id, str) or not isinstance(recovery_root, RootKey) or recovery_root.key_id != key_id:
            raise _refuse("ROOT_RECOVERY_KEYS", "recovery keys must be pinned RootKey values")
        public = recovery_root.public
        if recovery_root.test and not allow_test_keys:
            raise _refuse("TEST_KEY_REFUSED", "test recovery authority")
        if not _usable_point(public) or public in seen_public or key_id in (old.key_id, new.key_id):
            raise _refuse("ROOT_RECOVERY_KEYS", "recovery keys must be distinct from roots and one another")
        trusted[key_id] = public
        seen_public.add(public)
    if len(signatures) < threshold or any(key_id not in trusted for key_id in signatures):
        raise _refuse("ROOT_RECOVERY_THRESHOLD", "not enough known recovery authorities")
    signed_message = RECOVERY_DOMAIN + raw
    valid = 0
    for key_id, signature_hex in signatures.items():
        if not isinstance(signature_hex, str):
            raise _refuse("ROOT_RECOVERY_SIGNATURE")
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise _refuse("ROOT_RECOVERY_SIGNATURE") from exc
        if not sr.verify_signature(trusted[key_id], signed_message, signature):
            raise _refuse("ROOT_RECOVERY_SIGNATURE", key_id)
        valid += 1
    if valid < threshold:
        raise _refuse("ROOT_RECOVERY_THRESHOLD")
    return raw


def accept_root_recovery(
    recovery_envelope: Mapping[str, Any], list_envelope: Mapping[str, Any], *, tenant: str,
    root: RootKey, new_root: RootKey, recovery_keys: Mapping[str, RootKey], threshold: int,
    audit: AnchoredAuditChain, clock: Callable[[], datetime], monotonic: Callable[[], float],
    allow_test_keys: bool = False,
) -> TrustedKeyList:
    """Recover a store from a compromised/lost active root using an independent threshold authority.

    The replacement root signs the first list in a new trust epoch. Its list version restarts at 1;
    the anchored audit history remains monotonic through the separate trust epoch. The compromised root
    need not sign or cooperate. This is a local verifier/store primitive, not a recovery distribution service.
    """
    writer = _writer(audit)
    if root.key_id == new_root.key_id:
        raise _refuse("ROOT_RECOVERY_ROOTS")
    old = _read_active(writer, {root.key_id: root, new_root.key_id: new_root})
    if old.test and not allow_test_keys:
        raise _refuse("TEST_KEY_REFUSED", "test root")
    first, first_monotonic = clock(), monotonic()
    list_bytes = verify_key_list(list_envelope, root=new_root, now=first, allow_test_keys=allow_test_keys)
    if not isinstance(recovery_keys, Mapping):
        raise _refuse("ROOT_RECOVERY_KEYS", "recovery authorities must be supplied as a pinned mapping")
    try:
        records = _history(writer.chain.db)
    except sqlite3.Error as exc:
        raise _refuse("KEY_LIST_ERROR", "the accepted history cannot be read") from exc
    if not records:
        raise _refuse("ROOT_RECOVERY_NO_HISTORY", "recovery is not bootstrap")
    historical_authorities = {record["root"] for record in records}
    historical_authorities.update(public_fingerprint
                                  for record in records for _, public_fingerprint, _ in record["keys"])
    if new_root.key_id in historical_authorities:
        raise _refuse("ROOT_RECOVERY_ROOTS", "replacement root was previously used as a root or online key")
    if any(key_id in historical_authorities for key_id in recovery_keys):
        raise _refuse("ROOT_RECOVERY_KEYS", "a recovery authority was previously used as a root or online key")
    epoch = _current_epoch(records) + 1
    change = verify_root_recovery(
        recovery_envelope, old=old, new=new_root, tenant=tenant, trust_epoch=epoch,
        list_bytes=list_bytes, recovery_keys=recovery_keys, threshold=threshold, now=first,
        allow_test_keys=allow_test_keys,
    )
    return _record_acceptance(
        writer, TrustedKeyList(list_bytes, first, first_monotonic, epoch), tenant=tenant,
        old_id=old.key_id, new_id=new_root.key_id,
        pinned={old.key_id: old, new_root.key_id: new_root},
        clock=clock, monotonic=monotonic, trust_epoch=epoch, allow_epoch_advance=True,
        recovery_hash="sha256:" + hashlib.sha256(RECOVERY_DOMAIN + change).hexdigest(),
        recovery_signers=sorted(recovery_envelope["signatures"]), recovery_threshold=threshold,
    )


def current_keys(
    key_list: TrustedKeyList, *, tenant: str, audit: AnchoredAuditChain,
    clock: Callable[[], datetime], monotonic: Callable[[], float],
) -> dict[str, sr.KeyEntry]:
    """The keys of the newest accepted, fresh list in this store, for a check that consumes nothing.

    ``admit_receipt_with_key_list`` makes the same two checks inside its transaction; this reads them
    once, so a statement checked here can be checked again until it expires.
    """
    keys = key_list.keys(clock(), monotonic())
    writer = _writer(audit)
    try:
        with writer.anchors.lock():
            _require_newest(writer.chain.db, tenant, key_list.list_hash)
    except sqlite3.Error as exc:
        raise _refuse("KEY_LIST_ERROR", "the accepted history cannot be read") from exc
    return keys


def require_current(db: sqlite3.Connection, tenant: str, key_list: TrustedKeyList, now: datetime,
                    monotonic_now: float) -> None:
    """Refuse unless ``key_list`` is the newest list accepted in the store behind ``db`` and still fresh.

    For use inside the transaction that acts on a signature checked with that list.
    """
    _require_newest(db, tenant, key_list.list_hash)
    key_list.check_fresh(now, monotonic_now)


def admit_receipt_with_key_list(
    envelope: Mapping[str, Any], *, key_list: TrustedKeyList, tenant: str, audit: AnchoredAuditChain,
    clock: Callable[[], datetime], monotonic: Callable[[], float], expected: Mapping[str, str],
    allow_test_keys: bool = False,
) -> ledger.AdmittedReceipt:
    """``admit_receipt`` with keys taken only from the newest accepted, fresh key list of the same store."""
    keys = key_list.keys(clock(), monotonic())

    def still_current(db: sqlite3.Connection, now: datetime) -> None:
        require_current(db, tenant, key_list, now, monotonic())

    return ledger.admit_receipt(
        envelope, tenant=tenant, audit=audit, keys=keys, clock=clock, expected=expected,
        allow_test_keys=allow_test_keys, guard=still_current,
    )


__all__ = ["RootKey", "TrustedKeyList", "accept_key_list", "accept_root_change", "admit_receipt_with_key_list", "current_keys",
           "fingerprint", "make_key_list", "make_root_change", "make_root_recovery", "verify_key_list",
           "verify_root_change", "verify_root_recovery", "accept_root_recovery"]

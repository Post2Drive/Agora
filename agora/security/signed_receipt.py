"""Signed authorization receipts, phase 1: format, local verifier, test keys only.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3, 3A and 3B.

This module is NOT wired into the engine and holds NO production key. It defines the receipt format and a
verifier that refuses forged, tampered, expired, replayed, wrong-scope and test-keyed receipts. Production
signing is done by a KMS-held key in a service we operate (later phase); the pure-Python Ed25519 here exists so
the verifier has no new dependency and so test keys can sign vectors. It is not constant-time: never use
`sign` with a secret that matters.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

DOMAIN = b"agora.receipt.v1\x00"
VERSION = 1
ALGORITHM = "ed25519"
MAX_LIFETIME_SECONDS = 300
CLOCK_SKEW_SECONDS = 30

FIELDS = (
    "v", "alg", "tenant", "subject", "project", "import_id", "binding_id", "manifest_hash",
    "scenario_hash", "purpose", "release_id", "key_id", "issued_at", "expires_at", "nonce",
)
_TOKEN = re.compile(r"[A-Za-z0-9._:\-]{1,128}\Z")
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_TOKEN_FIELDS = ("tenant", "subject", "project", "import_id", "binding_id", "purpose", "release_id", "key_id")
_HASH_FIELDS = ("manifest_hash", "scenario_hash")


class ReceiptError(Exception):
    """Refusal. `code` is stable and machine-readable; nothing is written or authorised on refusal."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# --------------------------------------------------------------------------- Ed25519 (RFC 8032, pure Python)
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _recover_x(y: int, sign: int) -> int | None:
    xx = (y * y - 1) * _inv(_D * y * y + 1) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = x * _I % _P
    if (x * x - xx) % _P:
        return None
    if x == 0 and sign:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_BY = 4 * _inv(5) % _P
_BX = _recover_x(_BY, 0)
_B = (_BX, _BY, 1, _BX * _BY % _P)


def _add(p1, p2):
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    d = z1 * 2 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, point):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, point)
        point = _add(point, point)
        s >>= 1
    return q


def _compress(point) -> bytes:
    zi = _inv(point[2])
    x, y = point[0] * zi % _P, point[1] * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decompress(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h512(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _expand(seed: bytes):
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _compress(_mul(a, _B))


def sign(seed: bytes, message: bytes) -> bytes:
    """Ed25519 signature. Test keys only (not constant-time)."""
    a, prefix = _expand(seed)
    pub = _compress(_mul(a, _B))
    r = _h512(prefix + message) % _Q
    r_enc = _compress(_mul(r, _B))
    s = (r + _h512(r_enc + pub + message) * a) % _Q
    return r_enc + s.to_bytes(32, "little")


def verify_signature(pub: bytes, message: bytes, signature: bytes) -> bool:
    if len(pub) != 32 or len(signature) != 64:
        return False
    a_pt = _decompress(pub)
    r_pt = _decompress(signature[:32])
    if a_pt is None or r_pt is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _h512(signature[:32] + pub + message) % _Q
    return _compress(_mul(s, _B)) == _compress(_add(r_pt, _mul(h, a_pt)))


# --------------------------------------------------------------------------- canonical bytes
def _no_floats(value: Any) -> None:
    if isinstance(value, float):
        raise ReceiptError("NON_CANONICAL", "floats are not allowed")
    if isinstance(value, Mapping):
        for v in value.values():
            _no_floats(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _no_floats(v)


def canonical_bytes(receipt: Mapping[str, Any]) -> bytes:
    """The exact bytes that are signed (after the domain tag)."""
    _no_floats(receipt)
    return json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def signing_input(receipt: Mapping[str, Any]) -> bytes:
    return DOMAIN + canonical_bytes(receipt)


def _pairs_hook(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ReceiptError("NON_CANONICAL", "duplicate key")
    return dict(pairs)


def parse_canonical(data: bytes) -> dict[str, Any]:
    """Parse receipt JSON and refuse anything that is not already in canonical form."""
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs_hook,
                         parse_float=_reject_float, parse_constant=_reject_float)
    except ReceiptError:
        raise
    except Exception as exc:
        raise ReceiptError("MALFORMED", "not valid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise ReceiptError("MALFORMED", "receipt must be an object")
    if canonical_bytes(obj) != data:
        raise ReceiptError("NON_CANONICAL", "bytes are not in canonical form")
    return obj


def _reject_float(_: str):
    raise ReceiptError("NON_CANONICAL", "floats are not allowed")


# --------------------------------------------------------------------------- receipt checks
def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not _TIME.match(value):
        raise ReceiptError("BAD_TIME", "timestamps are UTC RFC 3339 with a Z suffix")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def validate_shape(receipt: Mapping[str, Any]) -> None:
    if set(receipt) != set(FIELDS):
        extra, missing = sorted(set(receipt) - set(FIELDS)), sorted(set(FIELDS) - set(receipt))
        raise ReceiptError("BAD_FIELDS", f"unknown={extra} missing={missing}")
    if receipt["v"] != VERSION or isinstance(receipt["v"], bool):
        raise ReceiptError("BAD_VERSION")
    if receipt["alg"] != ALGORITHM:
        raise ReceiptError("BAD_ALGORITHM")
    for name in _TOKEN_FIELDS:
        value = receipt[name]
        if not isinstance(value, str) or not _TOKEN.match(value):
            raise ReceiptError("BAD_FIELD", name)
    for name in _HASH_FIELDS:
        value = receipt[name]
        if not isinstance(value, str) or not _HASH.match(value):
            raise ReceiptError("BAD_FIELD", name)
    if not isinstance(receipt["nonce"], str) or not _NONCE.match(receipt["nonce"]):
        raise ReceiptError("BAD_FIELD", "nonce")
    issued, expires = _parse_time(receipt["issued_at"]), _parse_time(receipt["expires_at"])
    if expires <= issued or (expires - issued).total_seconds() > MAX_LIFETIME_SECONDS:
        raise ReceiptError("BAD_LIFETIME")


class KeyEntry:
    """One entry of a (test) key list: a public key with a validity window and status."""

    def __init__(self, key_id: str, public: bytes, not_before: str, not_after: str,
                 status: str = "active", test: bool = False) -> None:
        self.key_id, self.public, self.status, self.test = key_id, bytes(public), status, bool(test)
        self.not_before, self.not_after = _parse_time(not_before), _parse_time(not_after)


class NonceStore:
    """In-memory, thread-safe nonce consumption. A real deployment consumes the nonce in the same transaction
    as the audited action in the tenant's store (design 3B item 3); this stub only defines the contract."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def consume(self, key_id: str, nonce: str) -> bool:
        with self._lock:
            if (key_id, nonce) in self._seen:
                return False
            self._seen.add((key_id, nonce))
            return True


def make_receipt(seed: bytes, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Sign a receipt dict (test keys only). Returns the wire envelope {receipt_b64-free: canonical text, sig}."""
    validate_shape(receipt)
    body = canonical_bytes(receipt)
    return {"receipt": body.decode("ascii"), "sig": sign(seed, DOMAIN + body).hex()}


def verify_receipt(
    envelope: Mapping[str, Any], *, keys: Mapping[str, KeyEntry], now: datetime, expected: Mapping[str, str],
    nonces: NonceStore, allow_test_keys: bool = False,
) -> dict[str, Any]:
    """Return the verified receipt dict or raise ReceiptError. Consumes the nonce only after every check passes.

    `expected` is the exact scope the caller is about to act on (tenant, subject, project, import_id, binding_id,
    manifest_hash, scenario_hash, purpose, ...); every key given must equal the receipt's value. It must not be empty.
    """
    if not expected:
        raise ReceiptError("NO_SCOPE", "caller must state the scope being authorised")
    if not isinstance(envelope, Mapping) or set(envelope) != {"receipt", "sig"}:
        raise ReceiptError("MALFORMED", "envelope must be exactly {receipt, sig}")
    if not isinstance(envelope["receipt"], str) or not isinstance(envelope["sig"], str):
        raise ReceiptError("MALFORMED", "receipt and sig must be strings")
    try:
        body = envelope["receipt"].encode("ascii")
        signature = bytes.fromhex(envelope["sig"])
    except (UnicodeEncodeError, ValueError) as exc:
        raise ReceiptError("MALFORMED", "receipt must be ASCII and sig hex") from exc
    receipt = parse_canonical(body)
    validate_shape(receipt)
    entry = keys.get(receipt["key_id"])
    if entry is None:
        raise ReceiptError("UNKNOWN_KEY")
    if entry.test and not allow_test_keys:
        raise ReceiptError("TEST_KEY_REFUSED")
    if entry.status != "active":
        raise ReceiptError("KEY_NOT_ACTIVE", entry.status)
    if not verify_signature(entry.public, DOMAIN + body, signature):
        raise ReceiptError("BAD_SIGNATURE")
    if now.tzinfo is None:
        raise ReceiptError("BAD_CLOCK", "now must be timezone-aware")
    issued, expires = _parse_time(receipt["issued_at"]), _parse_time(receipt["expires_at"])
    skew = timedelta(seconds=CLOCK_SKEW_SECONDS)
    if not (entry.not_before <= issued <= entry.not_after):
        raise ReceiptError("KEY_OUT_OF_WINDOW")
    if issued > now + skew:
        raise ReceiptError("NOT_YET_VALID")
    if now >= expires:
        raise ReceiptError("EXPIRED")
    for name, want in expected.items():
        if name not in FIELDS or receipt.get(name) != want:
            raise ReceiptError("SCOPE_MISMATCH", name)
    if not nonces.consume(receipt["key_id"], receipt["nonce"]):
        raise ReceiptError("REPLAY")
    return receipt

"""The one governed entry point for receipt admission: trust comes from worker configuration (test keys only).

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3A and 3B (items 1, 3, 4 and 6).

A worker opens one ``ReceiptGate`` from its own configuration file. The tenant, release id, the two pinned root
keys (current and standby), key mode and audit store paths come from that file and from nowhere else: a request
cannot name a tenant, a release, a key, a clock or a test-key switch. Admission calls only ``key_list.admit_receipt_with_key_list``,
so receipt keys come only from the newest accepted, fresh key list in the same store.

The request fields are the scope being authorised. The worker MUST derive them from the action it is about to
run (the authenticated subject and the hashes of the inputs it actually loaded), not copy them from the receipt
or take the requester's word; otherwise the scope check compares a claim with itself.

One gate per thread (its SQLite connection is not shared across threads). NOT wired into the engine. The clock
is whatever the worker process passes in; there is no trusted time source. Not a boundary against code in the
same process, or against anyone who can edit the configuration file or both the audit database and the anchor.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from agora.audit_anchor import AnchoredAuditChain, open_anchored_audit
from agora.pathsafe import read_stable_bytes
from agora.security import key_list as kl
from agora.security import receipt_ledger as ledger
from agora.security import signed_receipt as sr

CONFIG_TYPE = "receipt_gate_config"
CONFIG_VERSION = 2
MAX_CONFIG_BYTES = 16 * 1024
KEY_MODES = ("test", "production")
_CONFIG_FIELDS = {"type", "v", "tenant", "release_id", "key_mode", "root_public", "standby_root_public",
                  "audit_db", "audit_anchor", "chain_id"}
WORKER_FIELDS = ("tenant", "release_id")
REQUEST_FIELDS = tuple(name for name in sr.SCOPE_FIELDS if name not in WORKER_FIELDS)


@dataclass(frozen=True)
class GateConfig:
    tenant: str
    release_id: str
    key_mode: str
    root_public: bytes
    standby_root_public: bytes
    audit_db: Path
    audit_anchor: Path
    chain_id: str


def _bad_config(detail: str) -> sr.ReceiptError:
    return sr.ReceiptError("GATE_CONFIG", detail)


def _unique(pairs):
    names = [name for name, _ in pairs]
    if len(set(names)) != len(names):
        raise _bad_config("duplicate field")
    return dict(pairs)


def _root_public(data: Mapping[str, Any], name: str) -> bytes:
    text = data[name]
    if not isinstance(text, str) or len(text) != 72 or not text.startswith("ed25519:") \
            or any(c not in "0123456789abcdef" for c in text[8:]):
        raise _bad_config(name)
    public = bytes.fromhex(text[8:])
    if not kl._usable_point(public):
        raise _bad_config(f"{name} is not a usable Ed25519 point")
    return public


def load_gate_config(path: str | Path) -> GateConfig:
    """Read the worker's configuration. Anything missing, unknown or malformed refuses; nothing has a default."""
    try:
        raw = read_stable_bytes(path)
        if len(raw) > MAX_CONFIG_BYTES:
            raise _bad_config("file is too large")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except sr.ReceiptError:
        raise
    except Exception as exc:
        raise _bad_config("the configuration file cannot be read as a safe UTF-8 JSON file") from exc
    if not isinstance(data, dict) or set(data) != _CONFIG_FIELDS:
        raise _bad_config("fields must be exactly " + ",".join(sorted(_CONFIG_FIELDS)))
    if data["type"] != CONFIG_TYPE or type(data["v"]) is not int or data["v"] != CONFIG_VERSION:
        raise _bad_config("type or version")
    for name in WORKER_FIELDS:
        if not isinstance(data[name], str) or not sr._TOKEN.match(data[name]):
            raise _bad_config(name)
    if data["key_mode"] not in KEY_MODES:
        raise _bad_config("key_mode must be test or production")
    root_public = _root_public(data, "root_public")
    standby_public = _root_public(data, "standby_root_public")
    if standby_public == root_public:
        raise _bad_config("standby_root_public must differ from root_public")
    paths = []
    for name in ("audit_db", "audit_anchor"):
        value = data[name]
        # A relative path would let the working directory choose the store, and with it the rollback history.
        if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
            raise _bad_config(f"{name} must be an absolute path")
        paths.append(Path(value))
    if not isinstance(data["chain_id"], str) or not sr._TOKEN.match(data["chain_id"]):
        raise _bad_config("chain_id")
    return GateConfig(data["tenant"], data["release_id"], data["key_mode"], root_public, standby_public,
                      paths[0], paths[1], data["chain_id"])


class ReceiptGate:
    """Holds the worker's trust settings and the key list last accepted through this object."""

    def __init__(self, config: GateConfig, audit: AnchoredAuditChain, *,
                 clock: Callable[[], datetime], monotonic: Callable[[], float]) -> None:
        self._config, self._audit = config, audit
        self._clock, self._monotonic = clock, monotonic
        test = config.key_mode == "test"
        self._root = kl.RootKey(config.root_public, test=test)
        self._standby = kl.RootKey(config.standby_root_public, test=test)
        self._allow_test_keys = test
        self._key_list: kl.TrustedKeyList | None = None

    @property
    def key_list_version(self) -> int | None:
        return None if self._key_list is None else self._key_list.list_version

    def refresh_key_list(self, envelope: Mapping[str, Any]) -> int:
        """Accept a signed key list. On refusal the previously loaded list, if any, is kept: it is still
        re-checked as newest and fresh at every admission, so a bad envelope cannot extend or revive it."""
        accepted = kl.accept_key_list(
            envelope, tenant=self._config.tenant, root=self._root, standby=self._standby, audit=self._audit,
            clock=self._clock, monotonic=self._monotonic, allow_test_keys=self._allow_test_keys,
        )
        self._key_list = accepted
        return accepted.list_version

    def rotate_root(self, change_envelope: Mapping[str, Any], list_envelope: Mapping[str, Any]) -> int:
        """Apply a signed root rollover or revocation together with the new root's first key list (see
        ``key_list.accept_root_change``). On refusal the previously loaded list is kept, as above."""
        accepted = kl.accept_root_change(
            change_envelope, list_envelope, tenant=self._config.tenant, root=self._root, standby=self._standby,
            audit=self._audit, clock=self._clock, monotonic=self._monotonic,
            allow_test_keys=self._allow_test_keys,
        )
        self._key_list = accepted
        return accepted.list_version

    def admit(self, envelope: Mapping[str, Any], *, request: Mapping[str, str]) -> ledger.AdmittedReceipt:
        """Admit one receipt for one request, or raise ``sr.ReceiptError``. Do not act on any exception."""
        if not isinstance(request, Mapping) or set(request) != set(REQUEST_FIELDS):
            raise sr.ReceiptError("BAD_REQUEST", "request fields must be exactly " + ",".join(REQUEST_FIELDS))
        scope = dict(request)  # one read: the caller's mapping cannot change what is checked
        if set(scope) != set(REQUEST_FIELDS) or not all(isinstance(v, str) for v in scope.values()):
            raise sr.ReceiptError("BAD_REQUEST", "request values must be strings")
        scope.update(tenant=self._config.tenant, release_id=self._config.release_id)
        if self._key_list is None:
            raise sr.ReceiptError("KEY_LIST_NOT_LOADED", "load a signed key list before admitting")
        return kl.admit_receipt_with_key_list(
            envelope, key_list=self._key_list, tenant=self._config.tenant, audit=self._audit, clock=self._clock,
            monotonic=self._monotonic, expected=scope, allow_test_keys=self._allow_test_keys,
        )


@contextmanager
def open_receipt_gate(config_path: str | Path, *, clock: Callable[[], datetime],
                      monotonic: Callable[[], float]) -> Iterator[ReceiptGate]:
    """Open the gate over the configured, already bootstrapped audit store. Never creates or bootstraps one."""
    config = load_gate_config(config_path)
    # AuditChainStore creates a missing database; a new empty store would have no key-list or nonce history.
    if not config.audit_db.is_file():
        raise sr.ReceiptError("AUDIT_UNANCHORED", "the configured audit database does not exist")
    manager = open_anchored_audit(config.audit_db, config.audit_anchor, config.chain_id)
    try:
        audit = manager.__enter__()
    except Exception as exc:
        raise sr.ReceiptError("AUDIT_UNANCHORED", "the audit store cannot be opened cleanly anchored") from exc
    try:
        yield ReceiptGate(config, audit, clock=clock, monotonic=monotonic)
    finally:
        manager.__exit__(None, None, None)


__all__ = ["GateConfig", "REQUEST_FIELDS", "ReceiptGate", "load_gate_config", "open_receipt_gate"]

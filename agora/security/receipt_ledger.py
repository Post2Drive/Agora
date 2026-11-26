"""Durable single use of signed receipts: nonce consumption committed together with its audit event.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md section 3A (nonce replay and atomicity) and 3B item 3.

``admit_receipt`` verifies a receipt and then, in ONE SQLite transaction in the tenant's audit store, appends
a ``receipt_consumed`` audit event and records ``(key_id, nonce)``. The write goes through the anchored audit
writer. A receipt counts as admitted only when this function returns.

Two guards refuse a replay: the audit event id is derived from ``(key_id, nonce)`` and the chain refuses a
repeated event id, and the nonce table must match the chain's consumption events one for one, so a removed or
added nonce row stops all further admissions.

NOT wired into the engine and NOT a boundary against code in the same process or an owner of the database and
anchor files: such a party can construct an ``AdmittedReceipt`` or rewrite both files. The anchor is a local
sidecar (see agora.audit_anchor). The action a receipt authorises happens outside this transaction; this
module does not make that action atomic with the consumption. Nonce records are never purged in this version.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable, Mapping

from agora.audit_anchor import AnchoredAuditChain, AnchorRequiredError, AnchorWriteError, require_anchored
from agora.audit_chain import AuditReplayError
from agora.security import signed_receipt as sr

EVENT_PREFIX = "receipt-consume-"
EVENT_TYPE = "receipt_consumed"
TABLE = "receipt_nonces"

_SCHEMA = {
    TABLE: (
        "CREATE TABLE receipt_nonces (key_id TEXT NOT NULL, nonce TEXT NOT NULL, tenant TEXT NOT NULL, "
        "receipt_hash TEXT NOT NULL, expires_at TEXT NOT NULL, audit_event_id TEXT NOT NULL UNIQUE, "
        "PRIMARY KEY (key_id, nonce))"
    ),
    "protect_receipt_nonce_update": (
        "CREATE TRIGGER protect_receipt_nonce_update BEFORE UPDATE ON receipt_nonces "
        "BEGIN SELECT RAISE(ABORT, 'receipt nonces are append-only'); END"
    ),
    "protect_receipt_nonce_delete": (
        "CREATE TRIGGER protect_receipt_nonce_delete BEFORE DELETE ON receipt_nonces "
        "BEGIN SELECT RAISE(ABORT, 'receipt nonces are append-only'); END"
    ),
}


@dataclass(frozen=True)
class AdmittedReceipt:
    """What was committed. A plain value object: holding one is not proof of authority by itself."""

    receipt: Mapping[str, Any]
    receipt_hash: str
    audit_event_id: str


class _CheckOnly:
    """Lets verify_receipt run every check; the durable consumption happens in the ledger transaction."""

    def consume(self, key_id: str, nonce: str) -> bool:
        return True


def consumption_event_id(key_id: str, nonce: str) -> str:
    material = json.dumps([key_id, nonce], separators=(",", ":")).encode("ascii")
    return EVENT_PREFIX + hashlib.sha256(material).hexdigest()


def _ledger_objects(db: sqlite3.Connection) -> dict[str, str]:
    rows = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE (lower(tbl_name)=? OR lower(name)=?) AND sql IS NOT NULL",
        (TABLE, TABLE),
    ).fetchall()
    return {name: sql for name, sql in rows}


def _consumption_events(db: sqlite3.Connection) -> set[str]:
    rows = db.execute(
        "SELECT event_id FROM audit_events WHERE substr(event_id, 1, ?)=?", (len(EVENT_PREFIX), EVENT_PREFIX),
    ).fetchall()
    return {row[0] for row in rows}


def _record(db: sqlite3.Connection, row: tuple[str, str, str, str, str, str]) -> None:
    """Runs inside the audit append transaction, after the event row is inserted."""
    key_id, nonce, tenant, receipt_hash, expires_at, event_id = row
    events = _consumption_events(db)
    if event_id not in events:
        raise sr.ReceiptError("LEDGER_INCONSISTENT", "the audit event was not stored")
    earlier = events - {event_id}
    objects = _ledger_objects(db)
    if not objects:  # first use; if consumptions already exist, the row comparison below refuses and rolls this back
        for statement in _SCHEMA.values():
            db.execute(statement)
        objects = _ledger_objects(db)
    if objects != _SCHEMA:
        raise sr.ReceiptError("LEDGER_SCHEMA", "nonce table or its triggers are not as this version creates them")
    if {r[0] for r in db.execute("SELECT audit_event_id FROM receipt_nonces")} != earlier:
        raise sr.ReceiptError("LEDGER_INCONSISTENT", "nonce rows do not match the audit chain")
    if db.execute("SELECT 1 FROM receipt_nonces WHERE tenant<>? LIMIT 1", (tenant,)).fetchone():
        raise sr.ReceiptError("TENANT_MISMATCH", "this store holds another tenant's receipts")
    db.execute(
        "INSERT INTO receipt_nonces(key_id,nonce,tenant,receipt_hash,expires_at,audit_event_id) "
        "VALUES (?,?,?,?,?,?)", row,
    )


def admit_receipt(
    envelope: Mapping[str, Any], *, tenant: str, audit: AnchoredAuditChain,
    keys: Mapping[str, sr.KeyEntry], clock: Callable[[], datetime], expected: Mapping[str, str],
    allow_test_keys: bool = False,
) -> AdmittedReceipt:
    """Verify, then durably consume. Raises ``sr.ReceiptError``; the caller must not act on any exception.

    ``tenant`` is the tenant this store belongs to, taken from the worker's own configuration, never from the
    request. ``clock`` must read the trusted time source; it is read again after the write lock is held, so a
    receipt that expires while waiting is refused. ``AUDIT_ANCHOR_WRITE_FAILED`` means the nonce IS consumed
    but the anchor was not written: the receipt is spent, the action is refused, and the chain refuses further
    appends until an operator reconciles it.
    """
    try:
        writer = require_anchored(audit)
    except AnchorRequiredError as exc:
        raise sr.ReceiptError("AUDIT_REQUIRED", "an anchored audit writer is required") from exc
    first = clock()
    receipt = sr.verify_receipt(
        envelope, keys=keys, now=first, expected=expected, nonces=_CheckOnly(),  # type: ignore[arg-type]
        allow_test_keys=allow_test_keys,
    )
    if receipt["tenant"] != tenant:
        raise sr.ReceiptError("TENANT_MISMATCH", "receipt is for another tenant")
    receipt_hash = "sha256:" + hashlib.sha256(sr.signing_input(receipt)).hexdigest()
    event_id = consumption_event_id(receipt["key_id"], receipt["nonce"])
    expires = sr._parse_time(receipt["expires_at"])
    row = (receipt["key_id"], receipt["nonce"], tenant, receipt_hash, receipt["expires_at"], event_id)

    def within_transaction(db: sqlite3.Connection) -> None:
        second = clock()
        if second.tzinfo is None or second < first:
            raise sr.ReceiptError("BAD_CLOCK", "trusted time is naive or moved backwards")
        if second >= expires:
            raise sr.ReceiptError("EXPIRED")
        _record(db, row)

    event = {
        "event_id": event_id, "event_type": EVENT_TYPE, "subject_id": receipt["subject"],
        "operation": receipt["purpose"], "decision": "allow", "receipt_hash": receipt_hash,
        "manifest_hash": receipt["manifest_hash"], "scenario_hash": receipt["scenario_hash"],
        "resource_ids": [f"{name}:{receipt[name]}" for name in
                         ("tenant", "project", "import_id", "binding_id", "release_id", "key_id")],
    }
    try:
        writer.append(event, in_transaction=within_transaction)
    except sr.ReceiptError:
        raise
    except AuditReplayError as exc:
        raise sr.ReceiptError("REPLAY") from exc
    except AnchorRequiredError as exc:
        raise sr.ReceiptError("AUDIT_UNANCHORED", str(exc)) from exc
    except AnchorWriteError as exc:
        raise sr.ReceiptError("AUDIT_ANCHOR_WRITE_FAILED", "receipt is spent; do not act") from exc
    except Exception as exc:
        raise sr.ReceiptError("LEDGER_ERROR", "the consumption could not be committed") from exc
    return AdmittedReceipt(MappingProxyType(dict(receipt)), receipt_hash, event_id)


__all__ = ["AdmittedReceipt", "admit_receipt", "consumption_event_id"]

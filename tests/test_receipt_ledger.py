"""Durable single use of signed receipts (test keys only): atomic with the anchored audit event."""
import json
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agora.audit_anchor import AnchoredAuditChain, AnchorStore, bootstrap_anchor, open_anchored_audit
from agora.audit_chain import AuditChainStore
from agora.security import receipt_ledger as ledger
from agora.security import signed_receipt as sr

VEC = json.loads((Path(__file__).parent / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))
TK = VEC["test_key"]
SEED = bytes.fromhex(TK["seed_hex"])
BASE = VEC["base_receipt"]
KEYS = {TK["key_id"]: sr.KeyEntry(TK["key_id"], bytes.fromhex(TK["public_hex"]), TK["not_before"],
                                  TK["not_after"], status="active", test=True)}
NOW = datetime(2026, 11, 24, 12, 1, tzinfo=timezone.utc)


def paths(tmp_path):
    return tmp_path / "audit.sqlite3", tmp_path / "anchors" / "a.jsonl"


@pytest.fixture
def store(tmp_path):
    db_path, anchor_path = paths(tmp_path)
    chain = AuditChainStore(db_path)
    bootstrap_anchor(chain, AnchorStore(anchor_path, "tenant-a-chain"), performed_by="maint-1")
    chain.close()
    with open_anchored_audit(db_path, anchor_path, "tenant-a-chain") as writer:
        yield writer


def envelope(n=0, **changes):
    receipt = {**BASE, "nonce": f"{n:032x}", **changes}
    return sr.make_receipt(SEED, receipt), {name: receipt[name] for name in sr.SCOPE_FIELDS}


def admit(writer, n=0, *, tenant=BASE["tenant"], clock=lambda: NOW, expected=None, allow=True, **changes):
    env, scope = envelope(n, **changes)
    return ledger.admit_receipt(env, tenant=tenant, audit=writer, keys=KEYS, clock=clock,
                                expected=scope if expected is None else expected, allow_test_keys=allow)


def refused(code, *args, **kwargs):
    with pytest.raises(sr.ReceiptError) as err:
        admit(*args, **kwargs)
    assert err.value.code == code


def counts(writer):
    db = writer.chain.db
    events = db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    has = db.execute("SELECT 1 FROM sqlite_master WHERE name='receipt_nonces'").fetchone()
    return events, (db.execute("SELECT COUNT(*) FROM receipt_nonces").fetchone()[0] if has else 0)


def alter(writer, *statements):
    for statement in statements:
        writer.chain.db.execute(statement)
    writer.chain.db.commit()


def test_admission_records_nonce_and_anchored_audit_event_together(store):
    admitted = admit(store)
    assert counts(store) == (1, 1)
    assert store.verify()["status"] == "anchored_verified"
    event = store.find_event(admitted.audit_event_id)
    assert event["event_type"] == "receipt_consumed" and event["receipt_hash"] == admitted.receipt_hash
    assert f"tenant:{BASE['tenant']}" in event["resource_ids"]
    assert "[REDACTED]" not in json.dumps(event)
    assert BASE["nonce"] not in json.dumps(event) and f"{0:032x}" not in json.dumps(event)
    with pytest.raises(TypeError):
        admitted.receipt["tenant"] = "other"
    admit(store, 1)
    assert counts(store) == (2, 2)


def test_replay_is_refused_after_the_store_is_reopened(tmp_path, store):
    admit(store)
    with open_anchored_audit(*paths(tmp_path), "tenant-a-chain") as reopened:
        refused("REPLAY", reopened)
        assert counts(reopened) == (1, 1)


def test_concurrent_admission_from_separate_connections_has_one_winner(tmp_path, store):
    results, barrier = [], threading.Barrier(6)

    def go():
        with open_anchored_audit(*paths(tmp_path), "tenant-a-chain") as writer:
            barrier.wait()
            try:
                admit(writer)
                results.append("ok")
            except sr.ReceiptError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=go) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["REPLAY"] * 5 + ["ok"]
    assert counts(store) == (1, 1)


def test_failed_verification_writes_nothing_and_does_not_burn_the_nonce(store):
    _, scope = envelope()
    refused("SCOPE_MISMATCH", store, expected={**scope, "project": "other"})
    refused("TEST_KEY_REFUSED", store, allow=False)
    assert counts(store) == (0, 0)
    admit(store)


def test_store_tenant_must_match_the_receipt_even_if_the_requested_scope_agrees(store):
    refused("TENANT_MISMATCH", store, tenant="tenant-b")
    assert counts(store) == (0, 0)


def test_a_store_never_holds_two_tenants(store):
    admit(store)
    env, scope = envelope(1, tenant="tenant-b")
    with pytest.raises(sr.ReceiptError) as err:
        ledger.admit_receipt(env, tenant="tenant-b", audit=store, keys=KEYS, clock=lambda: NOW,
                             expected=scope, allow_test_keys=True)
    assert err.value.code == "TENANT_MISMATCH"
    assert counts(store) == (1, 1)


def test_receipt_expiring_while_waiting_for_the_lock_is_refused(store):
    times = iter([NOW, NOW + timedelta(minutes=10)])
    refused("EXPIRED", store, clock=lambda: next(times))
    assert counts(store) == (0, 0) and store.verify()["valid"]
    admit(store)


@pytest.mark.parametrize("second", [NOW - timedelta(seconds=1), NOW.replace(tzinfo=None)])
def test_clock_going_backwards_or_losing_its_zone_is_refused(store, second):
    times = iter([NOW, second])
    refused("BAD_CLOCK", store, clock=lambda: next(times))
    assert counts(store) == (0, 0)


def test_unanchored_writer_is_refused(tmp_path):
    chain = AuditChainStore(tmp_path / "plain.sqlite3")
    refused("AUDIT_REQUIRED", chain)
    assert chain.verify()["entries"] == 0
    chain.close()


def test_chain_with_an_unanchored_tail_refuses_admission(store):
    store.chain.append({"event_id": "side-door", "event_type": "t"})
    refused("AUDIT_UNANCHORED", store)
    assert counts(store) == (1, 0)


def test_rolled_back_database_cannot_reuse_a_spent_receipt(tmp_path, store):
    db_path, anchor_path = paths(tmp_path)
    old = tmp_path / "old.sqlite3"
    shutil.copy(db_path, old)
    admit(store)
    restored = AuditChainStore(old)
    writer = AnchoredAuditChain(restored, AnchorStore(anchor_path, "tenant-a-chain"))
    refused("AUDIT_UNANCHORED", writer)
    restored.close()


def test_anchor_write_failure_spends_the_receipt_and_refuses_the_action(store, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store.anchors, "advance", boom)
    refused("AUDIT_ANCHOR_WRITE_FAILED", store)
    assert counts(store) == (1, 1)
    monkeypatch.undo()
    refused("AUDIT_UNANCHORED", store)
    refused("AUDIT_UNANCHORED", store, 1)


def test_failure_while_recording_the_nonce_rolls_back_the_audit_event(store, monkeypatch):
    admit(store)

    def boom(db, row):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(ledger, "_record", boom)
    refused("LEDGER_ERROR", store, 1)
    assert counts(store) == (1, 1) and store.verify()["valid"]
    monkeypatch.undo()
    admit(store, 1)


def test_deleted_nonce_row_does_not_reopen_the_receipt_and_stops_admissions(store):
    admit(store)
    alter(store, "DROP TRIGGER protect_receipt_nonce_delete", "DELETE FROM receipt_nonces",
          ledger._SCHEMA["protect_receipt_nonce_delete"])
    refused("REPLAY", store)
    refused("LEDGER_INCONSISTENT", store, 1)
    assert counts(store) == (1, 0)


def test_added_nonce_row_stops_admissions(store):
    admit(store)
    alter(store, "INSERT INTO receipt_nonces VALUES ('k','n','tenant-a','h','e','forged')")
    refused("LEDGER_INCONSISTENT", store, 1)


def test_dropped_nonce_table_is_not_silently_recreated(store):
    admit(store)
    alter(store, "DROP TABLE receipt_nonces")
    refused("LEDGER_INCONSISTENT", store, 1)
    assert counts(store) == (1, 0)


@pytest.mark.parametrize("statements", [
    ("DROP TRIGGER protect_receipt_nonce_delete",),
    ("DROP TRIGGER protect_receipt_nonce_update",),
    ("CREATE TRIGGER swallow BEFORE INSERT ON receipt_nonces BEGIN SELECT RAISE(IGNORE); END",),
    ("CREATE TRIGGER swallow BEFORE INSERT ON RECEIPT_NONCES BEGIN SELECT RAISE(IGNORE); END",),
    ("CREATE INDEX extra ON receipt_nonces(tenant)",),
])
def test_altered_ledger_schema_is_refused(store, statements):
    admit(store)
    alter(store, *statements)
    refused("LEDGER_SCHEMA", store, 1)
    assert counts(store) == (1, 1)


def test_precreated_weak_nonce_table_is_refused(store):
    alter(store, "CREATE TABLE receipt_nonces (key_id, nonce, tenant, receipt_hash, expires_at, audit_event_id)")
    refused("LEDGER_SCHEMA", store)
    assert counts(store) == (0, 0)


def test_trigger_that_swallows_the_audit_event_cannot_admit_a_receipt(store):
    alter(store, "CREATE TRIGGER swallow_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(IGNORE); END")
    refused("LEDGER_INCONSISTENT", store)
    assert counts(store) == (0, 0)


def test_in_transaction_hook_commits_or_rolls_back_with_the_event(tmp_path):
    chain = AuditChainStore(tmp_path / "c.sqlite3")
    chain.db.execute("CREATE TABLE side (v TEXT)")
    chain.db.commit()

    def failing(db):
        db.execute("INSERT INTO side VALUES ('x')")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        chain.append({"event_id": "one", "event_type": "t"}, in_transaction=failing)
    assert chain.verify()["entries"] == 0 and chain.db.execute("SELECT COUNT(*) FROM side").fetchone()[0] == 0
    chain.append({"event_id": "one", "event_type": "t"},
                 in_transaction=lambda db: db.execute("INSERT INTO side VALUES ('y')"))
    chain.close()
    other = sqlite3.connect(tmp_path / "c.sqlite3")
    assert other.execute("SELECT v FROM side").fetchall() == [("y",)]
    other.close()

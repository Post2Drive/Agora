"""Root rollover and root revocation between two pinned roots (test keys only)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agora.audit_chain import AuditChainStore
from agora.security import key_list as kl
from agora.security import receipt_gate as rg
from agora.security import signed_receipt as sr

from test_receipt_gate import (BASE, NOW, RECEIPTS, ROOT_SEED, SEED, STANDBY_SEED, consumed, opened, paths,
                               receipt, refused, settings, write)

__all__ = ["paths"]  # the imported fixture

HERE = Path(__file__).parent
VECTORS = json.loads((HERE / "vectors" / "root_change_vectors.json").read_text(encoding="utf-8"))
OUTSIDER_SEED = bytes([9]) * 32
SEEDS = {"A": ROOT_SEED, "B": STANDBY_SEED, "X": OUTSIDER_SEED}
ONLINE = "ed25519:" + sr.public_key(SEED).hex()


def root(name):
    return kl.RootKey(sr.public_key(SEEDS[name]), test=True)


def online(key_id=RECEIPTS["test_key"]["key_id"], public=ONLINE, status="active"):
    return {"key_id": key_id, "public": public, "not_before": "2026-11-01T00:00:00Z",
            "not_after": "2026-12-31T00:00:00Z", "status": status, "test": True}


def list_for(signer, version, keys=None):
    return kl.make_key_list(SEEDS[signer], {
        "type": "key_list", "v": 1, "alg": "ed25519", "list_version": version,
        "issued_at": "2026-11-24T12:00:00Z", "expires_at": "2026-11-24T12:15:00Z",
        "root_key_id": root(signer).key_id, "keys": [online()] if keys is None else keys,
    })


def statement(kind, old, new, listed, **changes):
    return {"type": kind, "v": 1, "alg": "ed25519", "old_root_key_id": root(old).key_id,
            "new_root_key_id": root(new).key_id,
            "key_list_hash": "sha256:" + hashlib.sha256(kl.DOMAIN + listed["key_list"].encode()).hexdigest(),
            **changes}


def signed(document, signer, domain=None):
    """Sign without the signer's own validation, so the verifier's checks are what is tested."""
    raw = sr.canonical_bytes(document)
    domain = domain or (kl.ROLLOVER_DOMAIN if document["type"] == "root_rollover" else kl.REVOCATION_DOMAIN)
    return {"root_change": raw.decode("ascii"), "sig": sr.sign(SEEDS[signer], domain + raw).hex()}


def rollover(listed, old="A", new="B"):
    return signed(statement("root_rollover", old, new, listed), old)


def revocation(listed, old="A", new="B"):
    return signed(statement("root_revocation", old, new, listed), new)


def count(gate):
    return gate._audit.chain.db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]


@pytest.fixture
def config(tmp_path, paths):
    return write(tmp_path, settings(paths))


@pytest.mark.parametrize("make", [rollover, revocation], ids=["rollover", "revocation"])
def test_a_root_change_is_one_event_and_the_new_root_admits(config, make):
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        before = count(gate)
        new_list = list_for("B", 2)
        assert gate.rotate_root(make(new_list), new_list) == 2 == gate.key_list_version
        assert count(gate) == before + 1
        event = gate._audit.find_event("key-list-accept-000000000002")
        assert event["root_change_hash"].startswith("sha256:") and "[REDACTED]" not in json.dumps(event)
        assert gate._audit.verify()["status"] == "anchored_verified"
        wire, request = receipt()
        assert gate.admit(wire, request=request) and consumed(gate) == 1


@pytest.mark.parametrize("make", [rollover, revocation], ids=["rollover", "revocation"])
def test_the_old_root_is_refused_for_good_and_the_change_survives_a_restart(config, make):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        gate.rotate_root(make(new_list), new_list)
    with opened(config) as gate:
        refused("BAD_SIGNATURE", gate.refresh_key_list, list_for("A", 3))
        # The old root cannot take the store back, by either kind of statement.
        back = list_for("A", 3)
        refused("ROOT_RETIRED", gate.rotate_root, rollover(back, "B", "A"), back)
        refused("ROOT_RETIRED", gate.rotate_root, revocation(back, "B", "A"), back)
        assert gate.refresh_key_list(new_list) == 2
        assert gate.refresh_key_list(list_for("B", 3)) == 3


def test_swapping_the_configured_pins_does_not_revive_the_old_root(tmp_path, paths, config):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        gate.rotate_root(rollover(new_list), new_list)
    swapped = settings(paths, root_public="ed25519:" + sr.public_key(ROOT_SEED).hex(),
                       standby_root_public="ed25519:" + sr.public_key(OUTSIDER_SEED).hex())
    with opened(write(tmp_path, swapped, "swapped.json")) as gate:
        # The store's active root (B) is no longer pinned: nothing can be loaded; A stays refused.
        refused("KEY_LIST_ROOT_UNPINNED", gate.refresh_key_list, list_for("A", 3))
        listed = list_for("X", 3)
        refused("KEY_LIST_ROOT_UNPINNED", gate.rotate_root, revocation(listed, "B", "X"), listed)


def test_the_next_standby_can_be_pinned_after_a_rollover(tmp_path, paths, config):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        gate.rotate_root(rollover(new_list), new_list)
    later = settings(paths, root_public="ed25519:" + sr.public_key(STANDBY_SEED).hex(),
                     standby_root_public="ed25519:" + sr.public_key(OUTSIDER_SEED).hex())
    with opened(write(tmp_path, later, "later.json")) as gate:
        assert gate.refresh_key_list(list_for("B", 3)) == 3
        third = list_for("X", 4)
        assert gate.rotate_root(rollover(third, "B", "X"), third) == 4


def test_a_standby_root_cannot_sign_an_ordinary_list(config):
    with opened(config) as gate:
        refused("BAD_SIGNATURE", gate.refresh_key_list, list_for("B", 1))
        gate.refresh_key_list(list_for("A", 1))
        refused("BAD_SIGNATURE", gate.refresh_key_list, list_for("B", 2))
        assert gate.key_list_version == 1


@pytest.mark.parametrize("make", [rollover, revocation], ids=["rollover", "revocation"])
def test_an_empty_store_can_apply_a_root_change(config, make):
    new_list = list_for("B", 5)
    with opened(config) as gate:
        assert gate.rotate_root(make(new_list), new_list) == 5
        refused("BAD_SIGNATURE", gate.refresh_key_list, list_for("A", 6))


def test_without_a_change_a_store_does_not_follow_a_different_configured_root(tmp_path, paths, config):
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
    other = settings(paths, root_public="ed25519:" + sr.public_key(OUTSIDER_SEED).hex())
    with opened(write(tmp_path, other, "other.json")) as gate:
        refused("KEY_LIST_ROOT_UNPINNED", gate.refresh_key_list, list_for("X", 2))
        assert count(gate) == 1  # only the first acceptance


def bad_changes():
    listed = list_for("B", 2)
    good = statement("root_rollover", "A", "B", listed)
    revoke = statement("root_revocation", "A", "B", listed)
    return [
        ("rollover-signed-by-new-root", "BAD_SIGNATURE", signed(good, "B")),
        ("revocation-signed-by-old-root", "BAD_SIGNATURE", signed(revoke, "A")),
        ("outsider", "BAD_SIGNATURE", signed(good, "X")),
        ("key-list-domain", "BAD_SIGNATURE", signed(good, "A", kl.DOMAIN)),
        ("type-does-not-match-signer", "ROOT_CHANGE_TYPE", signed(good, "B", kl.REVOCATION_DOMAIN)),
        ("revocation-type-signed-as-rollover", "ROOT_CHANGE_TYPE", signed(revoke, "A", kl.ROLLOVER_DOMAIN)),
        ("unknown-type", "ROOT_CHANGE_TYPE", signed({**good, "type": "other"}, "A", kl.ROLLOVER_DOMAIN)),
        ("extra-field", "ROOT_CHANGE_FIELDS", signed({**good, "extra": "x"}, "A")),
        ("version", "BAD_VERSION", signed({**good, "v": 2}, "A")),
        ("boolean-version", "BAD_VERSION", signed({**good, "v": True}, "A")),
        ("algorithm", "BAD_ALGORITHM", signed({**good, "alg": "rsa"}, "A")),
        ("hash-shape", "ROOT_CHANGE_FIELDS", signed({**good, "key_list_hash": 5}, "A")),
        ("same-root", "ROOT_CHANGE_ROOTS", signed({**good, "new_root_key_id": root("A").key_id}, "A")),
        ("names-unpinned-new", "ROOT_CHANGE_ROOTS", signed({**good, "new_root_key_id": root("X").key_id}, "A")),
        ("names-wrong-old", "ROOT_CHANGE_ROOTS", signed({**good, "old_root_key_id": root("X").key_id}, "A")),
        ("another-list", "ROOT_CHANGE_LIST", signed(statement("root_rollover", "A", "B", list_for("B", 3)), "A")),
        ("envelope", "MALFORMED", {**signed(good, "A"), "extra": "x"}),
        ("not-hex", "MALFORMED", {**signed(good, "A"), "sig": "zz"}),
    ]


@pytest.mark.parametrize("name,code,change", bad_changes(), ids=[c[0] for c in bad_changes()])
def test_a_bad_statement_changes_nothing(config, name, code, change):
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        before = count(gate)
        refused(code, gate.rotate_root, change, list_for("B", 2))
        assert count(gate) == before and gate.key_list_version == 1
        wire, request = receipt()
        assert gate.admit(wire, request=request)
        assert gate.refresh_key_list(list_for("A", 2)) == 2


def test_the_new_list_must_be_signed_by_the_other_pinned_root(config):
    with opened(config) as gate:
        for signer in ("A", "X"):
            listed = list_for(signer, 2)
            refused("BAD_SIGNATURE", gate.rotate_root, rollover(listed), listed)


@pytest.mark.parametrize("code,keys,version", [
    ("KEY_LIST_ROLLBACK", None, 2),
    ("KEY_LIST_SUPERSEDED", None, 3),  # same version, different bytes
    ("KEY_STATUS_REGRESSION", [online()], 4),
    ("KEY_REBOUND", [online(public="ed25519:" + sr.public_key(bytes([3]) * 32).hex())], 4),
])
def test_history_rules_carry_across_a_root_change(config, code, keys, version):
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 3, [online(status="revoked")]))
        before = count(gate)
        listed = list_for("B", version, keys if keys is not None else [online(status="revoked")])
        refused(code, gate.rotate_root, revocation(listed), listed)
        assert count(gate) == before


@pytest.mark.parametrize("name", ["A", "B"])
def test_no_pinned_root_may_be_listed_as_an_online_key(config, name):
    """List validation only knows the signing root; the other pinned root is refused by the store check."""
    keys = [online(), online("zz-root", "ed25519:" + root(name).public.hex())]
    with opened(config) as gate:
        if name == "A":
            body = json.loads(list_for("B", 2)["key_list"])
            body["keys"] = keys
            listed = kl.make_key_list(STANDBY_SEED, body)
            refused("KEY_LIST_KEYS", gate.rotate_root, rollover(listed), listed)
        else:
            body = json.loads(list_for("A", 1)["key_list"])
            body["keys"] = keys
            refused("KEY_LIST_KEYS", gate.refresh_key_list, kl.make_key_list(ROOT_SEED, body))
        assert count(gate) == 0


def test_a_retired_root_may_not_come_back_as_an_online_key(tmp_path, paths, config):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        gate.rotate_root(rollover(new_list), new_list)
    later = settings(paths, root_public="ed25519:" + sr.public_key(STANDBY_SEED).hex(),
                     standby_root_public="ed25519:" + sr.public_key(OUTSIDER_SEED).hex())
    with opened(write(tmp_path, later, "later.json")) as gate:
        listed = list_for("B", 3, [online(), online("zz-root", "ed25519:" + root("A").public.hex())])
        refused("KEY_LIST_KEYS", gate.refresh_key_list, listed)


def test_an_older_gate_stops_admitting_once_another_applies_a_change(config):
    wire, request = receipt()
    with opened(config) as first, opened(config) as second:
        first.refresh_key_list(list_for("A", 1))
        new_list = list_for("B", 2)
        second.rotate_root(revocation(new_list), new_list)
        refused("KEY_LIST_SUPERSEDED", first.admit, wire, request=request)
        assert consumed(first) == 0


@pytest.mark.parametrize("operation", ["refresh", "rotate"])
def test_a_root_change_committed_after_the_first_look_is_caught_in_the_transaction(config, monkeypatch, operation):
    with opened(config) as first, opened(config) as second:
        first.refresh_key_list(list_for("A", 1))
        applied = list_for("B", 2)
        real = kl._read_active

        def race(writer, pinned):
            seen = real(writer, pinned)
            monkeypatch.setattr(kl, "_read_active", real)
            second.rotate_root(revocation(applied), applied)
            return seen

        monkeypatch.setattr(kl, "_read_active", race)
        if operation == "refresh":
            refused("KEY_LIST_ROOT_CHANGED", first.refresh_key_list, list_for("A", 3))
        else:
            listed = list_for("B", 3)
            refused("KEY_LIST_ROOT_CHANGED", first.rotate_root, rollover(listed), listed)
        assert second._audit.find_event("key-list-accept-000000000003") is None


def test_an_applied_change_cannot_be_applied_again(config):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        gate.refresh_key_list(list_for("A", 1))
        change = rollover(new_list)
        gate.rotate_root(change, new_list)
        before = count(gate)
        refused("BAD_SIGNATURE", gate.rotate_root, change, new_list)
        assert count(gate) == before


def test_production_mode_refuses_a_change_to_a_test_marked_list(tmp_path, paths):
    new_list = list_for("B", 2)
    with opened(write(tmp_path, settings(paths, key_mode="production"))) as gate:
        refused("TEST_KEY_REFUSED", gate.rotate_root, rollover(new_list), new_list)


@pytest.mark.parametrize("standby,code", [(None, "ROOT_PINS"), (root("A"), "ROOT_PINS"),
                                          (kl.RootKey(bytes(32), test=True), "ROOT_PINS")])
def test_a_root_change_needs_a_distinct_usable_standby(config, standby, code):
    new_list = list_for("B", 2)
    with opened(config) as gate:
        refused(code, kl.accept_root_change, rollover(new_list), new_list, tenant=BASE["tenant"], root=root("A"),
                standby=standby, audit=gate._audit, clock=lambda: NOW, monotonic=lambda: 100.0,
                allow_test_keys=True)


def test_a_test_root_cannot_hand_over_without_the_test_switch(config):
    """Only the old root is test-marked here, so no other check can produce this refusal."""
    body = json.loads(list_for("B", 2)["key_list"])
    body["keys"] = [{**online(), "test": False}]
    new_list = kl.make_key_list(STANDBY_SEED, body)
    with opened(config) as gate:
        refused("TEST_KEY_REFUSED", kl.accept_root_change, rollover(new_list), new_list, tenant=BASE["tenant"],
                root=root("A"), standby=kl.RootKey(root("B").public, test=False), audit=gate._audit,
                clock=lambda: NOW, monotonic=lambda: 100.0)
        assert count(gate) == 0


@pytest.mark.parametrize("code,changes", [
    ("ROOT_CHANGE_TYPE", {"type": "other"}),
    ("ROOT_CHANGE_ROOTS", {"new_root_key_id": root("A").key_id}),
])
def test_the_test_signer_refuses_a_meaningless_statement(code, changes):
    document = {**statement("root_rollover", "A", "B", list_for("B", 2)), **changes}
    refused(code, kl.make_root_change, ROOT_SEED, document)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["name"] for c in VECTORS["cases"]])
def test_root_change_vector(case):
    raw = bytes.fromhex(case["canonical_hex"])
    envelope = {"root_change": raw.decode("ascii"), "sig": case["sig_hex"]}
    old = kl.RootKey(bytes.fromhex(VECTORS["old_root_public_hex"]), test=True)
    new = kl.RootKey(bytes.fromhex(VECTORS["new_root_public_hex"]), test=True)
    arguments = {"old": old, "new": new, "list_bytes": bytes.fromhex(VECTORS["key_list_canonical_hex"])}
    if case["verdict"] == "ok":
        assert raw == sr.canonical_bytes(case["input"])
        assert kl.verify_root_change(envelope, **arguments) == raw
        signer = ROOT_SEED if case["input"]["type"] == "root_rollover" else STANDBY_SEED
        assert kl.make_root_change(signer, case["input"]) == envelope
    else:
        refused(case["verdict"], kl.verify_root_change, envelope, **arguments)

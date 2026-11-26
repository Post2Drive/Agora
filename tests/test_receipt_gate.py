"""The governed receipt entry point and the key-list test vectors (test keys only)."""
import ast
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agora.audit_anchor import AnchorStore, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.security import key_list as kl
from agora.security import receipt_gate as rg
from agora.security import signed_receipt as sr

HERE = Path(__file__).parent
RECEIPTS = json.loads((HERE / "vectors" / "receipt_vectors.json").read_text(encoding="utf-8"))
LISTS = json.loads((HERE / "vectors" / "key_list_vectors.json").read_text(encoding="utf-8"))
BASE = RECEIPTS["base_receipt"]
SEED = bytes.fromhex(RECEIPTS["test_key"]["seed_hex"])
ROOT_SEED = bytes([7]) * 32  # test root, never a production key
STANDBY_SEED = bytes([8]) * 32  # test standby root, never a production key
NOW = datetime(2026, 11, 24, 12, 1, tzinfo=timezone.utc)


def envelope_for(version=1, *, test=True, seed=ROOT_SEED, status="active"):
    return kl.make_key_list(seed, {
        "type": "key_list", "v": 1, "alg": "ed25519", "list_version": version,
        "issued_at": "2026-11-24T12:00:00Z", "expires_at": "2026-11-24T12:15:00Z",
        "root_key_id": kl.fingerprint(sr.public_key(seed)),
        "keys": [{"key_id": RECEIPTS["test_key"]["key_id"], "public": "ed25519:" + sr.public_key(SEED).hex(),
                  "not_before": "2026-11-01T00:00:00Z", "not_after": "2026-12-31T00:00:00Z",
                  "status": status, "test": test}],
    })


def receipt(n=0, **changes):
    document = {**BASE, "nonce": f"{n:032x}", **changes}
    return sr.make_receipt(SEED, document), {name: document[name] for name in rg.REQUEST_FIELDS}


@pytest.fixture
def paths(tmp_path):
    db, anchor = tmp_path / "audit.sqlite3", tmp_path / "anchors" / "a.jsonl"
    chain = AuditChainStore(db)
    bootstrap_anchor(chain, AnchorStore(anchor, "tenant-a-chain"), performed_by="maint-1")
    chain.close()
    return db, anchor


def settings(paths, **changes):
    return {"type": "receipt_gate_config", "v": 2, "tenant": BASE["tenant"], "release_id": BASE["release_id"],
            "key_mode": "test", "root_public": "ed25519:" + sr.public_key(ROOT_SEED).hex(),
            "standby_root_public": "ed25519:" + sr.public_key(STANDBY_SEED).hex(),
            "audit_db": str(paths[0]), "audit_anchor": str(paths[1]), "chain_id": "tenant-a-chain", **changes}


def write(tmp_path, document, name="gate.json"):
    path = tmp_path / name
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


def opened(path, now=NOW):
    return rg.open_receipt_gate(path, clock=lambda: now, monotonic=lambda: 100.0)


def refused(code, call, *args, **kwargs):
    with pytest.raises(sr.ReceiptError) as err:
        call(*args, **kwargs)
    assert err.value.code == code, str(err.value)


def consumed(gate):
    return gate._audit.chain.db.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_id LIKE 'receipt-consume-%'").fetchone()[0]


def test_a_receipt_is_admitted_once_through_the_configured_gate(tmp_path, paths):
    config = write(tmp_path, settings(paths))
    wire, request = receipt()
    with opened(config) as gate:
        assert gate.key_list_version is None
        assert gate.refresh_key_list(envelope_for()) == 1 == gate.key_list_version
        admitted = gate.admit(wire, request=request)
        assert admitted.receipt["tenant"] == BASE["tenant"] and consumed(gate) == 1
        refused("REPLAY", gate.admit, wire, request=request)
    # After a restart nothing is held in memory: the list must be presented again, and the nonce stays spent.
    with opened(config) as gate:
        refused("KEY_LIST_NOT_LOADED", gate.admit, wire, request=request)
        gate.refresh_key_list(envelope_for())
        refused("REPLAY", gate.admit, wire, request=request)


@pytest.mark.parametrize("field,value", [("tenant", "tenant-b"), ("release_id", "rel-other")])
def test_a_validly_signed_receipt_for_another_worker_is_refused(tmp_path, paths, field, value):
    wire, request = receipt(**{field: value})
    with opened(write(tmp_path, settings(paths))) as gate:
        gate.refresh_key_list(envelope_for())
        refused("SCOPE_MISMATCH", gate.admit, wire, request=request)
        assert consumed(gate) == 0


@pytest.mark.parametrize("name", rg.REQUEST_FIELDS)
def test_every_request_field_must_match_the_receipt(tmp_path, paths, name):
    wire, request = receipt()
    other = "sha256:" + "0" * 64 if name.endswith("_hash") else "something-else"
    with opened(write(tmp_path, settings(paths))) as gate:
        gate.refresh_key_list(envelope_for())
        refused("SCOPE_MISMATCH", gate.admit, wire, request={**request, name: other})
        assert consumed(gate) == 0


@pytest.mark.parametrize("change", [
    {"tenant": BASE["tenant"]}, {"release_id": BASE["release_id"]}, {"allow_test_keys": "yes"},
    {"purpose": None}, {"purpose": 1}, "drop-purpose", "not-a-mapping",
])
def test_a_request_cannot_name_worker_settings_or_omit_scope(tmp_path, paths, change):
    wire, request = receipt()
    if change == "drop-purpose":
        request.pop("purpose")
    elif change == "not-a-mapping":
        request = list(request.items())
    else:
        request.update(change)
    with opened(write(tmp_path, settings(paths))) as gate:
        gate.refresh_key_list(envelope_for())
        refused("BAD_REQUEST", gate.admit, wire, request=request)
        assert consumed(gate) == 0


def test_a_mapping_that_changes_between_reads_cannot_add_fields(tmp_path, paths):
    wire, request = receipt()

    class Shifting(Mapping):
        """Shows the correct fields on the first iteration and an extra one afterwards."""

        reads = 0

        def __getitem__(self, name):
            return request.get(name, "extra")

        def __len__(self):
            return len(request)

        def __iter__(self):
            self.reads += 1
            return iter(list(request) if self.reads == 1 else [*request, "allow_test_keys"])

    with opened(write(tmp_path, settings(paths))) as gate:
        gate.refresh_key_list(envelope_for())
        refused("BAD_REQUEST", gate.admit, wire, request=Shifting())
        assert consumed(gate) == 0


def test_a_list_signed_by_an_unpinned_root_is_refused(tmp_path, paths):
    with opened(write(tmp_path, settings(paths))) as gate:
        refused("BAD_SIGNATURE", gate.refresh_key_list, envelope_for(seed=bytes([9]) * 32))
        assert gate.key_list_version is None


def test_production_mode_refuses_test_marked_keys_and_admits_unmarked_ones(tmp_path, paths):
    wire, request = receipt()
    with opened(write(tmp_path, settings(paths, key_mode="production"))) as gate:
        refused("TEST_KEY_REFUSED", gate.refresh_key_list, envelope_for())
        refused("KEY_LIST_NOT_LOADED", gate.admit, wire, request=request)
        gate.refresh_key_list(envelope_for(test=False))
        assert gate.admit(wire, request=request).receipt["nonce"] == f"{0:032x}"


def test_a_refused_refresh_keeps_the_loaded_list(tmp_path, paths):
    with opened(write(tmp_path, settings(paths))) as gate:
        gate.refresh_key_list(envelope_for(2))
        refused("KEY_LIST_ROLLBACK", gate.refresh_key_list, envelope_for(1))
        refused("BAD_SIGNATURE", gate.refresh_key_list, envelope_for(3, seed=bytes([9]) * 32))
        assert gate.key_list_version == 2
        wire, request = receipt()
        assert gate.admit(wire, request=request)


def test_a_revocation_accepted_by_another_gate_stops_an_older_one(tmp_path, paths):
    config = write(tmp_path, settings(paths))
    wire, request = receipt()
    with opened(config) as first, opened(config) as second:
        first.refresh_key_list(envelope_for(1))
        second.refresh_key_list(envelope_for(2, status="revoked"))
        refused("KEY_LIST_SUPERSEDED", first.admit, wire, request=request)
        refused("KEY_NOT_ACTIVE", second.admit, wire, request=request)
        assert consumed(first) == 0


@pytest.mark.parametrize("changes", [
    {"type": "other"}, {"v": 1}, {"v": True},
    {"standby_root_public": "ed25519:" + "00" * 32}, {"standby_root_public": None},
    {"standby_root_public": "ed25519:" + sr.public_key(ROOT_SEED).hex()}, {"tenant": ""}, {"tenant": 5}, {"release_id": "a b"},
    {"key_mode": "dev"}, {"root_public": "ed25519:" + "00" * 32}, {"root_public": "ed25519:" + "AB" * 32},
    {"root_public": sr.public_key(ROOT_SEED).hex()},
    {"root_public": "ed25519:" + sr.public_key(ROOT_SEED).hex().upper()},
    {"root_public": "xxxxxxx:" + sr.public_key(ROOT_SEED).hex()}, {"audit_db": "audit.sqlite3"},
    {"audit_anchor": "anchors/a.jsonl"}, {"audit_db": 1}, {"chain_id": ""}, {"allow_test_keys": True},
])
def test_a_malformed_configuration_is_refused(tmp_path, paths, changes):
    refused("GATE_CONFIG", rg.load_gate_config, write(tmp_path, settings(paths, **changes)))


@pytest.mark.parametrize("name", sorted(rg._CONFIG_FIELDS))
def test_no_configuration_field_has_a_default(tmp_path, paths, name):
    document = settings(paths)
    del document[name]
    refused("GATE_CONFIG", rg.load_gate_config, write(tmp_path, document))


@pytest.mark.parametrize("text", ["[]", "not json", "", "{}" + " " * 20000])
def test_an_unreadable_configuration_is_refused(tmp_path, text):
    refused("GATE_CONFIG", rg.load_gate_config, write(tmp_path, text))


def test_duplicate_fields_oversize_and_missing_files_are_refused(tmp_path, paths):
    text = json.dumps(settings(paths))
    refused("GATE_CONFIG", rg.load_gate_config, write(tmp_path, '{"tenant":"tenant-b",' + text[1:]))
    refused("GATE_CONFIG", rg.load_gate_config, write(tmp_path, text + " " * rg.MAX_CONFIG_BYTES))
    refused("GATE_CONFIG", rg.load_gate_config, tmp_path / "absent.json")


def test_a_symlinked_configuration_is_refused(tmp_path, paths):
    target = write(tmp_path, settings(paths))
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available")
    refused("GATE_CONFIG", rg.load_gate_config, link)


def test_the_gate_never_creates_or_bootstraps_a_store(tmp_path, paths):
    missing = tmp_path / "empty" / "new.sqlite3"
    missing.parent.mkdir()
    with pytest.raises(sr.ReceiptError) as err:
        with opened(write(tmp_path, settings(paths, audit_db=str(missing)))):
            pass
    assert err.value.code == "AUDIT_UNANCHORED" and "does not exist" in str(err.value)
    assert not missing.exists()
    refused("AUDIT_UNANCHORED", lambda: opened(write(tmp_path, settings(paths, chain_id="other-chain"))).__enter__())


def test_an_error_inside_the_gate_block_is_not_relabelled(tmp_path, paths):
    with pytest.raises(KeyError):
        with opened(write(tmp_path, settings(paths))):
            raise KeyError("caller bug")


def _called_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.alias):
            yield node.name


@pytest.mark.parametrize("name,allowed", [
    ("admit_receipt", {"security/receipt_ledger.py", "security/key_list.py"}),
    ("verify_receipt", {"security/signed_receipt.py", "security/receipt_ledger.py"}),
    ("admit_receipt_with_key_list", {"security/key_list.py", "security/receipt_gate.py"}),
    ("accept_key_list", {"security/key_list.py", "security/receipt_gate.py"}),
    ("accept_root_change", {"security/key_list.py", "security/receipt_gate.py"}),
    ("_record_acceptance", {"security/key_list.py"}),
])
def test_no_other_package_module_reaches_the_lower_level_functions(name, allowed):
    """A source check against accidental second paths, not a defence against code that hides the name."""
    package = HERE.parent / "agora"
    users = {p.relative_to(package).as_posix() for p in package.rglob("*.py") if name in set(_called_names(p))}
    assert users <= allowed, users - allowed


@pytest.mark.parametrize("case", LISTS["cases"], ids=[c["name"] for c in LISTS["cases"]])
def test_key_list_vector(case):
    raw = bytes.fromhex(case["canonical_hex"])
    envelope = {"key_list": raw.decode("ascii"), "sig": case["sig_hex"]}
    root = kl.RootKey(bytes.fromhex(LISTS["root_public_hex"]), test=LISTS["root_test"])
    now = datetime.strptime(case["now"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    arguments = {"root": root, "now": now, "allow_test_keys": case["allow_test_keys"]}
    if case["verdict"] == "ok":
        assert raw == sr.canonical_bytes(case["input"])
        assert kl.verify_key_list(envelope, **arguments) == raw
        assert kl.make_key_list(ROOT_SEED, case["input"]) == envelope
    else:
        refused(case["verdict"], kl.verify_key_list, envelope, **arguments)

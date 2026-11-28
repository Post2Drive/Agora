"""Signed release manifest and file self-check (test keys only)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agora import pathsafe
from agora.security import release_manifest as rm
from agora.security import signed_receipt as sr
from agora.security.key_list import RootKey

SEED = bytes(range(32))  # public test seed
OTHER_SEED = bytes(range(1, 33))
ROOT = RootKey(sr.public_key(SEED), test=True)
NOW = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)
VECTORS = json.loads((Path(__file__).parent / "vectors" / "release_manifest_vectors.json").read_text("utf-8"))


@pytest.fixture()
def release(tmp_path):
    base = tmp_path.resolve() / "release"
    (base / "pkg" / "sub").mkdir(parents=True)
    (base / "pkg" / "__init__.py").write_bytes(b"")
    (base / "pkg" / "engine.py").write_bytes(b"RATE = 1\n")
    (base / "pkg" / "sub" / "data.json").write_bytes(b"{}\n")
    return base


def manifest(base, **changes):
    body = rm.build_manifest(base, release_id="rel-1", built_at="2026-11-28T11:00:00Z",
                             min_key_list_version=3, root_key_id=ROOT.key_id)
    body.update(changes)
    return body


def signed(body, seed=SEED, domain=rm.DOMAIN):
    """Sign without the producer's own validation, so the verifier is what refuses."""
    raw = sr.canonical_bytes(body)
    return {"release_manifest": raw.decode("ascii"), "sig": sr.sign(seed, domain + raw).hex()}


def check(base, envelope, **changes):
    arguments = {"root": ROOT, "expected_release_id": "rel-1", "now": NOW, "allow_test_keys": True}
    arguments.update(changes)
    return rm.check_release(base, envelope, **arguments)


def unverified(result, reason):
    assert (result.integrity, result.reason) == (rm.UNVERIFIED, reason)
    # An unverified check never names a release or a manifest.
    assert (result.release_id, result.manifest_hash, result.min_key_list_version) == (None, None, None)


def test_a_clean_release_verifies(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    result = check(release, envelope)
    assert (result.integrity, result.reason, result.release_id, result.min_key_list_version) == (
        rm.VERIFIED, None, "rel-1", 3)
    assert result.manifest_hash.startswith("sha256:")
    assert [f["path"] for f in manifest(release)["files"]] == [
        "pkg/__init__.py", "pkg/engine.py", "pkg/sub/data.json"]


def test_empty_directories_are_ignored(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / "pkg" / "empty").mkdir()
    assert check(release, envelope).integrity == rm.VERIFIED


@pytest.mark.parametrize("content", [b"RATE = 2\n", b"RATE = 100\n"], ids=["same-size", "other-size"])
def test_a_changed_file_is_unverified(release, content):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / "pkg" / "engine.py").write_bytes(content)
    unverified(check(release, envelope), "RELEASE_FILE_CHANGED")


@pytest.mark.parametrize("name", ["pkg/extra.py", "pkg/__pycache__/engine.cpython-312.pyc", ".hidden",
                                  "pkg/odd name.py"])
def test_an_unlisted_file_is_unverified(release, name):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / name).parent.mkdir(exist_ok=True)
    (release / name).write_bytes(b"x")
    unverified(check(release, envelope), "RELEASE_FILE_UNLISTED")


def test_a_missing_file_is_unverified(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / "pkg" / "sub" / "data.json").unlink()
    unverified(check(release, envelope), "RELEASE_FILE_MISSING")


@pytest.mark.parametrize("target_is_directory", [False, True], ids=["file", "directory"])
def test_a_link_in_the_release_is_unverified(release, tmp_path, target_is_directory):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    target = tmp_path.resolve() / "outside"
    if target_is_directory:
        target.mkdir()
    else:
        target.write_bytes(b"x")
    try:
        os.symlink(target, release / "pkg" / "link", target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    unverified(check(release, envelope), "RELEASE_TREE")


def test_a_release_reached_through_a_link_is_unverified(release, tmp_path):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    link = tmp_path.resolve() / "alias"
    try:
        os.symlink(release, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    unverified(check(link, envelope), "RELEASE_TREE")
    with pytest.raises(sr.ReceiptError, match="reached through a link"):  # refused before anything is listed
        manifest(link)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_special_file_is_unverified(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    os.mkfifo(release / "pkg" / "pipe")
    unverified(check(release, envelope), "RELEASE_TREE")


def test_an_unreadable_subdirectory_is_not_skipped(release, monkeypatch):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / "pkg" / "locked").mkdir()
    real = os.scandir

    def scandir(path):
        if Path(path).name == "locked":
            raise PermissionError("denied")
        return real(path)

    monkeypatch.setattr(rm.os, "scandir", scandir)
    unverified(check(release, envelope), "RELEASE_TREE")


def test_a_file_added_while_hashing_is_unverified(release, monkeypatch):
    envelope = rm.make_release_manifest(SEED, manifest(release))

    def add(path):
        (release / "pkg" / "late.py").write_bytes(b"x")

    monkeypatch.setattr(pathsafe, "_RACE_HOOK", add)
    unverified(check(release, envelope), "RELEASE_TREE")


def test_a_file_replaced_while_it_is_read_is_unverified(release, monkeypatch):
    envelope = rm.make_release_manifest(SEED, manifest(release))

    def grow(path):
        with open(path, "ab") as handle:
            handle.write(b"#")

    monkeypatch.setattr(pathsafe, "_RACE_HOOK", grow)
    unverified(check(release, envelope), "RELEASE_TREE")


def test_a_file_of_another_size_is_refused_before_it_is_read(release, monkeypatch):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    (release / "pkg" / "__init__.py").write_bytes(b"#" * 64)
    monkeypatch.setattr(rm.pathsafe, "read_stable_bytes", lambda path: pytest.fail("read " + str(path)))
    unverified(check(release, envelope), "RELEASE_FILE_CHANGED")


def test_missing_manifest_is_unverified(release):
    unverified(check(release, None), "RELEASE_MANIFEST_MISSING")


@pytest.mark.parametrize("envelope", [{}, "text", {"release_manifest": "{}"},
                                      {"release_manifest": 1, "sig": "00"},
                                      {"release_manifest": "{}", "sig": "zz"},
                                      {"release_manifest": "é", "sig": "00"}])
def test_malformed_envelope_is_unverified(release, envelope):
    unverified(check(release, envelope), "MALFORMED")


def test_oversized_manifest_is_refused_before_its_signature(release, monkeypatch):
    monkeypatch.setattr(rm, "MAX_BYTES", 8)
    unverified(check(release, signed(manifest(release))), "MALFORMED")


def test_another_signer_is_unverified(release):
    unverified(check(release, signed(manifest(release), seed=OTHER_SEED)), "BAD_SIGNATURE")


@pytest.mark.parametrize("domain", [b"", sr.DOMAIN, b"agora.keylist.v1\x00"])
def test_a_signature_for_another_domain_is_unverified(release, domain):
    unverified(check(release, signed(manifest(release), domain=domain)), "BAD_SIGNATURE")


def test_an_edited_manifest_is_unverified(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    envelope["release_manifest"] = envelope["release_manifest"].replace("rel-1", "rel-2")
    unverified(check(release, envelope, expected_release_id="rel-2"), "BAD_SIGNATURE")


def test_a_test_root_needs_an_explicit_allow(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    unverified(check(release, envelope, allow_test_keys=False), "TEST_KEY_REFUSED")


def test_a_manifest_naming_another_root_is_unverified(release):
    body = manifest(release, root_key_id=RootKey(sr.public_key(OTHER_SEED)).key_id)
    unverified(check(release, signed(body)), "RELEASE_ROOT")


def test_another_release_id_is_unverified(release):
    """An older signed release is not accepted unless configuration names it."""
    envelope = rm.make_release_manifest(SEED, manifest(release))
    unverified(check(release, envelope, expected_release_id="rel-2"), "RELEASE_ID_MISMATCH")


def test_build_time_in_the_future_is_unverified(release):
    envelope = signed(manifest(release, built_at="2026-11-28T12:00:31Z"))
    unverified(check(release, envelope), "RELEASE_NOT_YET_VALID")
    assert check(release, signed(manifest(release, built_at="2026-11-28T12:00:30Z"))).integrity == rm.VERIFIED


def test_a_naive_clock_is_unverified(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    unverified(check(release, envelope, now=NOW.replace(tzinfo=None)), "BAD_CLOCK")


def test_an_unexpected_error_is_unverified(release, monkeypatch):
    envelope = rm.make_release_manifest(SEED, manifest(release))

    def broken(*args):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(rm, "_check_files", broken)
    unverified(check(release, envelope), "RELEASE_CHECK_ERROR")


def test_a_directory_that_is_not_there_is_unverified(release):
    envelope = rm.make_release_manifest(SEED, manifest(release))
    unverified(check(release / "nope", envelope), "RELEASE_TREE")
    with pytest.raises(sr.ReceiptError, match="not a directory"):
        manifest(release / "nope")


def _entry(path):
    return {"path": path, "sha256": "sha256:" + "0" * 64, "size": 0}


@pytest.mark.parametrize("path", ["../x", "a/../x", "./x", "/etc/passwd", "a//b", "a/", "", "a\\b", "C:x",
                                  "a b", "x.", "...", "a\nb", "x\n", "a" * 513, 7])
def test_unusable_paths_are_refused(release, path):
    unverified(check(release, signed(manifest(release, files=[_entry(path)]))), "RELEASE_FILES")


@pytest.mark.parametrize("files", [
    [], [_entry("b"), _entry("a")], [_entry("a"), _entry("a")], [_entry("A"), _entry("a")],
    [dict(_entry("a"), mode=1)], [{"path": "a", "size": 0}], [dict(_entry("a"), size=-1)],
    [dict(_entry("a"), size=True)], [dict(_entry("a"), size=rm.MAX_FILE_BYTES + 1)],
    [dict(_entry("a"), sha256="0" * 64)], "a",
], ids=["empty", "unsorted", "duplicate", "case-duplicate", "extra-field", "missing-field", "negative",
        "bool-size", "huge", "bare-hash", "not-a-list"])
def test_unusable_file_lists_are_refused(release, files):
    unverified(check(release, signed(manifest(release, files=files))), "RELEASE_FILES")


@pytest.mark.parametrize("changes,reason", [
    ({"type": "key_list"}, "RELEASE_TYPE"), ({"v": 2}, "BAD_VERSION"), ({"v": True}, "BAD_VERSION"),
    ({"alg": "none"}, "BAD_ALGORITHM"), ({"release_id": "a b"}, "RELEASE_FIELDS"),
    ({"release_id": 1}, "RELEASE_FIELDS"), ({"root_key_id": "root"}, "RELEASE_FIELDS"),
    ({"built_at": "2026-11-28 11:00:00"}, "BAD_TIME"), ({"min_key_list_version": 0}, "RELEASE_FIELDS"),
    ({"min_key_list_version": "3"}, "RELEASE_FIELDS"), ({"extra": 1}, "RELEASE_FIELDS"),
])
def test_unusable_manifest_fields_are_refused(release, changes, reason):
    unverified(check(release, signed(manifest(release, **changes))), reason)


def test_non_canonical_bytes_are_refused(release):
    raw = json.dumps(manifest(release), indent=1).encode("ascii")
    envelope = {"release_manifest": raw.decode("ascii"), "sig": sr.sign(SEED, rm.DOMAIN + raw).hex()}
    unverified(check(release, envelope), "NON_CANONICAL")


@pytest.mark.parametrize("name", ["pkg/__pycache__/engine.cpython-312.pyc", "pkg/stray.pyc", "pkg/old.PYO"])
def test_build_refuses_compiled_files(release, name):
    (release / name).parent.mkdir(exist_ok=True)
    (release / name).write_bytes(b"x")
    with pytest.raises(sr.ReceiptError, match="compiled files"):
        manifest(release)


def test_build_refuses_a_name_no_manifest_can_list(release):
    (release / "pkg" / "odd name.py").write_bytes(b"x")
    with pytest.raises(sr.ReceiptError, match="cannot be listed"):
        manifest(release)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["name"] for c in VECTORS["cases"]])
def test_release_manifest_vector(case):
    raw = bytes.fromhex(case["canonical_hex"])
    envelope = {"release_manifest": raw.decode("ascii"), "sig": case["sig_hex"]}
    root = RootKey(bytes.fromhex(VECTORS["root_public_hex"]), test=VECTORS["root_test"])
    now = datetime.strptime(case["now"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    arguments = {"root": root, "now": now, "allow_test_keys": case["allow_test_keys"]}
    if case["verdict"] == "ok":
        assert raw == sr.canonical_bytes(case["input"])
        assert rm.verify_release_manifest(envelope, **arguments) == raw
        assert rm.make_release_manifest(SEED, case["input"]) == envelope
    else:
        with pytest.raises(sr.ReceiptError) as refused:
            rm.verify_release_manifest(envelope, **arguments)
        assert refused.value.code == case["verdict"]

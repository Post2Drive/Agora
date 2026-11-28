"""Signed release manifest and file self-check: format, local verifier, test keys only.

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md sections 3A ("Release verification, fail closed"),
3B (items 1 and 4) and 4.

A release manifest names a release id, a build time, the lowest key-list version the release accepts and
``{path, sha256, size}`` for every file of the release, sorted by path. It uses the receipt canonical form and
is signed by a pinned root under its own domain tag. ``check_release`` verifies the signature and then compares
one directory with the manifest: every listed file must match, and nothing else may be there. Every failure,
including a missing manifest, gives ``integrity == "unverified"``; nothing defaults to verified.

Compiled files are not excused. An unlisted ``__pycache__`` file makes a release unverified, because Python can
execute it in place of the source that was hashed. A release directory has to be read-only and run without
writing or already holding bytecode.

What a "verified" result means: when each file was read, the directory held exactly the signed files. It does
NOT prove which code a process is running (that needs the attestation of 3B item 5), that files stayed the same
afterwards, or anything about code outside the directory (the interpreter, dependencies, ``sys.path``). This
module is itself among the files it checks, so changed code in the same process can report anything. It is
detection, not prevention. There is no release revocation: the caller states the release id it expects, from its
own configuration, and an older signed manifest still verifies if configuration names that release.

Test keys only. Not built: a build or signing pipeline, a production key, any engine, pipeline or receipt-gate
call, run stamping, the refusal to issue receipts to unverified releases, and enforcement of
``min_key_list_version`` (it is returned for a later caller).
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from agora import pathsafe
from agora.security import signed_receipt as sr
from agora.security.key_list import MAX_LIST_VERSION, RootKey

DOMAIN = b"agora.release.v1\x00"
OBJECT_TYPE = "release_manifest"
VERSION = 1
MAX_BYTES = 4 * 1024 * 1024
MAX_FILES = 20_000
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_PATH_CHARS = 512
VERIFIED = "verified"
UNVERIFIED = "unverified"
_FIELDS = {"type", "v", "alg", "release_id", "built_at", "min_key_list_version", "root_key_id", "files"}
_FILE_FIELDS = {"path", "sha256", "size"}
_SEGMENT = re.compile(r"[A-Za-z0-9._\-]+")


def _refuse(code: str, detail: str = "") -> sr.ReceiptError:
    return sr.ReceiptError(code, detail)


def _usable_path(path: Any) -> bool:
    """A relative ``/``-separated path that names the same one file on Linux and Windows."""
    if not isinstance(path, str) or not 0 < len(path) <= MAX_PATH_CHARS:
        return False
    return all(
        _SEGMENT.fullmatch(part) is not None and not part.endswith(".")  # also refuses "." and ".."
        for part in path.split("/")
    )


def _validate(body: Mapping[str, Any]) -> None:
    if set(body) != _FIELDS:
        raise _refuse("RELEASE_FIELDS")
    if body["type"] != OBJECT_TYPE:
        raise _refuse("RELEASE_TYPE")
    if type(body["v"]) is not int or body["v"] != VERSION:
        raise _refuse("BAD_VERSION")
    if body["alg"] != sr.ALGORITHM:
        raise _refuse("BAD_ALGORITHM")
    if not isinstance(body["release_id"], str) or not sr._TOKEN.match(body["release_id"]):
        raise _refuse("RELEASE_FIELDS", "release_id")
    if not isinstance(body["root_key_id"], str) or not sr._HASH.match(body["root_key_id"]):
        raise _refuse("RELEASE_FIELDS", "root_key_id")
    sr._parse_time(body["built_at"])
    floor = body["min_key_list_version"]
    if type(floor) is not int or not 1 <= floor <= MAX_LIST_VERSION:
        raise _refuse("RELEASE_FIELDS", "min_key_list_version")
    files = body["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise _refuse("RELEASE_FILES", "file count")
    paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != _FILE_FIELDS:
            raise _refuse("RELEASE_FILES", "unknown or missing file field")
        if not _usable_path(entry["path"]):
            raise _refuse("RELEASE_FILES", "path")
        if not isinstance(entry["sha256"], str) or not sr._HASH.match(entry["sha256"]):
            raise _refuse("RELEASE_FILES", "sha256")
        if type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_FILE_BYTES:
            raise _refuse("RELEASE_FILES", "size")
        paths.append(entry["path"])
    if paths != sorted(paths) or len({p.lower() for p in paths}) != len(paths):
        raise _refuse("RELEASE_FILES", "paths must be sorted and unique ignoring case")


def _walk(directory: Path) -> set[str]:
    """Relative paths of every file below ``directory``. A link, special file or unreadable entry refuses.

    Empty directories are ignored.
    """
    found: set[str] = set()
    pending: list[tuple[Path, str]] = [(directory, "")]
    seen = 0
    while pending:
        current, prefix = pending.pop()
        try:
            with os.scandir(current) as listing:
                names = [item.name for item in listing]
            for name in names:
                seen += 1
                if seen > 2 * MAX_FILES:
                    raise _refuse("RELEASE_TREE", "too many entries")
                info = os.lstat(current / name)
                relative = prefix + name
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise _refuse("RELEASE_TREE", "a link or reparse point is in the release")
                if stat.S_ISDIR(info.st_mode):
                    pending.append((current / name, relative + "/"))
                elif stat.S_ISREG(info.st_mode):
                    found.add(relative)
                else:
                    raise _refuse("RELEASE_TREE", "a special file is in the release")
        except OSError as exc:
            raise _refuse("RELEASE_TREE", "the release directory cannot be read in full") from exc
    return found


def _release_directory(directory: str | os.PathLike[str]) -> Path:
    if pathsafe.is_unsafe_path(directory) or not os.path.isdir(directory):
        raise _refuse("RELEASE_TREE", "not a directory, or reached through a link")
    return Path(os.path.abspath(directory))


def _digest(path: Path, size: int | None = None) -> tuple[str, int]:
    """Hash one file. With ``size``, a file of another size is refused before it is read."""
    try:
        length = os.lstat(path).st_size
        if length != size if size is not None else length > MAX_FILE_BYTES:
            raise _refuse("RELEASE_FILE_CHANGED", "size")
        data = pathsafe.read_stable_bytes(path)
    except (OSError, pathsafe.UnsafePathError) as exc:
        raise _refuse("RELEASE_TREE", "a release file cannot be read safely") from exc
    return "sha256:" + hashlib.sha256(data).hexdigest(), len(data)


def build_manifest(
    directory: str | os.PathLike[str], *, release_id: str, built_at: str, min_key_list_version: int,
    root_key_id: str,
) -> dict[str, Any]:
    """The unsigned manifest of one clean build directory, for a build step. Keep the manifest outside it."""
    base = _release_directory(directory)
    files = []
    for relative in sorted(_walk(base)):
        if "__pycache__" in relative.split("/") or relative.lower().endswith((".pyc", ".pyo")):
            raise _refuse("RELEASE_FILES", "compiled files are in the build directory")
        if not _usable_path(relative):
            raise _refuse("RELEASE_FILES", "a file name cannot be listed in a manifest")
        sha256, size = _digest(base / relative)
        files.append({"path": relative, "sha256": sha256, "size": size})
    body = {
        "type": OBJECT_TYPE, "v": VERSION, "alg": sr.ALGORITHM, "release_id": release_id, "built_at": built_at,
        "min_key_list_version": min_key_list_version, "root_key_id": root_key_id, "files": files,
    }
    _validate(body)
    return body


def make_release_manifest(seed: bytes, body: Mapping[str, Any]) -> dict[str, str]:
    """Sign a manifest with a TEST root seed. Returns the wire envelope {release_manifest, sig}."""
    _validate(body)
    raw = sr.canonical_bytes(body)
    return {"release_manifest": raw.decode("ascii"), "sig": sr.sign(seed, DOMAIN + raw).hex()}


def verify_release_manifest(
    envelope: Mapping[str, Any], *, root: RootKey, now: datetime, allow_test_keys: bool = False,
) -> bytes:
    """Signature and shape only; no file is read. Returns the signed canonical bytes or raises ReceiptError."""
    if not isinstance(envelope, Mapping) or set(envelope) != {"release_manifest", "sig"}:
        raise _refuse("MALFORMED", "envelope must be exactly {release_manifest, sig}")
    text, sig = envelope["release_manifest"], envelope["sig"]
    if not isinstance(text, str) or not isinstance(sig, str) or len(text) > MAX_BYTES:
        raise _refuse("MALFORMED", "release_manifest and sig must be strings of bounded size")
    try:
        raw, signature = text.encode("ascii"), bytes.fromhex(sig)
    except (UnicodeEncodeError, ValueError) as exc:
        raise _refuse("MALFORMED", "release_manifest must be ASCII and sig hex") from exc
    if root.test and not allow_test_keys:
        raise _refuse("TEST_KEY_REFUSED", "test root")
    # Verify the signature over the received bytes before interpreting them.
    if not sr.verify_signature(root.public, DOMAIN + raw, signature):
        raise _refuse("BAD_SIGNATURE")
    body = sr.parse_canonical(raw)
    _validate(body)
    if body["root_key_id"] != root.key_id:
        raise _refuse("RELEASE_ROOT")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise _refuse("BAD_CLOCK", "now must be timezone-aware")
    if sr._parse_time(body["built_at"]) > now + timedelta(seconds=sr.CLOCK_SKEW_SECONDS):
        raise _refuse("RELEASE_NOT_YET_VALID")
    return raw


@dataclass(frozen=True)
class ReleaseCheck:
    """The outcome of one self-check. A record, not a credential: any caller can construct one.

    ``release_id``, ``manifest_hash`` and ``min_key_list_version`` are set only when ``integrity`` is
    ``verified``. ``reason`` is the stable refusal code when it is not.
    """

    integrity: str
    reason: str | None = None
    release_id: str | None = None
    manifest_hash: str | None = None
    min_key_list_version: int | None = None


def _check_files(base: Path, entries: list[dict[str, Any]]) -> None:
    listed = {entry["path"] for entry in entries}
    present = _walk(base)
    if present - listed:
        raise _refuse("RELEASE_FILE_UNLISTED")
    if listed - present:
        raise _refuse("RELEASE_FILE_MISSING")
    for entry in entries:
        sha256, size = _digest(base / entry["path"], entry["size"])
        if sha256 != entry["sha256"] or size != entry["size"]:
            raise _refuse("RELEASE_FILE_CHANGED", "content")
    if _walk(base) != listed:  # a file added or removed while the others were being hashed
        raise _refuse("RELEASE_TREE", "the release changed during the check")


def check_release(
    directory: str | os.PathLike[str], envelope: Mapping[str, Any] | None, *, root: RootKey,
    expected_release_id: str, now: datetime, allow_test_keys: bool = False,
) -> ReleaseCheck:
    """Verify the manifest, then the directory. Never raises for a failed check: it returns ``unverified``.

    ``root``, ``expected_release_id`` and ``directory`` must come from the worker's own configuration.
    """
    try:
        if envelope is None:
            raise _refuse("RELEASE_MANIFEST_MISSING")
        raw = verify_release_manifest(envelope, root=root, now=now, allow_test_keys=allow_test_keys)
        body = sr.parse_canonical(raw)
        if body["release_id"] != expected_release_id:
            raise _refuse("RELEASE_ID_MISMATCH")
        _check_files(_release_directory(directory), body["files"])
    except sr.ReceiptError as exc:
        return ReleaseCheck(UNVERIFIED, exc.code)
    except Exception:
        return ReleaseCheck(UNVERIFIED, "RELEASE_CHECK_ERROR")
    return ReleaseCheck(
        VERIFIED, None, body["release_id"], "sha256:" + hashlib.sha256(DOMAIN + raw).hexdigest(),
        body["min_key_list_version"],
    )

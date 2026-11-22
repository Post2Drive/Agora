"""Checked-in synthetic pilot fixtures: verified by hash BEFORE any governed store is opened.

A fixture is a directory under ``agora/pilot_fixtures/<fixture-id>/`` with ``manifest.json``
(fixture id/version, synthetic flag, sha256 of every file) plus ``units.csv``,
``schema.json`` and ``binding.json``. Loading is fail closed with stable codes.
Offline and local only; nothing here touches the simulation engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parent / "pilot_fixtures"
DEFAULT_FIXTURE = "synthetic-units-v1"
REQUIRED_FILES = ("units.csv", "schema.json", "binding.json")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
# Independent pin of each checked-in manifest's digest: editing manifest AND payload together
# (so the internal hashes still agree) is caught here. Update only via a reviewed PR.
PINNED_MANIFEST_DIGESTS = {
    "synthetic-units-v1": "sha256:1bc5020b9874a8065c787c6e6df756fad4d4c25ffd402b5e5149843be465f18f",
}


class FixtureError(Exception):
    """Stable-code fixture failure. ``code`` is one of the FX_* constants."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    version: str
    csv_bytes: bytes
    schema: dict[str, Any]
    binding: dict[str, Any]
    manifest_hash: str
    file_hashes: dict[str, str]


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def list_fixtures(root: Path | None = None) -> list[str]:
    base = root or FIXTURE_ROOT
    if not base.is_dir():
        return []
    def _plain_dir(p: Path) -> bool:
        try:
            st = os.lstat(p)
        except OSError:
            return False
        return (p.is_dir() and not p.is_symlink()
                and not (getattr(st, "st_file_attributes", 0) & 0x400))
    return sorted(p.name for p in base.iterdir() if _ID.match(p.name) and _plain_dir(p))


def load_fixture(fixture_id: str, root: Path | None = None) -> Fixture:
    base = root or FIXTURE_ROOT
    if not isinstance(fixture_id, str) or not _ID.match(fixture_id):
        raise FixtureError("FX_UNKNOWN_FIXTURE", f"valid ids: {', '.join(list_fixtures(base)) or 'none'}")
    d = base / fixture_id
    if os.path.lexists(d) and (d.is_symlink() or (getattr(os.lstat(d), "st_file_attributes", 0) & 0x400)):
        raise FixtureError("FX_UNSAFE_PATH", d.name)
    if fixture_id not in list_fixtures(base):
        raise FixtureError("FX_UNKNOWN_FIXTURE", f"valid ids: {', '.join(list_fixtures(base)) or 'none'}")
    for p in (d, d / "manifest.json", *(d / n for n in REQUIRED_FILES)):
        if p.is_symlink():
            raise FixtureError("FX_UNSAFE_PATH", p.name)
    try:
        man_bytes = (d / "manifest.json").read_bytes()
        man = json.loads(man_bytes)
    except (OSError, ValueError) as exc:
        raise FixtureError("FX_MANIFEST_INVALID", type(exc).__name__) from exc
    if (not isinstance(man, dict) or man.get("fixture_id") != fixture_id
            or man.get("synthetic_only") is not True or man.get("data_class") != "synthetic"
            or not isinstance(man.get("fixture_version"), str) or not isinstance(man.get("files"), dict)):
        raise FixtureError("FX_MANIFEST_INVALID", "required keys/synthetic flag")
    if not man["fixture_version"].strip():
        raise FixtureError("FX_MANIFEST_INVALID", "empty fixture version")
    if base.resolve() == FIXTURE_ROOT.resolve():
        pin = PINNED_MANIFEST_DIGESTS.get(fixture_id)
        if pin is None or _sha(man_bytes) != pin:
            raise FixtureError("FX_MANIFEST_HASH_MISMATCH", "manifest digest differs from pinned value")
    files = man["files"]
    if set(files) != set(REQUIRED_FILES) or not all(isinstance(v, str) and _HASH.match(v) for v in files.values()):
        raise FixtureError("FX_MANIFEST_INVALID", "file hash map")
    raw: dict[str, bytes] = {}
    for name in REQUIRED_FILES:
        try:
            raw[name] = (d / name).read_bytes()
        except OSError as exc:
            raise FixtureError("FX_FILE_MISSING", name) from exc
        if _sha(raw[name]) != files[name]:
            raise FixtureError("FX_HASH_MISMATCH", name)
    try:
        schema, binding = json.loads(raw["schema.json"]), json.loads(raw["binding.json"])
    except ValueError as exc:
        raise FixtureError("FX_FILE_INVALID", "json") from exc
    if not isinstance(schema, dict) or not isinstance(binding, dict) or binding.get("binding_version") in (None, "latest"):
        raise FixtureError("FX_FILE_INVALID", "schema/binding shape or unpinned binding")
    return Fixture(fixture_id, man["fixture_version"], raw["units.csv"], schema, binding,
                   _sha(man_bytes), dict(files))

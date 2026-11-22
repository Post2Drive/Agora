"""Backup, restore and tamper detection for a synthetic pilot project (M2 item 5).

``agora backup`` refuses to copy a project whose audit chain is not intact against its
anchor. ``agora restore`` refuses a backup whose files differ from its manifest, whose
chain/anchor no longer verify, or a non-empty target. Both fail closed with a stable code
and fixed plain-language text; neither writes anything on refusal (a partly written
destination is removed). Synthetic data only; the simulation engine is never imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .audit_anchor import verify_anchored_readonly

MANIFEST = "BACKUP_MANIFEST.json"
CHAIN_REL = "audit/chain.sqlite3"
ANCHOR_REL = "audit_anchor/anchor.jsonl"
DEFAULT_CHAIN_ID = "synthetic-pilot-chain"
_SQLITE = (".sqlite3", ".db")

_WORDS = {
    "SOURCE_NOT_FOUND": "Nothing was backed up: the project folder or its audit files were not found.",
    "SOURCE_NOT_INTACT": "Nothing was backed up: the audit chain is NOT INTACT against its anchor "
                         "(tampered, truncated or unanchored). Investigate before backing up.",
    "SOURCE_NOT_SYNTHETIC": "Nothing was backed up: the folder is not a verified synthetic pilot project "
                            "(its run record is missing or not marked synthetic).",
    "UNSAFE_PATH": "Refused: a symbolic link or unsafe path was found. Only plain files inside the folder are handled.",
    "SNAPSHOT_CHANGED": "Nothing was kept: the audit chain changed or failed verification while it was being copied. "
                        "Try again when no run is active.",
    "BACKUP_MANIFEST_INVALID": "Nothing was restored: the backup manifest is malformed or not marked synthetic.",
    "DEST_NOT_EMPTY": "Refused: the destination already exists and is not empty. Use a new folder.",
    "BACKUP_MANIFEST_MISSING": "Nothing was restored: the backup has no readable manifest.",
    "BACKUP_FILE_MISSING": "Nothing was restored: a file listed in the manifest is missing from the backup.",
    "BACKUP_FILE_MODIFIED": "Nothing was restored: a backup file does not match its recorded checksum "
                            "(it was changed after the backup).",
    "BACKUP_EXTRA_FILE": "Nothing was restored: the backup contains a file the manifest does not list.",
    "BACKUP_NOT_INTACT": "Nothing was restored: the backed-up audit chain is NOT INTACT against its anchor.",
    "RESTORED_NOT_INTACT": "The restored copy failed verification and was removed.",
}


class BackupBlocked(Exception):
    def __init__(self, code: str, status: str | None = None):
        super().__init__(code)
        self.code, self.status = code, status

    def message(self) -> str:
        extra = f" (verifier status: {self.status})" if self.status else ""
        return f"BLOCKED {self.code}: {_WORDS.get(self.code, self.code)}{extra}"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _files(root: Path) -> list[str]:
    """Plain files only. Any symbolic link (file or directory) is refused, never followed."""
    out: list[str] = []
    for p in root.rglob("*"):
        if p.is_symlink():
            raise BackupBlocked("UNSAFE_PATH")
        if p.is_file():
            out.append(p.relative_to(root).as_posix())
    return sorted(out)


def _safe_rel(rel: Any) -> bool:
    if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/") or ":" in rel:
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def _is_synthetic_project(project: Path) -> bool:
    try:
        rec = json.loads((project / "run_record.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(rec, dict) and rec.get("data_class") == "synthetic"


def _read_manifest(root: Path) -> tuple[dict[str, str], str]:
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BackupBlocked("BACKUP_MANIFEST_MISSING") from None
    if not isinstance(manifest, dict):
        raise BackupBlocked("BACKUP_MANIFEST_INVALID")
    files, chain_id = manifest.get("files"), manifest.get("chain_id")
    if (manifest.get("manifest_version") != 1 or manifest.get("synthetic_only") is not True
            or not isinstance(chain_id, str) or not chain_id
            or not isinstance(files, dict) or not files
            or any(not _safe_rel(k) or not isinstance(v, str) or len(v) != 64
                   or any(c not in "0123456789abcdef" for c in v) for k, v in files.items())):
        raise BackupBlocked("BACKUP_MANIFEST_INVALID")
    return files, chain_id


def _check_dest(dest: Path) -> None:
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise BackupBlocked("DEST_NOT_EMPTY")


def _copy_one(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in _SQLITE:  # consistent snapshot, not a raw byte copy of a live database
        s = sqlite3.connect(f"file:{src.resolve().as_posix()}?mode=ro", uri=True)
        d = sqlite3.connect(dst)
        try:
            s.backup(d)
        finally:
            d.close()
            s.close()
    else:
        shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, rels: list[str]) -> None:
    for rel in rels:
        _copy_one(src / rel, dst / rel)


def _cleanup(dest: Path, existed: bool) -> None:
    if existed:
        for child in dest.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    else:
        shutil.rmtree(dest, ignore_errors=True)


def backup(project: str | Path, dest: str | Path, *, chain_id: str = DEFAULT_CHAIN_ID) -> dict[str, Any]:
    project, dest = Path(project), Path(dest)
    if not (project / CHAIN_REL).is_file() or not (project / ANCHOR_REL).is_file():
        raise BackupBlocked("SOURCE_NOT_FOUND")
    if not _is_synthetic_project(project):
        raise BackupBlocked("SOURCE_NOT_SYNTHETIC")
    _files(project)  # refuses symlinks before anything is read or written
    verdict = verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, chain_id)
    if not verdict.get("valid"):
        raise BackupBlocked("SOURCE_NOT_INTACT", verdict.get("status"))
    _check_dest(dest)
    existed = dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        rels = _files(project)
        _copy_tree(project, dest / "data", rels)
        copied = _files(dest / "data")
        after = verify_anchored_readonly(dest / "data" / CHAIN_REL, dest / "data" / ANCHOR_REL, chain_id)
        if not after.get("valid") or after.get("status") != verdict["status"]:
            raise BackupBlocked("SNAPSHOT_CHANGED", after.get("status"))
        manifest = {"manifest_version": 1, "synthetic_only": True, "chain_id": chain_id,
                    "audit_status": verdict["status"], "files": {r: _sha(dest / "data" / r) for r in copied}}
        (dest / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    except BaseException:
        _cleanup(dest, existed)
        raise
    return {"files": len(copied), "audit_status": verdict["status"], "backup": str(dest)}


def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    root = Path(backup_dir)
    listed, chain_id = _read_manifest(root)
    data = root / "data"
    actual = _files(data) if data.is_dir() else []
    for rel in listed:
        if rel not in actual:
            raise BackupBlocked("BACKUP_FILE_MISSING")
    for rel in actual:
        if rel not in listed:
            raise BackupBlocked("BACKUP_EXTRA_FILE")
    for rel, digest in listed.items():
        if _sha(data / rel) != digest:
            raise BackupBlocked("BACKUP_FILE_MODIFIED")
    verdict = verify_anchored_readonly(data / CHAIN_REL, data / ANCHOR_REL, chain_id)
    if not verdict.get("valid"):
        raise BackupBlocked("BACKUP_NOT_INTACT", verdict.get("status"))
    return {"files": len(listed), "audit_status": verdict["status"], "chain_id": chain_id}


def restore(backup_dir: str | Path, target: str | Path) -> dict[str, Any]:
    backup_dir, target = Path(backup_dir), Path(target)
    info = verify_backup(backup_dir)
    _check_dest(target)
    existed = target.exists()
    target.mkdir(parents=True, exist_ok=True)
    try:
        data = backup_dir / "data"
        for rel in _files(data):
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data / rel, target / rel)  # byte copy keeps checksums identical
        _files(target)
        for rel, digest in _read_manifest(backup_dir)[0].items():
            if not (target / rel).is_file() or _sha(target / rel) != digest:
                raise BackupBlocked("RESTORED_NOT_INTACT", "file_hash_mismatch")
        verdict = verify_anchored_readonly(target / CHAIN_REL, target / ANCHOR_REL, info["chain_id"])
        if not verdict.get("valid"):
            raise BackupBlocked("RESTORED_NOT_INTACT", verdict.get("status"))
    except BaseException:
        _cleanup(target, existed)
        raise
    return {"files": info["files"], "audit_status": verdict["status"], "restored_to": str(target)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agora backup|restore",
                                 description="Back up, verify or restore a synthetic pilot project.")
    sub = ap.add_subparsers(dest="op", required=True)
    b = sub.add_parser("backup", help="copy a project after verifying its audit chain against its anchor")
    b.add_argument("--project", required=True)
    b.add_argument("--dest", required=True)
    b.add_argument("--chain-id", default=DEFAULT_CHAIN_ID)
    v = sub.add_parser("verify", help="check a backup against its manifest and its audit anchor")
    v.add_argument("--backup", required=True)
    r = sub.add_parser("restore", help="verify a backup, then restore it into a new empty folder")
    r.add_argument("--backup", required=True)
    r.add_argument("--target", required=True)
    if argv and argv[0] == "verify":
        argv = ["verify", *argv[1:]]
    args = ap.parse_args(argv)
    try:
        if args.op == "backup":
            out = backup(args.project, args.dest, chain_id=args.chain_id)
            print(f"OK: backed up {out['files']} files; audit chain INTACT ({out['audit_status']}).")
        elif args.op == "verify":
            out = verify_backup(args.backup)
            print(f"OK: backup is intact ({out['files']} files match; audit chain INTACT).")
        else:
            out = restore(args.backup, args.target)
            print(f"OK: restored {out['files']} files; audit chain INTACT ({out['audit_status']}).")
    except BackupBlocked as exc:
        print(exc.message(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

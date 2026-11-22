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
from contextlib import contextmanager
import os
import shutil
import stat
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
    "SOURCE_LOCK_FAILED": "Nothing was backed up: the project's writer lock could not be taken. Try again when no run is active.",
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


def _is_link(p: Path) -> bool:
    """Symlink or Windows reparse point on the path or ANY existing ancestor.

    Fails closed: an lstat error other than "does not exist" counts as unsafe.
    """
    if ".." in Path(p).parts:  # lexical '..' could erase a symlink component: refuse
        return True
    cur = Path(os.path.abspath(p))
    for q in (cur, *cur.parents):
        try:
            st = os.lstat(q)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        if stat.S_ISLNK(st.st_mode) or (getattr(st, "st_file_attributes", 0) & 0x400):
            return True
    return False


def _is_entry_link(p: Path) -> bool:
    """Final-component link check for entries already below a vetted root."""
    try:
        st = os.lstat(p)
    except OSError:
        return True
    return p.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _refuse_links(*paths: Path) -> None:
    for p in paths:
        if _is_link(p):
            raise BackupBlocked("UNSAFE_PATH")


def _files(root: Path) -> list[str]:
    """Plain files only. Any symbolic link (file or directory) is refused, never followed."""
    out: list[str] = []
    for p in root.rglob("*"):
        if _is_entry_link(p):
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
    return _read_manifest_full(root)[:2]


def _read_manifest_full(root: Path) -> tuple[dict[str, str], str, Any, Any]:
    """Read the manifest ONCE; returns (files, chain_id, chain_sequence, chain_head_hash)."""
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BackupBlocked("BACKUP_MANIFEST_MISSING") from None
    if not isinstance(manifest, dict):
        raise BackupBlocked("BACKUP_MANIFEST_INVALID")
    files, chain_id = manifest.get("files"), manifest.get("chain_id")
    version, seq, head = manifest.get("manifest_version"), manifest.get("chain_sequence"), manifest.get("chain_head_hash")
    if (type(version) is not int or version != 1 or manifest.get("synthetic_only") is not True
            or type(seq) is not int or seq < 0
            or not isinstance(head, str) or len(head) != 64
            or any(c not in "0123456789abcdef" for c in head)
            or not isinstance(chain_id, str) or not chain_id
            or not isinstance(files, dict) or not files
            or any(not _safe_rel(k) or not isinstance(v, str) or len(v) != 64
                   or any(c not in "0123456789abcdef" for c in v) for k, v in files.items())):
        raise BackupBlocked("BACKUP_MANIFEST_INVALID")
    return files, chain_id, seq, head


def _head(verdict: dict[str, Any]) -> tuple[Any, Any]:
    """Exact chain head (sequence, hash) from a verifier verdict; compared, never inferred."""
    return verdict.get("sequence"), verdict.get("head_hash")


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
    _refuse_links(project, dest)
    if not project.is_dir():
        raise BackupBlocked("SOURCE_NOT_FOUND")
    _files(project)  # refuses nested symlinks BEFORE any source file is read
    if not (project / CHAIN_REL).is_file() or not (project / ANCHOR_REL).is_file():
        raise BackupBlocked("SOURCE_NOT_FOUND")
    if not _is_synthetic_project(project):
        raise BackupBlocked("SOURCE_NOT_SYNTHETIC")
    verdict = verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, chain_id)
    if not verdict.get("valid"):
        raise BackupBlocked("SOURCE_NOT_INTACT", verdict.get("status"))
    _check_dest(dest)
    existed = dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with _source_writer_lock(project, chain_id):
            return _backup_locked(project, dest, chain_id)
    except BaseException:
        _cleanup(dest, existed)
        raise


@contextmanager
def _source_writer_lock(project: Path, chain_id: str):
    """Hold the audit-anchor lock (the one every anchored writer takes) for the whole snapshot."""
    from .audit_anchor import AnchorError, AnchorStore
    try:
        lock = AnchorStore(project / ANCHOR_REL, chain_id).lock()
        lock.__enter__()
    except (AnchorError, OSError):
        raise BackupBlocked("SOURCE_LOCK_FAILED") from None
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


def _backup_locked(project: Path, dest: Path, chain_id: str) -> dict[str, Any]:
    # Re-verified UNDER the writer lock: no anchored append can land between this check and the copy.
    verdict = verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, chain_id)
    if not verdict.get("valid"):
        raise BackupBlocked("SOURCE_NOT_INTACT", verdict.get("status"))
    rels = [r for r in _files(project) if r != ANCHOR_REL + ".lock"]  # the lock file is not data
    _copy_tree(project, dest / "data", rels)
    copied = _files(dest / "data")
    after = verify_anchored_readonly(dest / "data" / CHAIN_REL, dest / "data" / ANCHOR_REL, chain_id)
    if (not after.get("valid") or after.get("status") != verdict["status"]
            or _head(after) != _head(verdict)):
        raise BackupBlocked("SNAPSHOT_CHANGED", after.get("status"))
    seq, head_hash = _head(after)
    manifest = {"manifest_version": 1, "synthetic_only": True, "chain_id": chain_id,
                "audit_status": verdict["status"], "chain_sequence": seq, "chain_head_hash": head_hash,
                "files": {r: _sha(dest / "data" / r) for r in copied}}
    (dest / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"files": len(copied), "audit_status": verdict["status"], "backup": str(dest)}


def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    return _verify_snapshot(backup_dir)[0]


def _verify_snapshot(backup_dir: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate a backup against ONE read of its manifest; returns (info, listed-files)."""
    root = Path(backup_dir)
    _refuse_links(root, root / MANIFEST, root / "data")
    listed, chain_id, seq, head_hash = _read_manifest_full(root)
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
    if (seq, head_hash) != _head(verdict):
        raise BackupBlocked("BACKUP_NOT_INTACT", "manifest_head_mismatch")
    return {"files": len(listed), "audit_status": verdict["status"], "chain_id": chain_id}, listed


def restore(backup_dir: str | Path, target: str | Path) -> dict[str, Any]:
    backup_dir, target = Path(backup_dir), Path(target)
    _refuse_links(target)
    info, listed = _verify_snapshot(backup_dir)
    _check_dest(target)
    existed = target.exists()
    target.mkdir(parents=True, exist_ok=True)
    try:
        data = backup_dir / "data"
        for rel in _files(data):
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data / rel, target / rel)  # byte copy keeps checksums identical
        _files(target)
        for rel, digest in listed.items():
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

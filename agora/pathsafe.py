"""Shared path-safety check for audit stores: refuse symlinks / reparse points (fail closed).

A symlinked audit DB, anchor file, lock file or ancestor could redirect reads/writes outside the
intended project boundary. Any lstat error other than "does not exist" counts as unsafe.
Checked BEFORE resolving or opening; descriptor opens add O_NOFOLLOW where the OS supports it.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


class UnsafePathError(ValueError):
    """Path (or an existing ancestor) is a symlink/reparse point, or could not be vetted."""


def is_unsafe_path(p: str | os.PathLike[str]) -> bool:
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


def require_safe_path(p: str | os.PathLike[str]) -> Path:
    if is_unsafe_path(p):
        raise UnsafePathError("path is a symlink/reparse point, has one in its ancestry, or could not be vetted")
    return Path(p)


def open_flags(base: int) -> int:
    return base | getattr(os, "O_NOFOLLOW", 0)


_RACE_HOOK = None  # test seam: called after the bytes are read, before the identity re-check


def _ident(st: os.stat_result) -> tuple[int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def read_stable_bytes(p: str | os.PathLike[str]) -> bytes:
    """Read a regular file through ONE held descriptor and prove the path still names that file.

    Fails closed (UnsafePathError) if the path is a link/reparse point, is not a regular file, changed
    while being read (size/mtime/inode), or no longer resolves to the descriptor's file afterwards
    (concurrent path replacement). Nothing is ever re-opened by path after the check."""
    path = require_safe_path(p)
    try:
        fd = os.open(path, open_flags(os.O_RDONLY | getattr(os, "O_BINARY", 0)))
    except OSError:
        raise UnsafePathError("could not open path for a held-descriptor read") from None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise UnsafePathError("not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        if _RACE_HOOK is not None:
            _RACE_HOOK(path)
        after = os.fstat(fd)
        try:
            named = os.lstat(path)
        except OSError:
            raise UnsafePathError("path changed while reading") from None
        if stat.S_ISLNK(named.st_mode) or _ident(before) != _ident(after):
            raise UnsafePathError("file changed while reading")
        if (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino):
            raise UnsafePathError("path now names a different file")
        return b"".join(chunks)
    finally:
        os.close(fd)


def open_ro_snapshot(p: str | os.PathLike[str]):
    """Read-only in-memory SQLite connection over bytes read from a held descriptor (no path reopen)."""
    import sqlite3
    data = read_stable_bytes(p)
    if not hasattr(sqlite3.Connection, "deserialize"):  # Python < 3.11: refuse rather than reopen by path
        raise UnsafePathError("handle-based SQLite open needs Python 3.11+")
    db = sqlite3.connect(":memory:")
    try:
        db.deserialize(data)
        db.execute("PRAGMA query_only=ON")
    except Exception:
        db.close()
        raise
    return db

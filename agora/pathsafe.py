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

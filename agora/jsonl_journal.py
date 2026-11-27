"""Locking and appending for the append-only JSONL governance files.

Every writer of such a file takes ``writer_lock`` around its whole read-check-append, so two
threads or processes cannot both pass a check and then both write, and cannot overwrite each
other's line (append mode is not atomic across separate handles on Windows).
"""
from __future__ import annotations

import os
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator

from .pathsafe import open_flags, require_safe_path
from .validation.audit_log import _exclusive_lock


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


@contextmanager
def writer_lock(path: str | os.PathLike[str]) -> Iterator[None]:
    """Cross-process exclusive lock for one journal file. Not re-entrant."""
    with _exclusive_lock(_lock_path(require_safe_path(path))):
        yield


def reader_lock(path: str | os.PathLike[str]):
    """Lock a read against an in-progress append, without ever creating a file.

    A writer creates the lock file before it creates or extends the journal. So once the journal
    is seen to exist, a missing lock file means no locking writer has written it (it predates
    the lock), and it is read as it is.
    """
    path = Path(path)
    if path.exists() and _lock_path(path).exists():
        return writer_lock(path)
    return nullcontext()


def append_line(path: str | os.PathLike[str], line: str) -> None:
    """Append one record and flush it to disk. The caller must hold ``writer_lock(path)``.

    Refuses a file whose last record is unterminated: appending would merge two records.
    """
    path = require_safe_path(path)
    if "\n" in line:
        raise ValueError("A journal record must be a single line")
    encoded = (line + "\n").encode("utf-8")
    flags = open_flags(os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0))
    descriptor = os.open(path, flags, 0o666)
    try:
        size = os.fstat(descriptor).st_size
        if size:
            os.lseek(descriptor, size - 1, os.SEEK_SET)
            if os.read(descriptor, 1) != b"\n":
                raise ValueError(f"{path.name} has an incomplete final record; repair it before appending")
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while appending a journal record")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

"""RT12 leftovers: pilot workdir plain '..' refusal and ancestor lstat failure (fail closed). Synthetic only."""
import os
from pathlib import Path

import pytest

from agora import pilot


def test_plain_dotdot_without_symlink_is_refused(tmp_path):
    (tmp_path / "a").mkdir()
    p = tmp_path / "a" / ".." / "new-workdir"
    assert pilot._linked_component(p) is True
    with pytest.raises(pilot.UnsafeWorkdir):
        pilot.run_pilot(p)
    assert not (tmp_path / "new-workdir").exists()


def test_ancestor_lstat_error_fails_closed(tmp_path, monkeypatch):
    anc = tmp_path / "anc"
    anc.mkdir()
    target = anc / "new-workdir"
    real = os.lstat

    def fake(p, *a, **k):
        if Path(p) == anc:
            raise PermissionError("denied")
        return real(p, *a, **k)

    monkeypatch.setattr(os, "lstat", fake)
    assert pilot._linked_component(target) is True
    with pytest.raises(pilot.UnsafeWorkdir):
        pilot.run_pilot(target)
    monkeypatch.undo()
    assert not target.exists()


def test_clean_workdir_not_flagged(tmp_path):
    assert pilot._linked_component(tmp_path / "ok" / "new") is False

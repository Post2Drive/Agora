"""Track A red-team group 2: symlink / reparse-point attacks on audit stores. Synthetic data only.

Each attack must fail closed with no outside read or write; outside targets stay byte-identical.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from agora import audit_cli, pathsafe
from agora.audit_anchor import (AnchoredAuditChain, AnchorError, AnchorRequiredError, AnchorStore,
                                bootstrap_anchor, open_anchored_audit, verify_anchored_readonly)
from agora.audit_chain import AuditChainStore
from agora.pathsafe import UnsafePathError
from agora.validation import audit_log

CID = "rt-paths"
pytestmark = pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")


def _link(target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")


def _evt(i):
    return {"event_id": f"e{i}", "event_type": "t", "subject_id": "u", "operation": "import", "decision": "allow"}


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


@pytest.fixture
def real(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    chain = AuditChainStore(d / "audit.sqlite3")
    anchors = AnchorStore(d / "anchor.jsonl", CID)
    chain.append(_evt(0))
    bootstrap_anchor(chain, anchors, performed_by="maint")
    chain.close()
    return d


def test_clean_regular_paths_still_work(real):
    with open_anchored_audit(real / "audit.sqlite3", real / "anchor.jsonl", CID) as w:
        w.append(_evt(1))
    assert verify_anchored_readonly(real / "audit.sqlite3", real / "anchor.jsonl", CID)["valid"]


def test_symlinked_chain_db_refused(real, tmp_path):
    _link(real / "audit.sqlite3", tmp_path / "link.sqlite3")
    before = _sha(real / "audit.sqlite3")
    assert verify_anchored_readonly(tmp_path / "link.sqlite3", real / "anchor.jsonl", CID)["status"] == "store_unreadable"
    with pytest.raises(AnchorRequiredError):
        with open_anchored_audit(tmp_path / "link.sqlite3", real / "anchor.jsonl", CID):
            pass
    with pytest.raises(UnsafePathError):
        AuditChainStore(tmp_path / "link.sqlite3")
    with pytest.raises(audit_cli.AuditBlocked):
        audit_cli._ro(tmp_path / "link.sqlite3")
    assert _sha(real / "audit.sqlite3") == before


def test_symlinked_anchor_file_refused_read_and_append(real, tmp_path):
    _link(real / "anchor.jsonl", tmp_path / "anchor-link.jsonl")
    before = _sha(real / "anchor.jsonl")
    a = AnchorStore(tmp_path / "anchor-link.jsonl", CID)
    with pytest.raises(AnchorError):
        a.read()
    with pytest.raises(AnchorError):
        a.advance(5, "a" * 64)
    assert verify_anchored_readonly(real / "audit.sqlite3", tmp_path / "anchor-link.jsonl", CID)["status"] == "anchor_invalid"
    with pytest.raises(AnchorRequiredError):
        with open_anchored_audit(real / "audit.sqlite3", tmp_path / "anchor-link.jsonl", CID):
            pass
    assert _sha(real / "anchor.jsonl") == before


def test_dangling_anchor_link_not_followed_or_created(real, tmp_path):
    outside = tmp_path / "outside.jsonl"
    _link(outside, tmp_path / "dangling.jsonl")
    a = AnchorStore(tmp_path / "dangling.jsonl", CID)
    with pytest.raises(AnchorError):
        a._append(0, "a" * 64, require_history=False)
    assert not outside.exists()


def test_symlinked_lock_file_refused_no_outside_write(real, tmp_path):
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"sentinel")
    _link(outside, real / "anchor.jsonl.lock")
    a = AnchorStore(real / "anchor.jsonl", CID)
    with pytest.raises(AnchorError):
        a.lock()
    with pytest.raises(UnsafePathError):
        with audit_log._exclusive_lock(real / "anchor.jsonl.lock"):
            pass
    assert outside.read_bytes() == b"sentinel"


def test_symlinked_ancestor_refused_everywhere(real, tmp_path):
    _link(real, tmp_path / "ancestor")
    chain, anchor = tmp_path / "ancestor" / "audit.sqlite3", tmp_path / "ancestor" / "anchor.jsonl"
    before = (_sha(real / "audit.sqlite3"), _sha(real / "anchor.jsonl"))
    assert verify_anchored_readonly(chain, anchor, CID)["status"] == "store_unreadable"
    with pytest.raises(AnchorError):
        AnchorStore(anchor, CID).read()
    with pytest.raises(AnchorError):
        AnchorStore(anchor, CID).lock()
    with pytest.raises(UnsafePathError):
        AuditChainStore(chain)
    with pytest.raises(audit_cli.AuditBlocked):
        audit_cli._ro(chain)
    with pytest.raises(UnsafePathError):
        audit_log.append(tmp_path / "ancestor" / "log.jsonl", {})
    assert (_sha(real / "audit.sqlite3"), _sha(real / "anchor.jsonl")) == before
    assert not (real / "log.jsonl").exists()


def test_cli_verify_blocks_symlinked_store(real, tmp_path, capsys):
    _link(real / "audit.sqlite3", tmp_path / "l.sqlite3")
    rc = audit_cli.main(["verify", "--audit", str(tmp_path / "l.sqlite3"), "--anchor",
                         str(real / "anchor.jsonl"), "--chain-id", CID])
    assert rc == 2
    assert "STORE_UNREADABLE" in capsys.readouterr().err


def test_lstat_error_is_unsafe(real, monkeypatch):
    real_lstat = os.lstat

    def boom(p, *a, **k):
        if str(p).endswith("real"):
            raise PermissionError("denied")
        return real_lstat(p, *a, **k)
    monkeypatch.setattr(os, "lstat", boom)
    assert pathsafe.is_unsafe_path(real / "audit.sqlite3")
    assert verify_anchored_readonly(real / "audit.sqlite3", real / "anchor.jsonl", CID)["status"] == "store_unreadable"
    with pytest.raises(AnchorError):
        AnchorStore(real / "anchor.jsonl", CID).read()


def test_dotdot_refused():
    assert pathsafe.is_unsafe_path("a/../b")

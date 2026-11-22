"""Track A red-team, RT13: source snapshot race with a REAL concurrent anchored writer (no mocked verifier).

Synthetic data only. A legitimate anchored append is attempted while backup() holds the snapshot; the append
must wait for the writer lock, so the backup's manifest head equals the head verified before the copy, the
backup verifies, and the append lands afterwards (not lost, not mixed into the snapshot).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pytest

import agora.backup as mod
from agora.audit_anchor import AnchoredAuditChain, AnchorStore, verify_anchored_readonly
from agora.audit_chain import AuditChainStore
from agora.backup import ANCHOR_REL, CHAIN_REL, MANIFEST, backup, verify_backup
from agora.pilot import PROJECT_ID, run_pilot

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)
CID = "synthetic-pilot-chain"


@pytest.fixture()
def project(tmp_path):
    assert run_pilot(tmp_path / "run", now=NOW).status == "completed"
    return tmp_path / "run" / PROJECT_ID


def _head(project):
    v = verify_anchored_readonly(project / CHAIN_REL, project / ANCHOR_REL, CID)
    return v["sequence"], v["head_hash"]


def test_concurrent_anchored_writer_cannot_land_inside_the_snapshot(project, tmp_path, monkeypatch):
    before = _head(project)
    in_copy, release, done, result = threading.Event(), threading.Event(), threading.Event(), {}

    def writer():
        chain = AuditChainStore(project / CHAIN_REL)
        try:
            w = AnchoredAuditChain(chain, AnchorStore(project / ANCHOR_REL, CID))
            w.append({"event_id": "race-1", "event_type": "t", "subject_id": "u",
                      "operation": "import", "decision": "allow"})
            result["appended"] = True
        except BaseException as exc:  # pragma: no cover - surfaced by the assertion below
            result["error"] = repr(exc)
        finally:
            chain.close()
            done.set()

    real = mod._copy_one
    t = threading.Thread(target=writer)

    def gated(src, dst):
        real(src, dst)
        if dst.name == "chain.sqlite3" and not in_copy.is_set():
            in_copy.set()
            t.start()                      # the writer starts while the writer lock is held by backup
            assert not done.wait(1.5), "anchored append landed while the snapshot lock was held"
    monkeypatch.setattr(mod, "_copy_one", gated)

    backup(project, tmp_path / "bk")
    t.join(10)
    assert done.is_set() and result == {"appended": True}, result

    m = json.loads((tmp_path / "bk" / MANIFEST).read_text(encoding="utf-8"))
    assert (m["chain_sequence"], m["chain_head_hash"]) == before        # snapshot head = pre-append head
    assert verify_backup(tmp_path / "bk")["audit_status"] == "anchored_verified"
    after = _head(project)
    assert after[0] == before[0] + 1 and after != before                # the append landed after the snapshot

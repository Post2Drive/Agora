"""A source holding added events must start from a snapshot its named parent recorded. Mock backend, synthetic data.

The chain here is real: one executed result keeps a snapshot, and a second run starts from it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat

import pytest

from agora.decision_cell import Option, StudyState, run_result_stamps
from agora.decision_cell import executor as ex
from agora.sim.engine import Simulation
from tests.test_decision_cell_evidence import PAIR, choice, view
from tests.test_decision_cell_executor import built_source, go, left, read, recorded, refused, source  # noqa: F401
from tests.test_decision_cell_rerun import rerun
from tests.test_decision_cell_retractions import SCOPE
from tests.test_decision_cell_verification import audit, events  # noqa: F401

ENDED = StudyState("s1", 5)


def first(audit, source, out, result="p1", **kw):
    """A fork at round 2 whose branches keep a snapshot at round 3."""
    kw.setdefault("keep_snapshots", (3,))
    return go(audit, source, out, result=result, **kw)


def second(audit, source, out, result="c1", **kw):
    request = choice(Option.FORK_FROM_EVENT, view(audit).evidence_hash, event_round=3, budget_units=100_000)
    kw.setdefault("study", ENDED)
    return go(audit, source, out, result=result, request=request, **kw)


def no_run(audit, source, out, code="SOURCE_NOT_PARENT_OUTPUT", **kw):
    view(audit)
    before, there = len(events(audit)), left(out)
    refused(code, lambda: second(audit, source, out, **kw))
    assert len(events(audit)) == before and recorded(audit, "c1") is None and left(out) == there


def test_no_snapshot_is_kept_unless_asked_for(audit, source, tmp_path):
    done = go(audit, source, tmp_path / "out")
    for name, facts in done.manifest["branches"].items():
        assert "snapshots" not in facts and not (done.path / name / "snapshots").exists()


def test_a_kept_snapshot_is_in_the_manifest_and_changes_no_state(audit, source, tmp_path):
    kept = first(audit, source, tmp_path / "out")
    plain = go(audit, source, tmp_path / "out", result="plain")
    for name, facts in kept.manifest["branches"].items():
        meta = json.loads((kept.path / name / "snapshots" / "round-00003.json").read_text(encoding="utf-8"))
        assert facts["snapshots"] == {"3": meta["meta_digest"]}
        assert facts["final_state_digest"] == plain.manifest["branches"][name]["final_state_digest"]
    assert read(audit, tmp_path / "out", "p1").manifest == kept.manifest


@pytest.mark.parametrize("keep", [(2,), (5,), (-1,), (True,), (3.0,), [3], ("3",), None])
def test_a_snapshot_round_the_run_cannot_offer_is_refused(audit, source, tmp_path, keep):
    view(audit)
    before = len(events(audit))
    refused("INPUT_INVALID", lambda: go(audit, source, tmp_path / "out", keep_snapshots=keep))
    assert len(events(audit)) == before and recorded(audit) is None and left(tmp_path / "out") == []


def test_a_result_can_be_built_on_and_says_which_branch_it_came_from(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    child = second(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",))
    assert child.manifest["source_produced_by"] == [{"result_id": "p1", "branch": ex.WITH_EVENT}]
    assert child.manifest["held_statement_ids"]
    snapshot = parent.manifest["branches"][ex.WITH_EVENT]["snapshots"]["3"]
    assert {b["snapshot_meta_digest"] for b in child.manifest["branches"].values()} == {snapshot}
    assert child.basis.parent_result_ids == ("p1",)


def test_a_copy_of_the_branch_is_the_same_snapshot(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    copy = tmp_path / "moved"
    shutil.copytree(parent.path / ex.WITH_EVENT, copy)
    assert second(audit, copy, out, parent_result_ids=("p1",)).manifest["source_produced_by"]


def test_a_look_alike_source_with_the_same_words_is_refused(audit, source, tmp_path):
    """The words match the parent's item exactly, but the study was never the parent's output."""
    out = tmp_path / "out"
    parent = first(audit, source, out)
    conn = sqlite3.connect(parent.path / ex.WITH_EVENT / "agora.db")
    try:
        added = conn.execute("SELECT round, event FROM injected ORDER BY id").fetchall()
    finally:
        conn.close()
    forged = tmp_path / "forged"
    shutil.copytree(source, forged)
    shutil.rmtree(forged / "snapshots", onerror=lambda f, p, _: (os.chmod(p, stat.S_IWRITE), f(p)))
    for suffix in ("", "-wal", "-shm"):
        (forged / ("agora.db" + suffix)).unlink(missing_ok=True)
    sim = Simulation(forged, snapshot_rounds=(3,))
    try:
        sim.prepare()
        with sim.store.db:
            sim.store.db.executemany("INSERT INTO injected (round, event) VALUES (?, ?)",
                                     [(3, json.dumps({"round": 3, "text": json.loads(e)["text"], "type": "news"},
                                                     sort_keys=True, separators=(",", ":")))
                                      for _, e in added])
        sim.run()
    finally:
        sim.close()
    no_run(audit, forged, out, parent_result_ids=("p1",))


def test_the_producer_must_be_named(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    go(audit, source, out, result="other")  # same item, no kept snapshot: it produced no source
    no_run(audit, parent.path / ex.WITH_EVENT, out)
    no_run(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("other",))


def test_only_the_producers_are_named_as_the_source(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    go(audit, source, out, result="other")
    child = second(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("other", "p1"))
    assert {p["result_id"] for p in child.manifest["source_produced_by"]} == {"p1"}


def test_a_changed_parent_manifest_does_not_count(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    path = parent.path / ex.RESULT_FILE
    path.write_bytes(path.read_bytes() + b"\n")  # same content, other bytes than were recorded
    no_run(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",))


def test_a_missing_parent_manifest_does_not_count(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    (parent.path / ex.RESULT_FILE).unlink()
    no_run(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",))


def test_a_parents_output_kept_elsewhere_does_not_count(audit, source, tmp_path):
    parent = first(audit, source, tmp_path / "out")
    no_run(audit, parent.path / ex.WITH_EVENT, tmp_path / "other-out", parent_result_ids=("p1",))


def test_a_snapshot_the_parent_did_not_record_does_not_count(audit, source, tmp_path):
    """A snapshot taken on the finished branch afterwards is not one the parent recorded."""
    out = tmp_path / "out"
    parent = first(audit, source, out, keep_snapshots=())
    branch = parent.path / ex.WITH_EVENT
    sim = Simulation(branch)
    try:
        sim.prepare()
        sim.take_snapshot(5)
    finally:
        sim.close()
    facts = ex._source_facts(branch)
    assert facts[1] == 5
    found = ex._producers(out, ("p1",), 5, json.loads(
        (branch / "snapshots" / "round-00005.json").read_text(encoding="utf-8"))["meta_digest"],
        audit, "t1", "p1", "s1")
    assert found == ()


def test_the_digest_must_be_recorded_for_that_round(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    digest = parent.manifest["branches"][ex.WITH_EVENT]["snapshots"]["3"]
    ask = lambda r, d: ex._producers(out, ("p1", "p1"), r, d, audit, "t1", "p1", "s1")
    assert ask(3, digest) == (("p1", ex.WITH_EVENT),)
    assert ask(4, digest) == () and ask(3, hashlib.sha256(b"x").hexdigest()) == ()


def test_a_branch_started_from_another_snapshot_is_not_run(audit, source, tmp_path, monkeypatch):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    real = Simulation.fork_from

    def other_snapshot(src, round, dest, **kw):
        made = real(src, round, dest, **kw)
        if made.name == ex.WITHOUT_EVENT:  # same events, but the record says another snapshot
            facts = json.loads((made / "fork.json").read_text(encoding="utf-8"))
            facts["snapshot_meta_digest"] = "0" * 64
            (made / "fork.json").write_text(json.dumps(facts), encoding="utf-8")
        return made

    monkeypatch.setattr(Simulation, "fork_from", staticmethod(other_snapshot))
    refused("SOURCE_CHANGED", lambda: second(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",)))
    assert recorded(audit, "c1") is None and len(left(out)) == 1


def test_a_snapshot_swapped_after_the_trace_is_blocked(audit, source, tmp_path, monkeypatch):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    real, calls = ex._carried_events, []

    def swapped(*args):
        calls.append(args)
        carried, digest = real(*args)
        return carried, digest if len(calls) == 1 else "0" * 64

    monkeypatch.setattr(ex, "_carried_events", swapped)
    error = refused("GATE_BLOCKED", lambda: second(
        audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",)))
    assert error.gate.failures == ("snapshot_unavailable",) and recorded(audit, "c1") is None


def test_a_failed_run_removes_its_read_only_snapshots(audit, source, tmp_path, monkeypatch):
    """Windows refuses to delete a read-only file, so they are made writable before the removal."""
    seen = []
    real_rmtree = ex.shutil.rmtree

    def watching(path, *args, **kw):
        if str(path).endswith(".executing"):
            seen.extend(p.stat().st_mode & stat.S_IWUSR for p in path.rglob("round-*"))
        return real_rmtree(path, *args, **kw)

    def fail(**kw):
        raise RuntimeError("recording failed")

    monkeypatch.setattr(ex.shutil, "rmtree", watching)
    monkeypatch.setattr(ex, "record_run_result", fail)
    with pytest.raises(RuntimeError, match="recording failed"):
        first(audit, source, tmp_path / "out")
    assert seen and all(seen)
    assert left(tmp_path / "out") == []


def test_stamps_follow_the_chain(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = first(audit, source, out)
    child = second(audit, parent.path / ex.WITH_EVENT, out, parent_result_ids=("p1",))
    assert set(parent.basis.item_ids) <= set(child.basis.item_ids)
    assert child.stamps == run_result_stamps(result_id="c1", audit=audit, **SCOPE)


def test_a_rerun_may_keep_any_earlier_round_and_be_built_on(audit, source, tmp_path):
    out = tmp_path / "out"
    parent = rerun(audit, source, out, result="p1", keep_snapshots=(0, 3, 3))
    assert sorted(parent.manifest["branches"][ex.RERUN]["snapshots"]) == ["0", "3"]
    child = second(audit, parent.path / ex.RERUN, out, parent_result_ids=("p1",))
    assert child.manifest["source_produced_by"] == [{"result_id": "p1", "branch": ex.RERUN}]

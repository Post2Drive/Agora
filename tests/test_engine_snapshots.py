import os
import sqlite3

import pytest

from agora.llm import LLMConfig, make_backend
from agora.sim.engine import Simulation, SnapshotError, _state_digest
from conftest import make_project


def _complete(project, *, snapshot_rounds=()):
    sim = Simulation(project, snapshot_rounds=snapshot_rounds)
    try:
        sim.prepare()
        sim.run()
        return sim.state_digest()
    finally:
        sim.close()


def _small_project(tmp_path, name, **overrides):
    options = {
        "rounds": 8,
        "population": {"llm_agents": 2, "crowd_agents": 20},
        **overrides,
    }
    return make_project(tmp_path, name, **options)


def test_fork_from_committed_snapshot_replays_same_final_state(tmp_path):
    source = _small_project(tmp_path, "source")
    expected = _complete(source, snapshot_rounds=(3,))

    fork = tmp_path / "fork"
    Simulation.fork_from(source, 3, fork)
    actual = _complete(fork)

    assert actual == expected
    assert not (source / "fork.json").exists()


def test_event_fork_changes_branch_and_preserves_source(tmp_path):
    source = _small_project(tmp_path, "source")
    baseline = _complete(source, snapshot_rounds=(2,))
    source_before = sqlite3.connect(source / "agora.db")
    try:
        source_rows = source_before.execute("SELECT * FROM injected ORDER BY id").fetchall()
    finally:
        source_before.close()

    fork = tmp_path / "event-fork"
    Simulation.fork_from(
        source, 2, fork,
        events=[{"type": "news", "text": "A verified synthetic event", "round": 4}],
    )
    fork_db = sqlite3.connect(fork / "agora.db")
    try:
        inserted = fork_db.execute("SELECT round, event FROM injected").fetchall()
    finally:
        fork_db.close()
    assert len(inserted) == 1
    assert inserted[0][0] == 4

    fork_digest = _complete(fork)
    assert fork_digest != baseline

    source_after = sqlite3.connect(source / "agora.db")
    try:
        assert source_after.execute("SELECT * FROM injected ORDER BY id").fetchall() == source_rows
    finally:
        source_after.close()
    assert _complete(source) == baseline


def test_event_set_order_does_not_change_fork_state(tmp_path):
    source = _small_project(tmp_path, "source")
    _complete(source, snapshot_rounds=(2,))
    events = [
        {"type": "news", "text": "Synthetic event B", "round": 4},
        {"type": "news", "text": "Synthetic event A", "round": 4},
    ]
    first, second = tmp_path / "first-fork", tmp_path / "second-fork"
    Simulation.fork_from(source, 2, first, events=events)
    Simulation.fork_from(source, 2, second, events=list(reversed(events)))
    assert _complete(first) == _complete(second)


def test_corrupt_snapshot_is_refused_without_creating_destination(tmp_path):
    source = _small_project(tmp_path, "source")
    sim = Simulation(source, snapshot_rounds=(2,))
    try:
        sim.prepare()
        sim.run(rounds=3)
        snapshot_db = source / "snapshots" / "round-00002.db"
        os.chmod(snapshot_db, 0o644)
        conn = sqlite3.connect(snapshot_db)
        try:
            conn.execute("UPDATE agent_state SET stance = stance + 0.125 WHERE id = 0")
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(SnapshotError, match="integrity|state"):
            Simulation.fork_from(source, 2, tmp_path / "bad-fork")
    finally:
        sim.close()
    assert not (tmp_path / "bad-fork").exists()


def test_incomplete_snapshot_artifact_is_preserved(tmp_path):
    source = _small_project(tmp_path, "source")
    sim = Simulation(source)
    try:
        sim.prepare()
        sim.run(rounds=3)
        artifacts = source / "snapshots"
        artifacts.mkdir(exist_ok=True)
        partial = artifacts / "round-00002.db"
        partial.write_bytes(b"leave this partial artifact untouched")
        with pytest.raises(SnapshotError, match="refusing to remove or overwrite"):
            sim.take_snapshot(2)
        assert partial.read_bytes() == b"leave this partial artifact untouched"
    finally:
        sim.close()


def test_existing_snapshot_is_reverified_and_never_overwritten(tmp_path):
    source = _small_project(tmp_path, "source")
    sim = Simulation(source, snapshot_rounds=(2,))
    try:
        sim.prepare()
        sim.run(rounds=3)
        snapshot_db = source / "snapshots" / "round-00002.db"
        before = snapshot_db.read_bytes()
        os.chmod(snapshot_db, 0o644)
        conn = sqlite3.connect(snapshot_db)
        try:
            conn.execute("UPDATE agent_state SET stance = stance + 0.25 WHERE id = 0")
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(SnapshotError, match="integrity"):
            sim.take_snapshot(2)
        assert snapshot_db.read_bytes() != before
    finally:
        sim.close()


def test_live_backend_fork_fails_closed(tmp_path):
    source = _small_project(
        tmp_path, "live",
        llm={"backend": "ollama", "model": "test-model"},
    )
    sim = Simulation(source, snapshot_rounds=(2,))
    # Keep the saved run identity as Ollama, but use the deterministic mock backend
    # to create its fixture without requiring a model server in CI.
    sim.llm = make_backend(LLMConfig.from_dict({"backend": "mock"}))
    try:
        sim.prepare()
        sim.run()
    finally:
        sim.close()
    with pytest.raises(SnapshotError, match="deterministic replay"):
        Simulation.fork_from(source, 2, tmp_path / "live-fork")


def test_missing_model_cache_fails_closed(tmp_path):
    source = _small_project(tmp_path, "source")
    _complete(source, snapshot_rounds=(2,))
    cache = source / "snapshots" / "round-00002.cache.db"
    assert cache.exists()
    cache.unlink()
    with pytest.raises(SnapshotError, match="cache"):
        Simulation.fork_from(source, 2, tmp_path / "missing-cache-fork")


def test_changed_engine_identity_refuses_fork(tmp_path, monkeypatch):
    import agora.sim.engine as engine

    source = _small_project(tmp_path, "source")
    _complete(source, snapshot_rounds=(2,))
    monkeypatch.setattr(engine, "_engine_digest", lambda: "changed-engine")
    with pytest.raises(SnapshotError, match="engine implementation"):
        Simulation.fork_from(source, 2, tmp_path / "changed-engine-fork")


def test_stale_staging_path_is_never_deleted(tmp_path):
    source = _small_project(tmp_path, "source")
    _complete(source, snapshot_rounds=(2,))
    staging = tmp_path / "fork.forking"
    staging.mkdir()
    sentinel = staging / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(SnapshotError, match="staging path"):
        Simulation.fork_from(source, 2, tmp_path / "fork")
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not (tmp_path / "fork").exists()


def test_snapshot_state_digest_preserves_row_order():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE event_log (round INTEGER, kind TEXT, detail TEXT)")
        conn.executemany("INSERT INTO event_log VALUES (?, ?, ?)", [
            (1, "news", "first"), (2, "news", "second")
        ])
        before = _state_digest(conn)
        conn.execute("DELETE FROM event_log")
        conn.executemany("INSERT INTO event_log VALUES (?, ?, ?)", [
            (2, "news", "second"), (1, "news", "first")
        ])
        assert _state_digest(conn) != before
    finally:
        conn.close()


@pytest.mark.parametrize("rounds", [(-1,), (True,), (8,)])
def test_snapshot_rounds_must_be_validated(tmp_path, rounds):
    project = _small_project(tmp_path, "source")
    with pytest.raises(ValueError, match="snapshot_rounds"):
        Simulation(project, snapshot_rounds=rounds)

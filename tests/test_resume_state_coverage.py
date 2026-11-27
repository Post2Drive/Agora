"""What a resumed round reads: a stopped run must finish like an uninterrupted one, from digested state."""
import sqlite3

import pytest
import yaml

from agora.sim import engine
from agora.sim.engine import Simulation, _cache_digest, _state_digest
from test_choice import ELECTION, project as election_project


def _choice_project(tmp_path, name, **overrides):
    choice = {**yaml.safe_load(ELECTION.read_text(encoding="utf-8"))["choice"], "open_round": 4, "close_round": 9}
    return election_project(tmp_path, name, rounds=10, choice=choice,
                            population={"llm_agents": 6, "crowd_agents": 80}, **overrides)


def _run(project, *, stop_after=None, snapshot_rounds=()):
    """Run to the end. With ``stop_after``, close after that many rounds and resume in a new Simulation."""
    for rounds in ([stop_after, None] if stop_after else [None]):
        sim = Simulation(project, snapshot_rounds=snapshot_rounds)
        try:
            sim.prepare()
            sim.run(rounds)
            digest = sim.state_digest()
        finally:
            sim.close()
    return digest


@pytest.mark.parametrize("communication", ["platform", "both"])
def test_choice_run_resumes_to_the_uninterrupted_state(tmp_path, communication):
    extra = {} if communication == "platform" else {"communication": communication, "contact_budget": 2}
    expected = _run(_choice_project(tmp_path, "straight", **extra))
    for stop in (1, 5):
        assert _run(_choice_project(tmp_path, f"stop{stop}", **extra), stop_after=stop) == expected, stop


def test_choice_fork_replays_the_source_final_state(tmp_path):
    source = _choice_project(tmp_path, "source")
    expected = _run(source, snapshot_rounds=(3,))
    fork = tmp_path / "fork"
    Simulation.fork_from(source, 3, fork)
    assert _run(fork) == expected


def test_resumed_round_reads_nothing_the_state_digest_leaves_out(tmp_path):
    """SQLite reports every column the resume reads from the run database; none may be outside the digest."""
    project = _choice_project(tmp_path, "reads", communication="both", contact_budget=2)
    sim = Simulation(project)
    try:
        sim.prepare()
        sim.run(5)
    finally:
        sim.close()
    seen = set()
    sim = Simulation(project)

    def record(action, table, column, database, trigger):
        if action == sqlite3.SQLITE_READ:
            seen.add((table, column))
        return sqlite3.SQLITE_OK

    try:
        sim.store.db.set_authorizer(record)
        sim.prepare()
        sim.run(2)
        sim.store.db.set_authorizer(lambda *args: sqlite3.SQLITE_OK)
    finally:
        sim.close()
    assert ("agent_state", "prefs") in seen and any(t.startswith("society_") for t, _ in seen)
    assert not {t for t, _ in seen} & engine._NON_STATE_TABLES
    assert not {(t, c) for t, c in seen if c in engine._VOLATILE_COLUMNS.get(t, ())}


def test_state_digest_tells_a_blob_from_the_text_of_its_repr():
    def digest(value):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE TABLE posts (text TEXT)")
            conn.execute("INSERT INTO posts VALUES (?)", (value,))
            return _state_digest(conn)
        finally:
            conn.close()

    assert digest(b"hello") != digest("b'hello'")


def test_cache_digest_tells_a_blob_from_the_text_of_its_repr(tmp_path):
    def digest(name, value):
        path = tmp_path / name
        conn = sqlite3.connect(path)
        with conn:
            conn.execute("CREATE TABLE cache (k TEXT PRIMARY KEY, v TEXT)")
            conn.execute("INSERT INTO cache VALUES ('k', ?)", (value,))
        conn.close()
        return _cache_digest(path)

    assert digest("blob.db", b"hello") != digest("text.db", "b'hello'")

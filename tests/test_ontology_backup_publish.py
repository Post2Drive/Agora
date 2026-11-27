"""``OntologyObjectStore.backup`` publishes a new file only: it never replaces one or takes a live sidecar name."""

from __future__ import annotations

import os

import pytest

from agora.ontology import OntologyError, OntologyObjectStore
from test_ontology_store import _allow, _binding, _import, _pack
from test_ontology_anchored_backup import env  # noqa: F401  (fixture)


def _leftovers(data):
    return sorted(p.name for p in data.iterdir() if ".tmp" in p.name)


def _create_during_verification(monkeypatch, path, content):
    """Create ``path`` after backup's existence check and before it publishes."""
    real = OntologyObjectStore._verify_connection_integrity

    def verify(conn):
        result = real(conn)
        path.write_bytes(content)
        return result

    monkeypatch.setattr(OntologyObjectStore, "_verify_connection_integrity", staticmethod(verify))


def test_a_destination_created_while_backing_up_is_not_replaced(env, monkeypatch):
    data = env["project"] / "data"
    destination = data / "contested.sqlite3"
    _create_during_verification(monkeypatch, destination, b"someone else's file")
    with pytest.raises(OntologyError, match="backup failed"):
        env["store"].backup(destination, policy=_allow, audit=env["audit"])
    assert destination.read_bytes() == b"someone else's file"
    assert _leftovers(data) == []


def test_an_anchored_backup_that_loses_the_race_keeps_the_other_file(env, monkeypatch):
    data = env["project"] / "data"
    destination = data / "contested.sqlite3"
    _create_during_verification(monkeypatch, destination, b"someone else's file")
    with pytest.raises(OntologyError, match="backup failed"):
        env["store"].create_anchored_backup(destination, policy=_allow, audit=env["audit"])
    assert destination.read_bytes() == b"someone else's file"
    assert _leftovers(data) == []


def test_a_second_backup_to_the_same_path_does_not_share_the_first_ones_temporary(env, monkeypatch):
    data = env["project"] / "data"
    destination = data / "contested.sqlite3"
    real = OntologyObjectStore._verify_connection_integrity
    inner = []

    def verify(conn):
        result = real(conn)
        if not inner:
            inner.append(None)  # set first: the nested backup verifies too
            inner[0] = env["store"].backup(destination, policy=_allow, audit=env["audit"]).read_bytes()
        return result

    monkeypatch.setattr(OntologyObjectStore, "_verify_connection_integrity", staticmethod(verify))
    with pytest.raises(OntologyError, match="backup failed"):
        env["store"].backup(destination, policy=_allow, audit=env["audit"])
    assert destination.read_bytes() == inner[0]
    assert _leftovers(data) == []


@pytest.mark.parametrize("name", [
    "ontology.sqlite3-wal", "ontology.sqlite3-shm", "ontology.sqlite3-journal",
    "tabular.sqlite3-journal", "ontology.sqlite3-WAL",
])
def test_a_sqlite_sidecar_name_is_refused(env, name):
    destination = env["project"] / "data" / name
    assert not destination.exists()
    with pytest.raises(OntologyError, match="sidecar"):
        env["store"].backup(destination, policy=_allow, audit=env["audit"])
    assert not destination.exists()


def test_a_published_backup_is_one_file_with_no_temporary_left(env):
    data = env["project"] / "data"
    destination = env["store"].backup(data / "clean.sqlite3", policy=_allow, audit=env["audit"])
    assert destination.is_file()
    assert os.stat(destination).st_nlink == 1
    assert _leftovers(data) == []

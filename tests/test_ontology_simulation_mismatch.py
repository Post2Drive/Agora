"""A run records ``failed`` only for a positive finding; an outage records nothing and can be retried."""
import sqlite3
from contextlib import closing

import pytest

from agora import protection
from agora.ontology import OntologyError, actions, store as store_module
from agora.ontology.registry import ProposalMismatchError

from test_ontology_action_approvals import catalog, world  # noqa: F401
from test_ontology_preconditions import met  # noqa: F401
from test_ontology_simulation import _admitted, _break_source, _outcomes, _run


def _snapshot(w):
    return w.project / "data" / "tabular.sqlite3"


def _edit(path, sql, parameters=()):
    with closing(sqlite3.connect(path)) as conn:
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        changed = conn.execute(sql, parameters).rowcount
        conn.commit()
    assert changed > 0


def _assert_nothing_recorded(w, proposal, match):
    with pytest.raises(OntologyError, match=match) as caught:
        _run(w, proposal)
    assert not isinstance(caught.value, ProposalMismatchError)
    assert _outcomes(w) == []


def _assert_recorded_failed(w, proposal):
    assert _run(w, proposal)["status"] == "failed"
    (event,) = _outcomes(w)
    assert event["event_type"] == "ontology_action_simulation_failed"


def test_a_missing_snapshot_database_records_nothing_and_the_run_can_be_retried(world):
    proposal = _admitted(world)
    path = _snapshot(world)
    aside = path.with_name("aside.sqlite3")
    path.rename(aside)
    _assert_nothing_recorded(world, proposal, "snapshot database was not found")
    aside.rename(path)
    assert _run(world, proposal)["status"] == "succeeded"


def test_a_locked_snapshot_database_records_nothing(world):
    proposal = _admitted(world)
    with closing(sqlite3.connect(_snapshot(world), isolation_level=None)) as holder:
        holder.execute("PRAGMA locking_mode = EXCLUSIVE")
        holder.execute("BEGIN EXCLUSIVE")
        _assert_nothing_recorded(world, proposal, "snapshot metadata could not be read")
        holder.execute("ROLLBACK")
    assert _run(world, proposal)["status"] == "succeeded"


def test_an_unverifiable_ingest_record_records_nothing(world, monkeypatch):
    proposal = _admitted(world)

    def unavailable(*args, **kwargs):
        raise OntologyError("the import's ingest record could not be verified")

    with monkeypatch.context() as patch:
        # The test world has real ingest records; this turns on the check and makes it fail.
        patch.setattr(protection, "ANCHOR_REQUIRED", True)
        patch.setattr(store_module, "require_attested_rows", unavailable)
        _assert_nothing_recorded(world, proposal, "could not be verified")
    assert _run(world, proposal)["status"] == "succeeded"


def test_a_stored_row_that_is_no_longer_json_records_nothing(world):
    proposal = _admitted(world)
    _edit(_snapshot(world), "UPDATE import_rows SET payload_json='{'")
    _assert_nothing_recorded(world, proposal, "snapshot integrity check failed")


def test_a_row_altered_under_its_row_id_records_failed(world):
    proposal = _admitted(world)
    _break_source(world)
    _assert_recorded_failed(world, proposal)


def test_a_removed_row_records_failed(world):
    proposal = _admitted(world)
    _edit(_snapshot(world), "DELETE FROM import_rows WHERE row_id=?",
          (proposal.document["target"]["source_row_id"],))
    _assert_recorded_failed(world, proposal)


def test_a_reference_that_points_at_another_objects_row_records_failed(world):
    proposal = _admitted(world)
    d = proposal.document
    actor, target = d["actor"], d["target"]
    # Swap the two references' rows through a placeholder, because each row may be referenced once.
    for key, row_id in ((actor["record_key"], "placeholder"), (target["record_key"], actor["source_row_id"]),
                        (actor["record_key"], target["source_row_id"])):
        _edit(world.store.path, "UPDATE ontology_object_refs SET snapshot_row_id=? WHERE record_key=?",
              (row_id, key))
    _assert_recorded_failed(world, proposal)


def test_changed_provenance_on_the_stored_reference_records_failed(world):
    proposal = _admitted(world)
    _edit(world.store.path, "UPDATE ontology_object_refs SET file_sha256=?", ("0" * 64,))
    _assert_recorded_failed(world, proposal)


def test_a_precondition_that_no_longer_holds_records_failed(met, world, monkeypatch):
    proposal = _admitted(world)
    monkeypatch.setattr(actions.preconditions, "evaluate", lambda *args: False)
    _assert_recorded_failed(world, proposal)


def test_a_rebuild_that_differs_records_failed(world, monkeypatch):
    proposal = _admitted(world)
    compose = actions._compose

    def different(*args, **kwargs):
        document, resource_ids = compose(*args, **kwargs)
        return {**document, "declared_effects": []}, resource_ids

    monkeypatch.setattr(actions, "_compose", different)
    _assert_recorded_failed(world, proposal)


def test_a_manifest_that_does_not_verify_records_nothing(world):
    proposal = _admitted(world)
    # The stored manifest is replaced, so nothing in it can be used to judge the rows.
    _edit(_snapshot(world), "UPDATE imports SET manifest_json='{}'")
    _assert_nothing_recorded(world, proposal, "snapshot integrity check failed")

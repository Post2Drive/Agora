from __future__ import annotations

import json
import sqlite3

import pytest

from agora.store import Store


def _manifest():
    return {
        "scenario_hash": "sha256:scenario-1",
        "import_id": "import-1",
        "dataset_id": "customers",
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "binding_fingerprint": "sha256:binding",
        "ontology_pack_fingerprint": "sha256:ontology",
        "transformation_policy_fingerprint": None,
        "data_role": "context",
    }


def test_input_provenance_is_append_only_and_verified(tmp_path):
    store = Store(tmp_path / "agora.db")
    manifest = _manifest()
    envelope = store.set_input_provenance(manifest)
    assert envelope["manifest_hash"].startswith("sha256:")
    assert store.get_input_provenance()["provenance_status"] == "verified"
    assert store.set_input_provenance(manifest) == envelope
    changed = {**manifest, "import_id": "import-2"}
    with pytest.raises(RuntimeError, match="append-once"):
        store.set_input_provenance(changed)
    store.close()


def test_tampered_manifest_is_rejected(tmp_path):
    store = Store(tmp_path / "agora.db")
    store.set_input_provenance(_manifest())
    store.db.execute("DROP TRIGGER protect_input_provenance_update")
    store.db.execute("UPDATE meta SET value=? WHERE key='input_provenance'", (json.dumps({"scenario_hash": "sha256:scenario-1", "input_manifest": {"scenario_hash": "sha256:scenario-1"}, "manifest_hash": "sha256:wrong"}),))
    store.db.commit()
    with pytest.raises(RuntimeError, match="hash mismatch"):
        store.get_input_provenance()
    store.close()


def test_reserved_meta_key_cannot_bypass_append_only_store(tmp_path):
    store = Store(tmp_path / "agora.db")
    with pytest.raises(ValueError, match="reserved"):
        store.set_meta("input_provenance", {"scenario_hash": "sha256:other"})
    store.set_input_provenance(_manifest())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("UPDATE meta SET value=? WHERE key='input_provenance'", ("{}",))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM meta WHERE key='input_provenance'")
    store.close()


def test_resume_requires_exact_scenario_hash(tmp_path):
    store = Store(tmp_path / "agora.db")
    store.set_input_provenance(_manifest())
    store.assert_resume_input("sha256:scenario-1")
    with pytest.raises(RuntimeError, match="scenario hash changed"):
        store.assert_resume_input("sha256:scenario-2")
    store.close()


def test_legacy_runs_are_labelled_and_cannot_resume(tmp_path):
    store = Store(tmp_path / "agora.db")
    assert store.get_input_provenance()["provenance_status"] == "legacy_missing"
    with pytest.raises(RuntimeError, match="legacy"):
        store.assert_resume_input("sha256:scenario-1")
    store.close()

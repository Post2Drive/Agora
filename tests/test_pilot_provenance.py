"""M2: run record carries a verified input_provenance envelope (docs/RUN_PROVENANCE_SPEC.md)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agora.pilot import load_run_record, run_pilot
from agora.scenario_inputs import manifest_hash, recompute_scenario_hash


@pytest.fixture(scope="module")
def done(tmp_path_factory):
    wd = tmp_path_factory.mktemp("prov")
    res = run_pilot(wd)
    assert res.status == "completed", res
    return Path(res.project)


def _rec(project):
    return json.loads((project / "run_record.json").read_text(encoding="utf-8"))


def _load_with(project, tmp_path, mutate):
    d = tmp_path / "p"
    d.mkdir()
    rec = _rec(project)
    mutate(rec)
    (d / "run_record.json").write_text(json.dumps(rec), encoding="utf-8")
    return load_run_record(d, verify_seal=False)


def test_envelope_is_complete_and_verified(done):
    rec = load_run_record(done)
    ip = rec["input_provenance"]
    assert rec["provenance_status"] == "verified"
    assert ip["provenance_version"] == 1 and ip["import_id"] == rec["imported"]["import_id"] != "latest"
    assert ip["manifest_hash"] == manifest_hash(ip["input_manifest"])
    assert ip["scenario_hash"] == recompute_scenario_hash(ip["input_manifest"]) == ip["input_manifest"]["scenario_hash"]
    assert ip["data_role"] == "scenario_input" and ip["created_at"]
    assert ip["scenario_hash"] in (done / "report" / "pilot_report.md").read_text(encoding="utf-8")
    assert rec["engine_invoked"] is False and rec["validated_prediction_enabled"] is False


def test_no_raw_row_values_in_provenance(done):
    blob = json.dumps(_rec(done)["input_provenance"])
    for v in ("U001", "U002", "U003", "north", "south", "east"):
        assert v not in blob


def _set(path, value):
    def f(rec):
        d = rec["input_provenance"]
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
    return f


@pytest.mark.parametrize("name,mutate", [
    ("manifest_edited", _set(["input_manifest", "file_sha256"], "sha256:" + "0" * 64)),
    ("manifest_and_hash_edited_scenario_stale", lambda r: (r["input_provenance"]["input_manifest"].update(
        scenario_parameters={"x": 1}), r["input_provenance"].update(
        manifest_hash=manifest_hash(r["input_provenance"]["input_manifest"])))),
    ("scenario_hash_edited", _set(["scenario_hash"], "sha256:" + "1" * 64)),
    ("manifest_hash_edited", _set(["manifest_hash"], "sha256:" + "2" * 64)),
    ("import_id_latest", _set(["import_id"], "latest")),
    ("import_id_differs", _set(["import_id"], "other")),
    ("binding_fp_differs", _set(["binding_fingerprint"], "sha256:" + "3" * 64)),
    ("bad_version", _set(["provenance_version"], 2)),
    ("bad_role", _set(["data_role"], "sealed_holdout")),
    ("bad_created_at", _set(["created_at"], "yesterday")),
    ("extra_field", _set(["raw_rows"], [1])),
    ("null_on_completed", lambda r: r.update(input_provenance=None)),
])
def test_tampered_envelope_fails_closed(done, tmp_path, name, mutate):
    with pytest.raises(ValueError):
        _load_with(done, tmp_path, mutate)


def test_missing_envelope_is_labelled_legacy_not_inferred(done, tmp_path):
    rec = _load_with(done, tmp_path, lambda r: r.pop("input_provenance"))
    assert rec["provenance_status"] == "legacy_missing" and "input_provenance" not in rec


def test_stopped_run_before_bind_records_null_provenance(tmp_path):
    wd = tmp_path / "w"
    first = run_pilot(wd)
    assert first.status == "completed"
    # a second attempt in a non-empty dir is refused upstream; here check the stopped-run branch directly
    rec = _rec(Path(first.project))
    rec["status"], rec["input_provenance"] = "failed", None
    d = tmp_path / "q"
    d.mkdir()
    (d / "run_record.json").write_text(json.dumps(rec), encoding="utf-8")
    assert load_run_record(d)["provenance_status"] == "not_reached"


def test_provenance_is_append_once(done):
    from agora.pilot import _write_run_record
    with pytest.raises(FileExistsError):
        _write_run_record(done, status="completed", started=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc), steps=[], ctx={}, csv_path=done / "synthetic_units.csv", report=None)

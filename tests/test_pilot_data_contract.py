from pathlib import Path

import pytest
import yaml

from agora.ontology.binding import load_binding, materialize_instances, validate_binding
from agora.ontology.loader import load_domain_pack
from agora.scenario_inputs import build_scenario_input
from agora.tabular import TabularIngestError, ingest_csv, validate_downstream_policy


ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "pilot_contract"


def _schema():
    return yaml.safe_load((ROOT / "schema.yaml").read_text(encoding="utf-8"))


def _valid_import(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes((ROOT / "sample.csv").read_bytes())
    return ingest_csv(tmp_path, source, _schema(), data_role="context")


def test_clean_room_fixture_imports_binds_and_materializes(tmp_path):
    pack = load_domain_pack(ROOT / "pack.yaml")
    binding = load_binding(ROOT / "binding.yaml")
    imported = _valid_import(tmp_path)
    assert validate_binding(pack, imported["manifest"], binding) is binding
    instances = materialize_instances(binding, pack, tmp_path, imported["import_id"])
    built = build_scenario_input(binding, pack, tmp_path, imported["import_id"])
    assert len(instances) == 3
    assert built["validated_prediction_enabled"] is False
    assert built["manifest"]["scenario_hash"].startswith("sha256:")


@pytest.mark.parametrize("content,code", [
    ("record_id,category,score\nR001,roads,nope\n", "VALUE_INVALID"),
    ("record_id,category,score\nR001,roads\n", "ROW_WIDTH_INVALID"),
    ("record_id,category,score,unexpected\nR001,roads,4,x\n", "HEADER_INVALID"),
])
def test_malformed_rows_and_schema_drift_fail_closed(tmp_path, content, code):
    source = tmp_path / "bad.csv"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(TabularIngestError) as exc_info:
        ingest_csv(tmp_path, source, _schema(), data_role="context")
    assert exc_info.value.code == code
    assert exc_info.value.diagnostic["error_code"] == code
    assert "nope" not in str(exc_info.value)


def test_missing_policy_metadata_fails_closed_without_sensitive_diagnostics():
    schema = _schema()
    schema["columns"][0].update({"sensitivity": "personal"})
    schema["columns"][0].pop("purpose", None)
    schema["columns"][0].pop("retention", None)
    with pytest.raises(TabularIngestError) as exc_info:
        validate_downstream_policy(schema)
    assert exc_info.value.code == "PERSONAL_DATA_POLICY_REQUIRED"
    assert "R001" not in str(exc_info.value)

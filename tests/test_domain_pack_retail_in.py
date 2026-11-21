from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from agora.ontology import OntologyError
from agora.ontology.binding import load_binding, materialize_instances, validate_binding
from agora.ontology.loader import load_domain_pack
from agora.tabular import TabularIngestError, ingest_csv, validate_downstream_policy


ROOT = Path(__file__).parents[1] / "domain_packs" / "retail_in"


def _schema() -> dict:
    return yaml.safe_load((ROOT / "schema.yaml").read_text(encoding="utf-8"))


def _binding():
    return load_binding(ROOT / "binding.yaml")


def test_retail_pack_imports_and_materializes_typed_instances(tmp_path):
    pack = load_domain_pack(ROOT / "pack.yaml")
    source = tmp_path / "sample.csv"
    source.write_bytes((ROOT / "sample.csv").read_bytes())
    result = ingest_csv(tmp_path, source, _schema(), data_role="context")
    binding = _binding()

    assert len(source.read_text(encoding="utf-8").splitlines()) - 1 >= 30
    assert {item.data_type for item in pack.property_types} >= {"identifier", "integer", "decimal", "date", "boolean", "string"}
    assert validate_binding(pack, result["manifest"], binding) is binding
    instances = materialize_instances(binding, pack, tmp_path, result["import_id"])
    assert len(instances) == 30
    assert instances[0]["property_values"]["retail:Customer.age"] == 21
    assert instances[0]["property_values"]["retail:Customer.spend"] == "12.50"
    assert instances[0]["property_values"]["retail:Customer.opted_in"] is True
    assert instances[0]["property_sensitivity"]["retail:Customer.customer_id"] == "personal"
    assert instances[0]["import_id"] == result["import_id"]
    assert instances[0]["source_locator"]["file_sha256"]


def test_record_key_is_stable_when_one_row_changes(tmp_path):
    pack = load_domain_pack(ROOT / "pack.yaml")
    source = tmp_path / "sample.csv"
    source.write_bytes((ROOT / "sample.csv").read_bytes())
    first = ingest_csv(tmp_path, source, _schema(), data_role="context")
    updated = source.read_text(encoding="utf-8").replace("C001,21,12.50", "C001,21,999.99", 1)
    source.write_text(updated, encoding="utf-8")
    second = ingest_csv(tmp_path, source, _schema(), data_role="context")
    left = materialize_instances(_binding(), pack, tmp_path, first["import_id"])[0]
    right = materialize_instances(_binding(), pack, tmp_path, second["import_id"])[0]
    assert left["record_key"] == right["record_key"]
    assert left["row_id"] != right["row_id"]
    assert left["property_values"]["retail:Customer.spend"] != right["property_values"]["retail:Customer.spend"]


def test_personal_policy_and_sensitivity_downgrade_fail_closed(tmp_path):
    pack = load_domain_pack(ROOT / "pack.yaml")
    source = tmp_path / "sample.csv"
    source.write_bytes((ROOT / "sample.csv").read_bytes())
    result = ingest_csv(tmp_path, source, _schema(), data_role="context")

    bad_schema = copy.deepcopy(_schema())
    personal = next(column for column in bad_schema["columns"] if column["sensitivity"] == "personal")
    personal.pop("purpose")
    personal.pop("retention")
    with pytest.raises(TabularIngestError) as exc_info:
        validate_downstream_policy(bad_schema)
    assert exc_info.value.code == "PERSONAL_DATA_POLICY_REQUIRED"

    downgraded = _binding().as_dict()
    downgraded["property_sensitivity"]["retail:Customer.customer_id"] = "internal"
    with pytest.raises(OntologyError, match="downgrade"):
        validate_binding(pack, result["manifest"], downgraded)


def test_all_actions_are_simulation_guarded():
    pack = load_domain_pack(ROOT / "pack.yaml")
    assert pack.action_types
    for action in pack.action_types:
        assert action.simulated_only is True
        assert action.execution_mode == "simulation_only"
        assert action.external_writeback == "prohibited"

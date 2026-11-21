from pathlib import Path

import yaml

from agora.ontology.binding import load_binding, materialize_instances, validate_binding
from agora.ontology.loader import load_domain_pack
from agora.scenario_inputs import build_scenario_input
from agora.tabular import ingest_csv


ROOT = Path(__file__).parents[1] / "domain_packs" / "civic_in"


def _run_pack(root: Path, project: Path):
    pack = load_domain_pack(root / "pack.yaml")
    schema = yaml.safe_load((root / "schema.yaml").read_text(encoding="utf-8"))
    binding = load_binding(root / "binding.yaml")
    source = project / "source.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes((root / "sample.csv").read_bytes())
    imported = ingest_csv(project, source, schema, data_role="context")
    assert validate_binding(pack, imported["manifest"], binding) is binding
    instances = materialize_instances(binding, pack, project, imported["import_id"])
    built = build_scenario_input(binding, pack, project, imported["import_id"])
    return pack, imported, instances, built


def test_civic_pack_end_to_end_is_typed_linked_and_scenario_ready(tmp_path):
    pack, imported, instances, built = _run_pack(ROOT, tmp_path)
    schema = yaml.safe_load((ROOT / "schema.yaml").read_text(encoding="utf-8"))
    assert len(instances) == 8
    assert all(column["sensitivity"] not in {"personal", "sensitive"} for column in schema["columns"])
    assert {item.data_type for item in pack.property_types} >= {"identifier", "integer", "date", "boolean", "string"}
    assert len(pack.link_types) == 1
    assert pack.link_types[0].source_type_id == "civic:ServiceRequest"
    assert instances[0]["property_values"]["civic:ServiceRequest.priority"] == 2
    assert instances[0]["property_values"]["civic:ServiceRequest.resolved"] is True
    assert built["manifest"]["ontology_pack_id"] == "civic-in-pack"
    assert built["manifest"]["transformation_policy_fingerprint"] is None
    assert built["validated_prediction_enabled"] is False


def test_same_tabular_binding_scenario_engine_handles_retail_and_civic(tmp_path):
    retail_root = Path(__file__).parents[1] / "domain_packs" / "retail_in"
    civic_project = tmp_path / "civic"
    retail_project = tmp_path / "retail"
    _, _, civic_instances, civic_built = _run_pack(ROOT, civic_project)
    retail_pack = load_domain_pack(retail_root / "pack.yaml")
    retail_schema = yaml.safe_load((retail_root / "schema.yaml").read_text(encoding="utf-8"))
    retail_binding = load_binding(retail_root / "binding.yaml")
    retail_source = retail_project / "source.csv"
    retail_source.parent.mkdir(parents=True)
    retail_source.write_bytes((retail_root / "sample.csv").read_bytes())
    retail_import = ingest_csv(retail_project, retail_source, retail_schema, data_role="context")
    retail_built = build_scenario_input(
        retail_binding, retail_pack, retail_project, retail_import["import_id"],
        transformation_policy={
            "policy_id": "synthetic-test", "purpose": "synthetic validation", "retention": "one day",
            "reviewer": "reviewer-1", "approved_at": "2026-01-01T00:00:00Z", "audit_reference": "audit-1",
            "authorized_property_ids": ["retail:Customer.customer_id", "retail:Customer.email"],
        },
    )
    assert civic_instances and retail_built["instances"]
    assert civic_built["manifest"]["ontology_pack_id"] != retail_built["manifest"]["ontology_pack_id"]

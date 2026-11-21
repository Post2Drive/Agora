from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from agora.report.render import _provenance_markdown, validate_exploratory_output
from agora.report.writer import _report_provenance
from agora.store import Store


def _manifest():
    return {
        "scenario_hash": "sha256:scenario-123",
        "import_id": "import-123",
        "dataset_id": "customers",
        "schema_id": "customers-v1",
        "schema_version": "1.0.0",
        "schema_fingerprint": "sha256:schema",
        "binding_id": "customers.binding",
        "binding_version": "1.0.0",
        "binding_fingerprint": "sha256:binding",
        "ontology_pack_id": "commerce",
        "ontology_schema_version": "1.0.0",
        "ontology_pack_fingerprint": "sha256:ontology",
        "transformation_policy_fingerprint": "sha256:policy",
        "data_role": "context",
        "source_registry_id": "source-123",
        "file_sha256": "sha256:file",
        "redactions": [
            {"property_id": "commerce:Customer.email", "row_id": "snapshot-row-secret"}
        ],
    }


def test_legacy_report_provenance_is_explicit_and_not_resumable(tmp_path):
    # A pre-contract run database has only its original meta table. Opening it
    # through the report path must not add the current Store schema or triggers.
    db_path = tmp_path / "agora.db"
    connection = sqlite3.connect(str(db_path))
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    connection.commit()
    connection.close()
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    provenance = _report_provenance(tmp_path)

    after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert after == before
    assert provenance["provenance_status"] == "legacy_missing"
    assert provenance["legacy"] is True
    assert provenance["mode"] == "exploratory"
    assert provenance["simulated"] is True
    lines = _provenance_markdown(provenance)
    rendered = "\\n".join(lines)
    assert "LEGACY RUN" in rendered
    assert "not eligible for scenario-input resume" in rendered


def test_verified_report_provenance_contains_required_fields_only(tmp_path):
    store = Store(tmp_path / "agora.db")
    store.set_input_provenance(_manifest())
    store.close()

    provenance = _report_provenance(tmp_path)
    assert provenance["provenance_status"] == "verified"
    assert provenance["legacy"] is False
    assert provenance["scenario_hash"] == "sha256:scenario-123"
    assert provenance["import_id"] == "import-123"
    assert provenance["binding_fingerprint"] == "sha256:binding"
    assert provenance["ontology_pack_fingerprint"] == "sha256:ontology"
    assert provenance["redaction_summary"] == {
        "redacted_values": 1,
        "property_ids": ["commerce:Customer.email"],
    }
    assert "snapshot-row-secret" not in json.dumps(provenance)
    rendered = "\\n".join(_provenance_markdown(provenance))
    for expected in ("RUN PROVENANCE — VERIFIED", "sha256:scenario-123",
                     "import-123", "sha256:binding", "sha256:ontology",
                     "exploratory simulation"):
        assert expected in rendered


@pytest.mark.parametrize("claim", [
    "This is a forecast.",
    "This is validated demand.",
    "This is a sales prediction.",
])
def test_exploratory_report_rejects_forbidden_claim_language(claim):
    with pytest.raises(ValueError, match="prohibited claim language"):
        validate_exploratory_output({
            "mode": "exploratory",
            "title": "A simulation report",
            "sections": [{"title": "Summary", "text": claim}],
            "quotes": {},
        })


def test_exploratory_report_accepts_simulation_language():
    validate_exploratory_output({
        "mode": "exploratory",
        "title": "A simulation report",
        "sections": [{"title": "Summary", "text": "Simulated preferences are exploratory."}],
        "quotes": {},
    })

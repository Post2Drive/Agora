import csv
import json

from agora.cli import main


def files(tmp_path, *, personal=True):
    source = tmp_path / "people.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "email"])
        writer.writerow(["1", "SECRET-CLI-VALUE"])
    schema = {
        "schema_id": "people-v1", "schema_version": "1.0.0", "dataset_name": "people",
        "columns": [
            {"name": "id", "type": "string", "nullable": False, "primary_key": True, "sensitivity": "internal"},
            {"name": "email", "type": "string", "nullable": False, "sensitivity": "personal" if personal else "internal",
             **({"purpose": "support", "retention": "30 days"} if personal else {})},
        ],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    return source, schema_path


def test_data_cli_import_is_idempotent_and_catalogues_snapshot(tmp_path, capsys):
    source, schema = files(tmp_path)
    args = ["data", "import-csv", "--project", str(tmp_path / "project"), "--csv", str(source), "--schema", str(schema), "--role", "context"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert "imported:" in first
    assert main(args) == 0
    assert "already imported:" in capsys.readouterr().out
    assert main(["data", "snapshots", "--project", str(tmp_path / "project")]) == 0
    assert "people" in capsys.readouterr().out


def test_data_cli_never_prints_values_and_requires_role(tmp_path, capsys):
    source, schema = files(tmp_path, personal=False)
    project = tmp_path / "project"
    args = ["data", "import-csv", "--project", str(project), "--csv", str(source), "--schema", str(schema), "--role", "context"]
    assert main(args) == 0
    output = capsys.readouterr().out
    assert "SECRET-CLI-VALUE" not in output
    assert main(["data", "show", "--project", str(project), "--import-id", output.split(":", 1)[1].strip()]) == 0
    assert "SECRET-CLI-VALUE" not in capsys.readouterr().out

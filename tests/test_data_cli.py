import csv
import json
import pytest

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


def test_data_cli_requires_role_and_lists_choices(capsys):
    with pytest.raises(SystemExit):
        main(["data", "import-csv", "--project", "p", "--csv", "f", "--schema", "s"])
    assert "context" in capsys.readouterr().err


def test_data_cli_reports_bad_schema_without_traceback(tmp_path, capsys):
    source, _schema = files(tmp_path, personal=False)
    rc = main(["data", "import-csv", "--project", str(tmp_path / "project"), "--csv", str(source), "--schema", str(tmp_path / "missing.yaml"), "--role", "context"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "SCHEMA_FILE_INVALID" in err
    assert "Traceback" not in err


def test_data_cli_rejected_outputs_safe_diagnostics(tmp_path, capsys):
    source, schema = files(tmp_path, personal=False)
    source.write_text("id,email\n1,SECRET-CLI-VALUE\n1,SECRET-CLI-VALUE-2\n", encoding="utf-8")
    project = tmp_path / "project"
    rc = main(["data", "import-csv", "--project", str(project), "--csv", str(source), "--schema", str(schema), "--role", "context"])
    assert rc == 2
    import_id = next(project.glob("data/tabular.sqlite3"))
    import sqlite3
    conn = sqlite3.connect(import_id)
    failed_id = conn.execute("SELECT import_id FROM imports WHERE status='failed'").fetchone()[0]
    conn.close()
    assert main(["data", "rejected", "--project", str(project), "--import-id", failed_id]) == 0
    output = capsys.readouterr().out
    assert "SECRET-CLI-VALUE" not in output
    assert "PRIMARY_KEY_DUPLICATE" in output

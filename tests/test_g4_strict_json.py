"""Strict JSON input tests for the G4.1 governance hardening."""
import json
import pytest

from agora.validation.json_io import strict_json_load, strict_json_loads


def test_strict_json_accepts_unambiguous_json():
    assert strict_json_loads('{"outer":{"value":3},"items":[true,null]}') == {
        "outer": {"value": 3}, "items": [True, None]
    }


@pytest.mark.parametrize("payload", [
    '{"key":1,"key":2}',
    '{"outer":{"key":1,"key":2}}',
])
def test_strict_json_rejects_duplicate_keys_at_any_depth(payload):
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        strict_json_loads(payload)


@pytest.mark.parametrize("payload", ['{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}'])
def test_strict_json_rejects_nonstandard_numeric_constants(payload):
    with pytest.raises(ValueError, match="invalid JSON constant"):
        strict_json_loads(payload)


def test_strict_json_file_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_bytes(b'{"value":"\xff"}')
    with pytest.raises(ValueError, match="not valid UTF-8"):
        strict_json_load(path)


def test_validation_cli_rejects_duplicate_evidence_before_registry_write(tmp_path):
    from agora.cli import main

    project = tmp_path / "project"
    project.mkdir()
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"registry_id":"first","registry_id":"second"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        main(["validation", "add", str(project), str(evidence)])
    assert not (project / "validation" / "registry.jsonl").exists()




def test_registry_jsonl_rejects_duplicate_keys(tmp_path):
    from agora.validation.registry import list_entries

    path = tmp_path / "registry.jsonl"
    path.write_text('{"registry_id":"one","registry_id":"two"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid registry JSON line 1.*duplicate JSON object key"):
        list_entries(path)

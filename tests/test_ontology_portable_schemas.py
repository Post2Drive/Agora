"""The published ontology schemas, conformance vectors and parsers agree."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from agora.ontology import OntologyError, parse_domain_pack, schema
from agora.ontology.binding import load_binding
from agora.ontology.loader import load_domain_pack

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "agora" / "ontology" / "schemas"
VECTORS = ROOT / "conformance" / "ontology"
PARSERS = {"domain-pack": parse_domain_pack, "data-binding": load_binding}


def _vectors(name: str) -> dict:
    return json.loads((VECTORS / f"{name}.json").read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    published = json.loads((PUBLISHED / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(published)
    return Draft202012Validator(published)


def _cases(key: str) -> list:
    return [
        pytest.param(name, case, id=f"{name}-{case['id']}")
        for name in PARSERS for case in _vectors(name)[key]
    ]


def _accepted(call) -> bool:
    """True or False only; any error other than OntologyError fails the test."""
    try:
        call()
    except OntologyError:
        return False
    return True


@pytest.mark.parametrize("name", sorted(PARSERS))
def test_published_schema_matches_the_generator(name):
    assert (PUBLISHED / f"{name}.schema.json").read_text(encoding="utf-8") == schema.render(name)


@pytest.mark.parametrize("name,case", _cases("cases"))
def test_conformance_vector(name, case):
    assert _validator(name).is_valid(case["document"]) is case["schema_valid"]
    assert _accepted(lambda: PARSERS[name](case["document"])) is case["agora_valid"]


@pytest.mark.parametrize("name", sorted(PARSERS))
def test_vectors_never_expect_agora_to_accept_what_the_schema_refuses(name):
    cases = _vectors(name)["cases"]
    assert len({case["id"] for case in cases}) == len(cases)
    assert not [case["id"] for case in cases if case["agora_valid"] and not case["schema_valid"]]


@pytest.mark.parametrize("name,case", _cases("json_text_cases"))
def test_json_file_with_repeated_keys_is_refused(name, case, tmp_path):
    source = tmp_path / "document.json"
    source.write_text(case["text"], encoding="utf-8")
    load = load_domain_pack if name == "domain-pack" else load_binding
    assert _accepted(lambda: load(source)) is case["agora_valid"]


def test_non_string_binding_field_name_is_refused_cleanly():
    # Not expressible in JSON, but YAML allows it.
    document = dict(_vectors("data-binding")["cases"][0]["document"])
    document[1] = "x"
    with pytest.raises(OntologyError, match="field names must be strings"):
        load_binding(document)


@pytest.mark.parametrize("domain", sorted(p.name for p in (ROOT / "domain_packs").iterdir() if p.is_dir()))
def test_repository_domain_examples_share_one_contract(domain):
    folder = ROOT / "domain_packs" / domain
    raw_pack = yaml.safe_load((folder / "pack.yaml").read_text(encoding="utf-8"))
    raw_binding = yaml.safe_load((folder / "binding.yaml").read_text(encoding="utf-8"))
    _validator("domain-pack").validate(raw_pack)
    _validator("data-binding").validate(raw_binding)
    pack = parse_domain_pack(raw_pack)
    binding = load_binding(raw_binding)
    assert binding.object_type_id in {item.type_id for item in pack.object_types}
    # The normalized form Agora serializes also satisfies the published schema.
    _validator("data-binding").validate({**binding.as_dict(), "fingerprint": binding.fingerprint})


def test_schema_command_prints_the_published_text(capsys):
    assert schema.main(["domain-pack"]) == 0
    assert capsys.readouterr().out == schema.render("domain-pack")
    assert schema.main(["nope"]) == 2


def test_schema_and_parser_trim_the_same_characters():
    """Every code point agrees on whether it is blank text."""
    pattern = Draft202012Validator({**schema.domain_pack_schema()["$defs"]["text"]})
    differing = [
        hex(code) for code in range(0x110000)
        if chr(code).isspace() and pattern.is_valid(chr(code))
        or code < 0x3100 and not chr(code).isspace() and not pattern.is_valid(chr(code))
    ]
    assert differing == []

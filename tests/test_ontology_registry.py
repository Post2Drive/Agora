import json

import pytest

from agora.ontology import (
    OntologyError,
    OntologyRegistry,
    load_domain_pack,
    parse_domain_pack,
    stable_record_key,
)


def make_pack(domain="civic", *, version="1.0.0"):
    participant = f"{domain}:Participant"
    name_property = f"{participant}.name"
    proposal = f"{domain}:Proposal"
    return {
        "pack_id": f"{domain}-pack",
        "schema_version": "1.0.0",
        "object_types": [
            {
                "type_id": participant,
                "version": version,
                "name": "Participant",
                "description": "A domain participant.",
                "properties": [name_property],
                "identity_strategy": "primary_key",
                "source_binding": {
                    "source_registry_id": f"source:{domain}:participants",
                    "locator": "table=participants",
                },
            },
            {
                "type_id": proposal,
                "version": "1.0.0",
                "name": "Proposal",
                "description": "A domain proposal.",
                "properties": [],
                "identity_strategy": "record_key",
            },
        ],
        "property_types": [
            {
                "property_id": name_property,
                "version": "1.0.0",
                "name": "name",
                "data_type": "string",
                "required": True,
                "nullable": False,
                "sensitivity": "personal",
                "source_registry_id": f"source:{domain}:participants",
                "locator": "column=name",
            }
        ],
        "link_types": [
            {
                "link_type_id": f"{domain}:Participant.supports",
                "version": "1.0.0",
                "name": "supports",
                "source_type_id": participant,
                "target_type_id": proposal,
                "predicate": "supports",
                "cardinality": "many_to_many",
            }
        ],
        "action_types": [
            {
                "action_type_id": f"{domain}:RecordSupport",
                "version": "1.0.0",
                "name": "RecordSupport",
                "actor_type_id": participant,
                "target_type_id": proposal,
                "inputs": [],
                "preconditions": [],
                "effects": ["record_simulated_support"],
                "permissions": ["execute_simulation"],
                "simulated_only": True,
                "execution_mode": "simulation_only",
                "external_writeback": "prohibited",
            }
        ],
    }


def test_commerce_and_civic_packs_validate_against_the_same_contract():
    commerce = parse_domain_pack(make_pack("commerce"))
    civic = parse_domain_pack(make_pack("civic"))

    assert commerce.pack_id == "commerce-pack"
    assert civic.pack_id == "civic-pack"
    assert commerce.fingerprint != civic.fingerprint
    assert commerce.object_types[0].source_binding.source_registry_id == "source:commerce:participants"
    assert civic.property_types[0].sensitivity == "personal"


@pytest.mark.parametrize(
    "field,value",
    [
        ("simulated_only", False),
        ("simulated_only", None),
        ("execution_mode", "live"),
        ("external_writeback", "allowed"),
        ("external_writeback", None),
    ],
)
def test_action_type_rejects_missing_or_unsafe_execution_guards(field, value):
    data = make_pack()
    action = data["action_types"][0]
    if value is None:
        action.pop(field)
    else:
        action[field] = value

    with pytest.raises(OntologyError):
        parse_domain_pack(data)


def test_property_sensitivity_is_required_and_has_no_default():
    data = make_pack()
    del data["property_types"][0]["sensitivity"]

    with pytest.raises(OntologyError, match="sensitivity"):
        parse_domain_pack(data)


def test_property_sensitivity_rejects_unknown_classification():
    data = make_pack()
    data["property_types"][0]["sensitivity"] = "secret"

    with pytest.raises(OntologyError, match="sensitivity"):
        parse_domain_pack(data)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(unexpected=True),
        lambda data: data["object_types"][0].update(unexpected=True),
        lambda data: data["property_types"][0].update(unexpected=True),
        lambda data: data["link_types"][0].update(unexpected=True),
        lambda data: data["action_types"][0].update(unexpected=True),
    ],
)
def test_unknown_pack_and_type_keys_fail_closed(mutate):
    data = make_pack()
    mutate(data)

    with pytest.raises(OntologyError, match="unknown"):
        parse_domain_pack(data)


def test_source_binding_requires_both_registry_id_and_locator():
    data = make_pack()
    data["object_types"][0]["source_binding"].pop("locator")

    with pytest.raises(OntologyError, match="source_binding"):
        parse_domain_pack(data)


def test_action_and_link_references_must_resolve():
    data = make_pack()
    data["link_types"][0]["target_type_id"] = "missing:Type"

    with pytest.raises(OntologyError, match="target_type_id"):
        parse_domain_pack(data)


def test_registry_detects_type_version_changes_and_fingerprints_content():
    v1 = OntologyRegistry.from_pack(parse_domain_pack(make_pack(version="1.0.0")))
    v2 = OntologyRegistry.from_pack(parse_domain_pack(make_pack(version="2.0.0")))

    changes = v2.changes_from(v1)
    object_changes = [change for change in changes if change.type_id == "civic:Participant"]
    assert len(object_changes) == 1
    assert (object_changes[0].old_version, object_changes[0].new_version) == ("1.0.0", "2.0.0")
    assert v1.fingerprint != v2.fingerprint


def test_registry_rejects_same_id_and_version_with_changed_definition():
    original = OntologyRegistry.from_pack(parse_domain_pack(make_pack()))
    changed_data = make_pack()
    changed_data["object_types"][0]["description"] = "Changed without a version bump."
    changed = parse_domain_pack(changed_data)

    with pytest.raises(OntologyError, match="same type ID and version"):
        original.register(changed)


def test_stable_record_key_is_versioned_and_scoped_to_dataset_identity():
    first = stable_record_key("dataset:patients", "P-0042")
    again = stable_record_key("dataset:patients", "P-0042")

    assert first == again
    assert first.startswith("agora-record-v1:")
    assert first != stable_record_key("dataset:patients", "P-0043")
    assert first != stable_record_key("dataset:participants", "P-0042")
    with pytest.raises(OntologyError):
        stable_record_key("dataset:patients", None)


def test_load_domain_pack_supports_yaml_and_json(tmp_path):
    data = make_pack("commerce")
    yaml_path = tmp_path / "civic.yaml"
    yaml_path.write_text(
        "pack_id: civic-pack\nschema_version: '1.0.0'\nobject_types: []\nproperty_types: []\nlink_types: []\naction_types: []\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "commerce.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    assert load_domain_pack(yaml_path).pack_id == "civic-pack"
    assert load_domain_pack(json_path).pack_id == "commerce-pack"


def test_property_data_type_must_be_supported():
    data = make_pack()
    data["property_types"][0]["data_type"] = "arbitrary_blob"

    with pytest.raises(OntologyError, match="data_type"):
        parse_domain_pack(data)


def test_yaml_loader_rejects_duplicate_mapping_keys(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "pack_id: first\npack_id: second\nschema_version: '1.0.0'\nobject_types: []\nproperty_types: []\nlink_types: []\naction_types: []\n",
        encoding="utf-8",
    )

    with pytest.raises(OntologyError, match="duplicate key"):
        load_domain_pack(path)

def test_load_domain_pack_rejects_unsupported_extension_and_invalid_payload(tmp_path):
    path = tmp_path / "pack.txt"
    path.write_text("pack_id: no", encoding="utf-8")

    with pytest.raises(OntologyError):
        load_domain_pack(path)
    with pytest.raises(OntologyError):
        parse_domain_pack([])
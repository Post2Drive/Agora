"""O0 close-out: rules the pack and binding code must enforce. All data is synthetic."""

from dataclasses import asdict

import pytest

from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore, parse_domain_pack
from agora.ontology.binding import (
    declared_sensitivity, iter_source_object_refs, load_binding, materialize_instances,
    materialize_source_object, validate_binding,
)
from agora.scenario_inputs import ScenarioInputError, build_scenario_input
from agora.tabular import ingest_csv

EMAIL = "o0:Customer.email"
TIER = "o0:Customer.tier"
CID = "o0:Customer.id"


def _pack_data(*, email="sensitive", tier=None):
    def prop(pid, data_type, sensitivity, **extra):
        return {"property_id": pid, "version": "1.0.0", "name": pid.rsplit(".", 1)[1],
                "data_type": data_type, "required": True, "nullable": False,
                "sensitivity": sensitivity, **extra}

    tier_rules = dict(tier or {})
    tier_type = tier_rules.pop("data_type", "string")

    return {
        "pack_id": "o0-pack", "schema_version": "1.0.0",
        "object_types": [{
            "type_id": "o0:Customer", "version": "1.0.0", "name": "Customer",
            "description": "Synthetic", "properties": [CID, EMAIL, TIER],
            "identity_strategy": "record_key",
        }],
        "property_types": [
            prop(CID, "identifier", "public"),
            prop(EMAIL, "string", email),
            prop(TIER, tier_type, "public", **tier_rules),
        ],
        "link_types": [], "action_types": [],
    }


def _pack(**kwargs):
    return parse_domain_pack(_pack_data(**kwargs))


def _binding_data(**overrides):
    return {
        "binding_id": "o0.customer", "binding_version": "1.0.0",
        "object_type_id": "o0:Customer", "object_type_version": "1.0.0",
        "dataset_id": "o0_customers", "schema_id": "o0-customers", "schema_version": "1.0.0",
        "column_map": {"customer_id": CID, "email": EMAIL, "tier": TIER},
        "identity": {"strategy": "record_key", "primary_key_column": "customer_id"},
        **overrides,
    }


def _binding(**overrides):
    return load_binding(_binding_data(**overrides))


def _import(project, rows, *, tier_nullable=False, tier_type="string", primary=True):
    def column(name, kind="string", **extra):
        return {"name": name, "type": kind, "nullable": False, "sensitivity": "public", **extra}

    tier = column("tier", tier_type, nullable=tier_nullable)
    if tier_nullable:
        tier["empty_as_null"] = True
    if tier_type == "decimal":
        tier.update(precision=6, scale=2)
    schema = {
        "schema_id": "o0-customers", "schema_version": "1.0.0", "dataset_name": "o0_customers",
        "columns": [column("customer_id", **({"primary_key": True} if primary else {})),
                    column("email"), tier],
    }
    project.mkdir(parents=True, exist_ok=True)
    source = project / "customers.csv"
    source.write_text("customer_id,email,tier\n" + "".join(f"{r}\n" for r in rows), encoding="utf-8")
    return ingest_csv(project, source, schema, data_role="context")["import_id"]


class _Recorder:
    def __init__(self):
        self.resources = []

    def __call__(self, operation, resource):
        self.resources.append(dict(resource))
        return {"decision": "allow", "reason": "policy_allow", "subject_id": "o0-operator",
                "policy_version": "o0-test", "resource_ids": list(resource["resource_ids"])}


def _read_all(binding, pack, project, import_id, policy):
    return materialize_instances(binding, pack, project, import_id, policy=policy)


def _read_refs(binding, pack, project, import_id, policy):
    return list(iter_source_object_refs(binding, pack, project, import_id, policy=policy))


def _read_scenario(binding, pack, project, import_id, policy):
    return build_scenario_input(binding, pack, project, import_id, policy=policy,
                                transformation_policy=None)


@pytest.mark.parametrize("reader", [_read_all, _read_refs, _read_scenario])
def test_downgraded_override_is_refused_before_the_policy_is_asked(tmp_path, reader):
    # Public columns, sensitive property, "public" override: the policy used to
    # be asked about public data while the returned labels said sensitive.
    import_id = _import(tmp_path, ["C1,a@example.test,gold"])
    policy = _Recorder()

    with pytest.raises((OntologyError, ScenarioInputError), match="downgrade"):
        reader(_binding(property_sensitivity={EMAIL: "public"}), _pack(), tmp_path, import_id, policy)

    assert policy.resources == []


@pytest.mark.parametrize("override, expected", [
    ({}, "sensitive"),
    ({TIER: "personal"}, "sensitive"),
    ({EMAIL: "sensitive"}, "sensitive"),
])
def test_policy_is_asked_about_the_strictest_declared_classification(tmp_path, override, expected):
    import_id = _import(tmp_path, ["C1,a@example.test,gold"])
    policy = _Recorder()
    binding = _binding(property_sensitivity=override)

    instances = materialize_instances(binding, _pack(), tmp_path, import_id, policy=policy)

    assert policy.resources[0]["source_sensitivity"] == expected
    assert max(instances[0]["property_sensitivity"].values()) == expected


def test_override_may_raise_a_classification():
    pack = _pack(email="internal")
    assert declared_sensitivity(pack, _binding()) == "internal"
    assert declared_sensitivity(pack, _binding(property_sensitivity={TIER: "sensitive"})) == "sensitive"


def test_validate_binding_refuses_a_downgrade_below_the_property():
    manifest = {
        "import_id": "i1", "dataset_id": "o0_customers", "schema_id": "o0-customers",
        "schema_version": "1.0.0", "schema_fingerprint": "x",
        "column_sensitivity": {"customer_id": "public", "email": "public", "tier": "public"},
        "column_types": {"customer_id": "string", "email": "string", "tier": "string"},
    }
    validate_binding(_pack(), manifest, _binding())
    with pytest.raises(OntologyError, match="downgrade below the declared"):
        validate_binding(_pack(), manifest, _binding(property_sensitivity={EMAIL: "internal"}))


@pytest.mark.parametrize("key", ["o0:Customer.emial", "email"])
def test_override_for_an_unmapped_property_is_refused_not_ignored(key):
    with pytest.raises(OntologyError, match="only name mapped property IDs"):
        _binding(property_sensitivity={key: "sensitive"})


def test_assigned_identity_object_type_cannot_be_bound_by_record_key():
    data = _pack_data()
    data["object_types"][0]["identity_strategy"] = "assigned"
    with pytest.raises(OntologyError, match="identity strategy"):
        declared_sensitivity(parse_domain_pack(data), _binding())


def test_object_type_must_not_repeat_a_property():
    data = _pack_data()
    data["object_types"][0]["properties"] = [CID, EMAIL, TIER, f" {TIER}"]
    with pytest.raises(OntologyError, match="must not repeat"):
        parse_domain_pack(data)


@pytest.mark.parametrize("pack_data, binding_data, message", [
    (_pack_data(), _binding_data(property_sensitivity={EMAIL: "public"}), "downgrade"),
    ({**_pack_data(), "object_types": [{**_pack_data()["object_types"][0],
                                        "identity_strategy": "assigned"}]},
     _binding_data(), "identity strategy"),
])
def test_store_does_not_register_a_binding_that_breaks_the_pack(tmp_path, pack_data, binding_data, message):
    (tmp_path / "data").mkdir()
    audit = AuditChainStore(tmp_path / "data" / "audit_chain.sqlite3")
    try:
        store = OntologyObjectStore(tmp_path)
        policy = _Recorder()
        pack_fp = store.register_pack(parse_domain_pack(pack_data), policy=policy, audit=audit)
        binding = load_binding(binding_data)
        with pytest.raises(OntologyError, match=message):
            store.register_binding(pack_fp, binding, policy=policy, audit=audit)
        with pytest.raises(OntologyError, match="unknown ontology binding"):
            store.get_binding(pack_fp, binding.fingerprint, policy=policy, audit=audit)
    finally:
        audit.close()


def _value_readers(binding, pack, project, import_id):
    yield "all", lambda: materialize_instances(binding, pack, project, import_id)
    yield "refs", lambda: list(iter_source_object_refs(binding, pack, project, import_id))


def _one_row(project, import_id, binding, pack):
    """Read the single source row through the exact-row path."""
    from agora.identity import stable_record_key
    from agora.tabular import read_snapshot

    row = read_snapshot(project, import_id)[0]
    return materialize_source_object(
        binding, pack, project, import_id, row["row_id"],
        stable_record_key("o0_customers", "C1"),
    )


@pytest.mark.parametrize("tier_rule, row, nullable, message", [
    (None, "C1,a@example.test,", True, "null value for non-nullable"),
    ({"allowed_values": ["gold", "silver"]}, "C1,a@example.test,secret-tier", False, "not allowed by property"),
])
@pytest.mark.parametrize("path", ["all", "refs", "row"])
def test_source_values_must_satisfy_the_pack(tmp_path, tier_rule, row, nullable, message, path):
    import_id = _import(tmp_path, [row], tier_nullable=nullable)
    pack, binding = _pack(tier=tier_rule), _binding()
    readers = dict(_value_readers(binding, pack, tmp_path, import_id))
    readers["row"] = lambda: _one_row(tmp_path, import_id, binding, pack)

    with pytest.raises(OntologyError, match=message) as caught:
        readers[path]()

    assert "secret-tier" not in str(caught.value)
    assert "example.test" not in str(caught.value)


def test_nullable_property_and_listed_values_are_accepted(tmp_path):
    import_id = _import(tmp_path, ["C1,a@example.test,", "C2,b@example.test,gold"], tier_nullable=True)
    pack = _pack(tier={"nullable": True, "allowed_values": ["gold"]})
    instances = materialize_instances(_binding(), pack, tmp_path, import_id)
    assert sorted(str(i["property_values"][TIER]) for i in instances) == ["None", "gold"]


@pytest.mark.parametrize("allowed, accepted", [([1.5], True), (["1.500"], True), ([2], False),
                                               ([True, None, "not-a-number"], False)])
def test_decimal_allowed_values_compare_numerically(tmp_path, allowed, accepted):
    import_id = _import(tmp_path, ["C1,a@example.test,1.50"], tier_type="decimal")
    pack = _pack(tier={"data_type": "decimal", "allowed_values": allowed})
    if accepted:
        assert materialize_instances(_binding(), pack, tmp_path, import_id)
    else:
        with pytest.raises(OntologyError, match="not allowed by property"):
            materialize_instances(_binding(), pack, tmp_path, import_id)


def test_allowed_values_do_not_treat_true_as_one(tmp_path):
    import_id = _import(tmp_path, ["C1,a@example.test,1"], tier_type="integer")
    pack = _pack(tier={"data_type": "integer", "allowed_values": [True]})
    with pytest.raises(OntologyError, match="not allowed by property"):
        materialize_instances(_binding(), pack, tmp_path, import_id)


def test_binding_key_column_must_be_unique_in_the_snapshot(tmp_path):
    # The import declares no primary key, so ingestion cannot catch the repeat.
    import_id = _import(tmp_path, ["C1,a@example.test,gold", "C1,b@example.test,gold"], primary=False)
    with pytest.raises(OntologyError, match="not unique"):
        materialize_instances(_binding(), _pack(), tmp_path, import_id)

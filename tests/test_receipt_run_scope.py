"""A signed receipt for a governed run binds the rows, mapping and scenario that will run (test keys only)."""
import copy
from datetime import datetime, timezone

import pytest

from agora import scenario as scenario_mod
from agora.principal import Principal, Assurance, SyntheticFixtureAdapter
from agora.scenario_inputs import manifest_hash
from agora.security import receipt_gate as rg
from agora.security import run_scope as rs
from agora.security import signed_receipt as sr
from conftest import make_project
from test_engine_governed_input import ACT, MAPPING, make_package
from test_receipt_gate import BASE, NOW, SEED, consumed, envelope_for, opened, paths, refused, settings, write

__all__ = ["paths"]  # fixture re-used from the gate tests


def principal(**changes):
    fixture = {"subject_id": "op-1", "tenant_id": BASE["tenant"], "project_ids": ["proj"], "roles": ["operator"],
               "assurance": "HIGH", "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc), **changes}
    return SyntheticFixtureAdapter({"who": fixture}).issue("who")


@pytest.fixture
def base(tmp_path):
    return scenario_mod.load(make_project(tmp_path) / "scenario.yaml")


@pytest.fixture
def gate(tmp_path, paths):
    with opened(write(tmp_path, settings(paths))) as value:
        value.refresh_key_list(envelope_for())
        yield value


def inputs(base, **changes):
    return {"package": make_package(), "mapping": copy.deepcopy(MAPPING), "base_scenario": base,
            "project_id": "proj", **changes}


def signed(run, nonce=0, **changes):
    """What a policy service would sign for this run."""
    document = {**BASE, **run.request, "nonce": f"{nonce:032x}", **changes}
    return sr.make_receipt(SEED, document)


def described(base, **changes):
    return rs.describe_run(subject_id="op-1", **inputs(base, **changes))


def admit(gate, envelope, base, who=None, **changes):
    return rs.admit_governed_run(gate, envelope, principal=who or principal(), **inputs(base, **changes))


def test_a_receipt_for_the_described_run_is_admitted_once(gate, base):
    run = described(base)
    envelope = signed(run)
    admitted = admit(gate, envelope, base)
    assert dict(admitted.run.request) == dict(run.request) and dict(admitted.run.action) == dict(run.action)
    assert admitted.admission.receipt["manifest_hash"] == run.request["manifest_hash"]
    assert admitted.admission.receipt["purpose"] == "governed_run.v1"
    assert [s.name for s in admitted.run.scenario.segments] == sorted(MAPPING["personas"])
    refused("REPLAY", admit, gate, envelope, base)
    assert consumed(gate) == 1


def _row_value(package, mapping, scenario):
    package["instances"][0]["property_values"][ACT] += 0.05


def _extra_row(package, mapping, scenario):
    package["instances"].append(copy.deepcopy(package["instances"][0]))


def _persona(package, mapping, scenario):
    mapping["personas"]["senior_residents"] = "A different persona"


def _seed(package, mapping, scenario):
    scenario.seed += 1


def _rounds(package, mapping, scenario):
    scenario.rounds += 1


def _context(package, mapping, scenario):
    scenario.context += " changed"


def _model(package, mapping, scenario):
    scenario.llm = {**scenario.llm, "model": "another-model"}


def _raw_only(package, mapping, scenario):
    scenario.raw = {**scenario.raw, "topic": "changed in the loaded document only"}


def _overwritten_segments(package, mapping, scenario):
    scenario.segments = scenario.segments[:1]  # replaced by projection, but the starting document differs


def _unmapped_value(package, mapping, scenario):
    package["instances"][0]["property_values"]["x:unmapped"] = "added"


def _same_mean(package, mapping, scenario):  # the projected segments stay identical
    one, two = package["instances"][0]["property_values"], package["instances"][1]["property_values"]
    one[ACT], two[ACT] = two[ACT], one[ACT]


def _origin_label(package, mapping, scenario):
    package["synthetic_demo"] = False


def _row_id(package, mapping, scenario):
    package["instances"][0]["row_id"] = "renamed"


@pytest.mark.parametrize("change", [_unmapped_value, _same_mean, _origin_label, _row_id, _row_value, _extra_row, _persona, _seed, _rounds, _context, _model, _raw_only,
                                    _overwritten_segments])
def test_changing_what_would_run_after_signing_is_refused(gate, base, change):
    envelope = signed(described(base))
    package, mapping, scenario = make_package(), copy.deepcopy(MAPPING), copy.deepcopy(base)
    change(package, mapping, scenario)
    # the two package hashes do not move, which is why they are not enough
    assert package["scenario_hash"] == make_package()["scenario_hash"]
    assert manifest_hash(package["manifest"]) == manifest_hash(make_package()["manifest"])
    refused("SCOPE_MISMATCH", admit, gate, envelope, scenario, package=package, mapping=mapping)
    assert consumed(gate) == 0


def test_a_mapping_change_that_projects_the_same_scenario_is_refused(gate, base):
    package = make_package()
    for row in package["instances"]:
        row["property_values"]["x:twin"] = row["property_values"][ACT]
        row["property_sensitivity"]["x:twin"] = "public"
    mapping = copy.deepcopy(MAPPING)
    mapping["numeric"]["openness"] = "x:twin"
    one, two = described(base, package=package), described(base, package=package, mapping=mapping)
    assert one.action["effective_scenario_sha256"] == two.action["effective_scenario_sha256"]
    refused("SCOPE_MISMATCH", admit, gate, signed(one), base, package=package, mapping=mapping)
    assert consumed(gate) == 0


def test_the_action_names_exactly_what_is_bound(base):
    assert sorted(described(base).action) == ["base_scenario_sha256", "domain", "effective_scenario_sha256",
                                              "mapping_sha256", "package_sha256"]


def test_a_receipt_over_the_plain_input_manifest_hash_is_refused(gate, base):
    run = described(base)
    envelope = signed(run, manifest_hash=manifest_hash(make_package()["manifest"]))
    refused("SCOPE_MISMATCH", admit, gate, envelope, base)
    assert consumed(gate) == 0


@pytest.mark.parametrize("field,value", [("purpose", "pilot.v1"), ("subject", "op-2"), ("project", "other"),
                                         ("import_id", "import-2"), ("binding_id", "binding-2"),
                                         ("tenant", "tenant-b"), ("release_id", "release-other")])
def test_a_receipt_for_another_scope_is_refused(gate, base, field, value):
    envelope = signed(described(base), **{field: value})
    with pytest.raises(sr.ReceiptError):
        admit(gate, envelope, base)
    assert consumed(gate) == 0


def test_the_subject_comes_from_the_principal(gate, base):
    envelope = signed(described(base))  # signed for op-1
    refused("SCOPE_MISMATCH", admit, gate, envelope, base, principal(subject_id="op-2"))
    assert consumed(gate) == 0


@pytest.mark.parametrize("changes", [
    {"tenant_id": "tenant-b"}, {"project_ids": ["other"]}, {"roles": ["reader"]}, {"assurance": "LOW"},
    {"expires_at": NOW},
])
def test_a_signed_receipt_does_not_widen_the_principal(gate, base, changes):
    envelope = signed(described(base))
    refused("PRINCIPAL_REFUSED", admit, gate, envelope, base, principal(**changes))
    assert consumed(gate) == 0


def test_a_hand_built_or_missing_principal_is_refused(gate, base):
    envelope = signed(described(base))
    hand_built = Principal("op-1", BASE["tenant"], frozenset({"proj"}), frozenset({"operator"}), Assurance.HIGH,
                           SyntheticFixtureAdapter.ISSUER, datetime(2099, 1, 1, tzinfo=timezone.utc))
    for who in (hand_built, {"subject_id": "op-1"}):
        refused("PRINCIPAL_REFUSED", rs.admit_governed_run, gate, envelope, principal=who, **inputs(base))
    refused("PRINCIPAL_REFUSED", rs.admit_governed_run, gate, envelope, principal=None, **inputs(base))
    assert consumed(gate) == 0


@pytest.mark.parametrize("level", ["personal", "sensitive", "unheard-of"])
def test_rows_that_policy_would_not_allow_are_refused(gate, base, level):
    package = make_package()
    package["instances"][0]["property_sensitivity"]["x:unmapped"] = level
    envelope = signed(described(base, package=package))
    refused("PRINCIPAL_REFUSED", admit, gate, envelope, base, package=package)
    assert consumed(gate) == 0


def test_the_admitted_run_is_the_copy_that_was_checked(tmp_path, paths, base):
    package, mapping, scenario = make_package(), copy.deepcopy(MAPPING), copy.deepcopy(base)
    envelope = signed(described(base))
    original = copy.deepcopy(package)
    armed = []

    def clock():
        if armed:  # the caller's objects change while the admission is in progress
            package["instances"][0]["property_values"][ACT] = 0.99
            mapping["personas"]["senior_residents"] = "swapped"
            scenario.rounds = 999
            scenario.llm["model"] = "swapped"  # nested objects too
            scenario.raw["topic"] = "swapped"
        return NOW

    with rg.open_receipt_gate(write(tmp_path, settings(paths)), clock=clock, monotonic=lambda: 100.0) as gate:
        gate.refresh_key_list(envelope_for())
        armed.append(True)
        admitted = admit(gate, envelope, scenario, package=package, mapping=mapping)
    assert admitted.run.package == original and admitted.run.mapping == MAPPING
    assert rs.scenario_digest(admitted.run.scenario) == admitted.run.action["effective_scenario_sha256"]
    assert admitted.run.scenario.rounds == base.rounds and admitted.run.scenario.llm == base.llm


def test_reading_the_run_cannot_change_it(base):
    run = described(base)
    run.package["instances"].clear()
    run.mapping["personas"].clear()
    run.scenario.segments.clear()
    run.projection["assumptions"].clear()
    assert run.package == make_package() and run.mapping == MAPPING
    assert len(run.scenario.segments) == 4 and run.projection["assumptions"]
    assert rs.scenario_digest(run.scenario) == run.action["effective_scenario_sha256"]
    with pytest.raises(TypeError):
        run.request["subject"] = "op-2"


def test_description_does_not_change_the_callers_inputs(base):
    package, mapping, before = make_package(), copy.deepcopy(MAPPING), rs.scenario_digest(base)
    described(base, package=package, mapping=mapping)
    assert package == make_package() and mapping == MAPPING and rs.scenario_digest(base) == before


def _tuple_rows(package):
    package["instances"] = tuple(package["instances"])


def _number_key(package):
    package["manifest"]["scenario_parameters"] = {1: "a"}


def _not_finite(package):
    package["extra"] = float("nan")


def _extra_number_key(package):
    package["extra"] = {1: "a"}


def _extra_tuple(package):
    package["extra"] = ("a",)


def _not_an_object(package):
    package["manifest"] = None


class _Shifty(dict):
    pass


def _subclass(package):
    package["instances"][0] = _Shifty(package["instances"][0])


def _validated(package):
    package["validated_prediction_enabled"] = True


def _stale_hash(package):
    package["manifest"]["import_id"] = "import-9"


def _no_binding(package):
    del package["manifest"]["binding_id"]


def _no_rows(package):
    package["instances"] = []


def _long_binding(package):
    package["manifest"]["binding_id"] = "has space"


@pytest.mark.parametrize("change", [_extra_number_key, _extra_tuple, _not_an_object, _tuple_rows, _number_key, _not_finite, _subclass, _validated, _stale_hash,
                                    _no_binding, _no_rows, _long_binding])
def test_unsafe_run_inputs_are_refused(base, change):
    package = make_package()
    change(package)
    refused("RUN_INPUT", described, base, package=package)


def test_scenario_digest_separates_types_and_refuses_unknown_values(base):
    one, two = copy.deepcopy(base), copy.deepcopy(base)
    one.raw, two.raw = {"v": ["a"]}, {"v": ("a",)}
    assert rs.scenario_digest(one) != rs.scenario_digest(two)
    one.raw, two.raw = {"v": datetime(2026, 1, 1)}, {"v": "2026-01-01T00:00:00"}
    assert rs.scenario_digest(one) != rs.scenario_digest(two)
    for bad in ({"v": {1, 2}}, {1: "a"}, {"v": float("inf")}):
        one.raw = bad
        refused("RUN_INPUT", rs.scenario_digest, one)


def test_a_naive_worker_clock_is_a_refusal(tmp_path, paths, base):
    envelope = signed(described(base))
    with rg.open_receipt_gate(write(tmp_path, settings(paths)), clock=lambda: NOW.replace(tzinfo=None),
                              monotonic=lambda: 100.0) as gate:
        refused("BAD_CLOCK", admit, gate, envelope, base)
        assert consumed(gate) == 0


def test_only_a_loaded_scenario_and_a_real_gate_are_accepted(base):
    refused("RUN_INPUT", described, {"name": "not a scenario"})

    class Other(scenario_mod.Scenario):
        pass

    refused("RUN_INPUT", described, Other(**{f: getattr(base, f) for f in base.__dataclass_fields__}))
    refused("RUN_INPUT", rs.describe_run, subject_id="op-1", **inputs(base, package=[]))
    refused("RUN_INPUT", rs.admit_governed_run, object(), {}, principal=principal(), **inputs(base))

"""A signed resume receipt names the run, its admissions and the committed checkpoint (library only, test keys)."""
import copy
import dataclasses

import pytest

from agora.security import run_scope as rs
from agora.security import signed_receipt as sr
from test_engine_governed_input import MAPPING, make_package
from test_receipt_gate import consumed, paths, refused
from test_receipt_run_scope import base, gate, inputs, principal, signed

__all__ = ["base", "gate", "paths"]  # fixtures re-used


def h(char):
    return "sha256:" + char * 64


def checkpoint(**changes):
    return rs.Checkpoint(**{"start_receipt_sha256": h("1"), "previous_receipt_sha256": h("2"),
                            "committed_round": 0, "state_sha256": h("3"), "reply_cache_sha256": h("4"), **changes})


def described(base, point=None, **changes):
    return rs.describe_resume(subject_id="op-1", checkpoint=point or checkpoint(), **inputs(base, **changes))


def admit(gate, envelope, base, point=None, who=None, **changes):
    return rs.admit_governed_resume(gate, envelope, principal=who or principal(),
                                    checkpoint=point or checkpoint(), **inputs(base, **changes))


def test_a_resume_receipt_is_admitted_once(gate, base):
    run = described(base)
    envelope = signed(run)
    admitted = admit(gate, envelope, base)
    assert admitted.admission.receipt["purpose"] == "governed_resume.v1"
    assert dict(admitted.run.action) == dict(run.action)
    refused("REPLAY", admit, gate, envelope, base)
    assert consumed(gate) == 1


def test_the_resume_action_names_exactly_what_is_bound(base):
    start = rs.describe_run(subject_id="op-1", **inputs(base))
    run = described(base)
    assert dict(run.action) == {
        "domain": "agora.governed-resume-action.v1", "run_action_sha256": start.request["manifest_hash"],
        "start_receipt_sha256": h("1"), "previous_receipt_sha256": h("2"), "committed_round": 0,
        "state_sha256": h("3"), "reply_cache_sha256": h("4")}
    assert run.request["manifest_hash"] == rs._digest(dict(run.action))
    assert run.scenario == start.scenario and run.package == start.package
    with pytest.raises(TypeError):
        run.request["purpose"] = "governed_run.v1"


def test_no_reply_cache_is_stated_not_omitted(base):
    assert described(base, checkpoint(reply_cache_sha256=None)).action["reply_cache_sha256"] == "none"


@pytest.mark.parametrize("change", [
    {"start_receipt_sha256": h("a")}, {"previous_receipt_sha256": h("a")}, {"committed_round": 1},
    {"state_sha256": h("a")}, {"reply_cache_sha256": h("a")}, {"reply_cache_sha256": None},
])
def test_a_receipt_for_another_checkpoint_is_refused(gate, base, change):
    base = copy.deepcopy(base)
    base.rounds = 5
    envelope = signed(described(base))
    refused("SCOPE_MISMATCH", admit, gate, envelope, base, checkpoint(**change))
    assert consumed(gate) == 0


@pytest.mark.parametrize("change", ["row", "mapping", "seed"])
def test_a_receipt_is_refused_when_the_run_inputs_changed(gate, base, change):
    envelope = signed(described(base))
    package, mapping, scenario = make_package(), copy.deepcopy(MAPPING), copy.deepcopy(base)
    if change == "row":
        package["synthetic_demo"] = False
    elif change == "mapping":
        mapping["personas"]["senior_residents"] = "A different persona"
    else:
        scenario.seed += 1
    refused("SCOPE_MISMATCH", admit, gate, envelope, scenario, package=package, mapping=mapping)
    assert consumed(gate) == 0


def test_a_start_receipt_does_not_admit_a_resume(gate, base):
    envelope = signed(rs.describe_run(subject_id="op-1", **inputs(base)))
    refused("SCOPE_MISMATCH", admit, gate, envelope, base)
    assert consumed(gate) == 0


def test_a_resume_receipt_does_not_admit_a_start(gate, base):
    envelope = signed(described(base))
    refused("SCOPE_MISMATCH", rs.admit_governed_run, gate, envelope, principal=principal(), **inputs(base))
    assert consumed(gate) == 0


def test_the_purpose_alone_separates_a_resume_from_a_start(gate, base):
    envelope = signed(described(base), purpose="governed_run.v1")
    refused("SCOPE_MISMATCH", admit, gate, envelope, base)
    assert consumed(gate) == 0


@pytest.mark.parametrize("name", ["start_receipt_sha256", "previous_receipt_sha256", "state_sha256",
                                  "reply_cache_sha256"])
@pytest.mark.parametrize("bad", ["3" * 64, "sha256:" + "A" * 64, "sha256:" + "1" * 63, h("1") + "\n", "none", 3])
def test_a_malformed_checkpoint_hash_is_refused(base, name, bad):
    refused("RUN_INPUT", described, base, checkpoint(**{name: bad}))


@pytest.mark.parametrize("name", ["start_receipt_sha256", "previous_receipt_sha256", "state_sha256"])
def test_a_required_checkpoint_hash_cannot_be_left_out(base, name):
    refused("RUN_INPUT", described, base, checkpoint(**{name: None}))


@pytest.mark.parametrize("bad", [-1, True, 0.0, "0", None])
def test_a_committed_round_must_be_a_whole_number_from_zero(base, bad):
    refused("RUN_INPUT", described, base, checkpoint(committed_round=bad))


def test_a_checkpoint_with_nothing_left_to_run_is_refused(base):
    base = copy.deepcopy(base)
    base.rounds = 5
    assert described(base, checkpoint(committed_round=3)).action["committed_round"] == 3
    for done in (4, 5):
        refused("RUN_INPUT", described, base, checkpoint(committed_round=done))


def test_only_an_exact_checkpoint_is_read(base):
    class Other(rs.Checkpoint):
        pass

    values = dataclasses.asdict(checkpoint())
    for bad in (values, Other(**values)):
        refused("RUN_INPUT", rs.describe_resume, subject_id="op-1", checkpoint=bad, **inputs(base))


@pytest.mark.parametrize("changes", [{"tenant_id": "tenant-b"}, {"project_ids": ["other"]}, {"roles": ["reader"]},
                                     {"assurance": "LOW"}])
def test_a_resume_receipt_does_not_widen_the_principal(gate, base, changes):
    envelope = signed(described(base))
    refused("PRINCIPAL_REFUSED", admit, gate, envelope, base, who=principal(**changes))
    assert consumed(gate) == 0


def test_resume_admission_needs_a_real_gate_and_principal(gate, base):
    envelope = signed(described(base))
    call = {"checkpoint": checkpoint(), **inputs(base)}
    refused("RUN_INPUT", rs.admit_governed_resume, object(), envelope, principal=principal(), **call)
    refused("PRINCIPAL_REFUSED", rs.admit_governed_resume, gate, envelope, principal=None, **call)
    assert consumed(gate) == 0


def test_rows_policy_would_not_allow_are_refused_on_resume(gate, base):
    package = make_package()
    package["instances"][0]["property_sensitivity"]["x:unmapped"] = "sensitive"
    envelope = signed(described(base, package=package))
    refused("PRINCIPAL_REFUSED", admit, gate, envelope, base, package=package)
    assert consumed(gate) == 0

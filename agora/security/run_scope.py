"""What a signed receipt authorises when the action is a governed run (library only, test keys only).

Design: docs/PRODUCT_BOUNDARY_AND_INTEGRITY_DESIGN.md section 3C.

``scenario_hash`` of an input package covers its manifest payload only: not the rows, not the segment mapping
and not the scenario the run starts from. A receipt bound to the two package hashes alone would therefore still
admit a run whose rows, mapping or scenario had been changed. For purpose ``governed_run.v1`` the receipt's
``manifest_hash`` is instead the hash of a run action that names all of them.

The worker never takes request fields from a caller. ``admit_governed_run`` copies the inputs once, derives
every request field from that copy, admits through the ``ReceiptGate`` and returns the same copy to be run.

A resume is a different action (purpose ``governed_resume.v1``): it names the start action, the admission that
started the run, the admission before this one, and the committed checkpoint it continues from.

Engine use: ``Simulation(signed_input=...)`` can START a run through this admission. The engine refuses every
resume and does not call the resume functions yet; the CLI and web app use neither. Calling this module alone
makes no run use the returned scenario. Not bound by the start action: the model configuration override, the
knowledge graph, the reply cache, earlier run state, and the engine code (release attestation is not built). A
resume action also names the committed state and reply cache; it does not bind the engine code. There is no
production identity adapter; only the synthetic fixture issuer exists.
Not a boundary against code in the same process.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping

from agora.principal import IdentityError, Principal, decide_principal
from agora.scenario import Scenario
from agora.scenario_inputs import recompute_scenario_hash
from agora.scenario_projection import ProjectionError, project_segments
from agora.security import receipt_gate as rg
from agora.security import receipt_ledger as ledger
from agora.security import signed_receipt as sr

PURPOSE = "governed_run.v1"
ACTION_DOMAIN = "agora.governed-run-action.v1"
RESUME_PURPOSE = "governed_resume.v1"
RESUME_ACTION_DOMAIN = "agora.governed-resume-action.v1"
NO_REPLY_CACHE = "none"
_SENSITIVITY_ORDER = ("public", "internal", "personal", "sensitive")


def _refuse(detail: str) -> sr.ReceiptError:
    return sr.ReceiptError("RUN_INPUT", detail)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("ascii")).hexdigest()


def _json_copy(value: Any) -> Any:
    """A private copy of plain JSON data. Exact types only: anything json would silently rewrite (a tuple, a
    non-text key) or that could answer differently on a second read (a subclass, a custom mapping) is refused."""
    kind = type(value)
    if value is None or kind in (str, int, bool):
        return value
    if kind is float and math.isfinite(value):
        return value
    if kind is list:
        return [_json_copy(item) for item in value]
    if kind is dict:
        items = list(value.items())
        if any(type(key) is not str for key, _ in items):
            raise _refuse("object keys must be text")
        return {key: _json_copy(item) for key, item in items}
    raise _refuse(f"inputs must be plain JSON data, not {kind.__name__}")


def plain_copy(value: Any) -> Any:
    """The same private, exact-types-only copy the run action is derived from, for a caller that has to inspect an
    input before admission without reading the original twice."""
    return _json_copy(value)


def _typed(value: Any) -> Any:
    """An unambiguous JSON form of scenario values: every container and date carries its type, so a list, a
    tuple, an object and a date can never share bytes."""
    kind = type(value)
    if value is None or kind in (str, int, bool):
        return value
    if kind is float and math.isfinite(value):
        return value
    if kind in (list, tuple):
        return [kind.__name__, [_typed(item) for item in value]]
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise _refuse("scenario object keys must be text")
        return ["dict", {key: _typed(item) for key, item in value.items()}]
    if kind in (datetime, date):
        return [kind.__name__, value.isoformat()]
    raise _refuse(f"the scenario holds a value of type {kind.__name__}")


def scenario_digest(scenario: Scenario) -> str:
    """SHA-256 over every dataclass field of a scenario, including the raw document it was loaded from."""
    return _digest(_typed(dataclasses.asdict(scenario)))


@dataclass(frozen=True)
class RunDescription:
    """What a run would do. ``request`` holds the receipt scope the worker presents to the gate and is what an
    issuer signs (together with tenant and release id, which come from worker configuration). A plain value
    object: holding one authorises nothing. The property accessors return fresh copies."""

    request: Mapping[str, str]
    action: Mapping[str, str]
    _package: dict
    _mapping: dict
    _scenario: Scenario
    _projection: dict

    @property
    def package(self) -> dict:
        return copy.deepcopy(self._package)

    @property
    def mapping(self) -> dict:
        return copy.deepcopy(self._mapping)

    @property
    def scenario(self) -> Scenario:
        return copy.deepcopy(self._scenario)

    @property
    def projection(self) -> dict:
        return copy.deepcopy(self._projection)


@dataclass(frozen=True)
class AdmittedRun:
    run: RunDescription
    admission: ledger.AdmittedReceipt


def describe_run(*, package: Mapping[str, Any], mapping: Mapping[str, Any], base_scenario: Scenario,
                 project_id: str, subject_id: str) -> RunDescription:
    """Derive the receipt scope of one run from the inputs themselves. Reads nothing else and writes nothing."""
    if type(base_scenario) is not Scenario:
        raise _refuse("base_scenario must be a loaded Scenario")
    own_package, own_mapping = _json_copy(package), _json_copy(mapping)
    base = copy.deepcopy(base_scenario)
    if type(own_package) is not dict:
        raise _refuse("package must be an object")
    manifest = own_package.get("manifest")
    try:
        input_scenario_hash = recompute_scenario_hash(manifest)
        import_id, binding_id = manifest["import_id"], manifest["binding_id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise _refuse("package manifest is incomplete") from exc
    if not (manifest.get("scenario_hash") == input_scenario_hash == own_package.get("scenario_hash")):
        raise _refuse("package scenario_hash does not match its manifest")
    try:
        derived, projection = project_segments(own_package, own_mapping, base)
    except (ProjectionError, TypeError, ValueError) as exc:
        raise _refuse(f"projection refused: {exc}") from exc
    action = {
        "domain": ACTION_DOMAIN,
        "package_sha256": _digest(own_package),
        "mapping_sha256": _digest(own_mapping),
        "base_scenario_sha256": scenario_digest(base),
        "effective_scenario_sha256": scenario_digest(derived),
    }
    request = {"subject": subject_id, "project": project_id, "import_id": import_id, "binding_id": binding_id,
               "manifest_hash": _digest(action), "scenario_hash": input_scenario_hash, "purpose": PURPOSE}
    for name, value in request.items():
        if type(value) is not str or not (sr._HASH if name in sr._HASH_FIELDS else sr._TOKEN).match(value):
            raise _refuse(f"{name} cannot be written in a receipt")
    return RunDescription(MappingProxyType(request), MappingProxyType(action), own_package, own_mapping,
                          derived, projection)


@dataclass(frozen=True)
class Checkpoint:
    """The committed point a resume continues from. The worker MUST read every value from its own run and audit
    stores; values copied from the requester or the receipt would make the scope check compare a claim with
    itself. ``previous_receipt_sha256`` is the latest admission for this run: the start receipt for a first resume.
    ``reply_cache_sha256`` is None only for a run whose scenario keeps no reply cache."""

    start_receipt_sha256: str
    previous_receipt_sha256: str
    committed_round: int
    state_sha256: str
    reply_cache_sha256: str | None


def _checkpoint_fields(checkpoint: Checkpoint, rounds: int) -> dict:
    if type(checkpoint) is not Checkpoint:
        raise _refuse("a resume needs a Checkpoint")
    values = {field.name: getattr(checkpoint, field.name) for field in dataclasses.fields(Checkpoint)}  # one read
    committed = values["committed_round"]
    if type(committed) is not int or committed < 0:
        raise _refuse("committed_round must be a whole number from 0: there is nothing to resume before a commit")
    if committed >= rounds - 1:
        raise _refuse("no round is left to run after this checkpoint")
    hashes = ["start_receipt_sha256", "previous_receipt_sha256", "state_sha256"]
    if values["reply_cache_sha256"] is not None:
        hashes.append("reply_cache_sha256")
    for name in hashes:
        value = values[name]
        if type(value) is not str or not sr._HASH.match(value):
            raise _refuse(f"{name} must be sha256: followed by 64 lowercase hex digits")
    if values["reply_cache_sha256"] is None:
        values["reply_cache_sha256"] = NO_REPLY_CACHE
    return values


def describe_resume(*, package: Mapping[str, Any], mapping: Mapping[str, Any], base_scenario: Scenario,
                    project_id: str, subject_id: str, checkpoint: Checkpoint) -> RunDescription:
    """Derive the receipt scope of continuing one run from one checkpoint. Reads nothing else, writes nothing.

    The inputs are derived again, exactly as for the start, so a changed row, mapping or scenario gives another
    ``run_action_sha256``. This function cannot tell whether those inputs started this run, or whether the
    checkpoint is true: the caller compares the first with the run's stored provenance and reads the second.
    """
    start = describe_run(package=package, mapping=mapping, base_scenario=base_scenario, project_id=project_id,
                         subject_id=subject_id)
    action = {"domain": RESUME_ACTION_DOMAIN, "run_action_sha256": start.request["manifest_hash"],
              **_checkpoint_fields(checkpoint, start._scenario.rounds)}
    request = {**start.request, "manifest_hash": _digest(action), "purpose": RESUME_PURPOSE}
    return dataclasses.replace(start, request=MappingProxyType(request), action=MappingProxyType(action))


def _highest_sensitivity(package: Mapping[str, Any]) -> str | None:
    """The highest level any row declares; None (which policy denies) if any level is unknown."""
    highest = 0
    for row in package["instances"]:
        for level in row["property_sensitivity"].values():
            if level not in _SENSITIVITY_ORDER:
                return None
            highest = max(highest, _SENSITIVITY_ORDER.index(level))
    return _SENSITIVITY_ORDER[highest]


def admit_governed_run(gate: rg.ReceiptGate, envelope: Mapping[str, Any], *, principal: Principal,
                       package: Mapping[str, Any], mapping: Mapping[str, Any], base_scenario: Scenario,
                       project_id: str) -> AdmittedRun:
    """Admit one signed receipt for exactly these inputs, or raise ``sr.ReceiptError`` and consume nothing
    (the one exception is the ledger's AUDIT_ANCHOR_WRITE_FAILED: the receipt is spent; do not act).

    The subject is the principal's, never a caller's text. The principal must be adapter-issued, unexpired, of
    the gate's tenant and allowed ``simulation_input`` on this project. A signed receipt does not widen what
    the principal may do. A receipt is single use: starting again needs a new one.
    """
    _require_admission_types(gate, principal)
    run = describe_run(package=package, mapping=mapping, base_scenario=base_scenario, project_id=project_id,
                       subject_id=principal.subject_id)
    return _admit(gate, envelope, principal, project_id, run)


def admit_governed_resume(gate: rg.ReceiptGate, envelope: Mapping[str, Any], *, principal: Principal,
                          package: Mapping[str, Any], mapping: Mapping[str, Any], base_scenario: Scenario,
                          project_id: str, checkpoint: Checkpoint) -> AdmittedRun:
    """Admit one signed resume receipt for exactly these inputs and this checkpoint. Refusals, the principal rule
    and single use are as for ``admit_governed_run``. Admission does not continue anything, and it does not check
    the checkpoint against any store: see ``Checkpoint``.
    """
    _require_admission_types(gate, principal)
    run = describe_resume(package=package, mapping=mapping, base_scenario=base_scenario, project_id=project_id,
                          subject_id=principal.subject_id, checkpoint=checkpoint)
    return _admit(gate, envelope, principal, project_id, run)


def _require_admission_types(gate: rg.ReceiptGate, principal: Principal) -> None:
    if type(gate) is not rg.ReceiptGate:
        raise _refuse("admission needs a ReceiptGate")
    if type(principal) is not Principal:
        raise sr.ReceiptError("PRINCIPAL_REFUSED", "principal_missing")


def _admit(gate: rg.ReceiptGate, envelope: Mapping[str, Any], principal: Principal, project_id: str,
           run: RunDescription) -> AdmittedRun:
    level = _highest_sensitivity(run._package)
    resource = {"project_id": project_id, "tenant_id": gate.tenant, "source_role": "scenario_input",
                "source_sensitivity": level, "target_sensitivity": level,
                "resource_ids": [run.request["import_id"], run.request["binding_id"]]}
    try:
        decision, _ = decide_principal(principal, "simulation_input", resource, now=gate.now())
    except IdentityError as exc:
        raise sr.ReceiptError("BAD_CLOCK", "the worker clock cannot be used") from exc
    if decision.get("decision") != "allow":
        raise sr.ReceiptError("PRINCIPAL_REFUSED", str(decision.get("reason")))
    return AdmittedRun(run, gate.admit(envelope, request=dict(run.request)))


__all__ = ["ACTION_DOMAIN", "NO_REPLY_CACHE", "PURPOSE", "RESUME_ACTION_DOMAIN", "RESUME_PURPOSE", "AdmittedRun",
           "Checkpoint", "RunDescription", "admit_governed_resume", "admit_governed_run", "describe_resume",
           "describe_run", "plain_copy", "scenario_digest"]

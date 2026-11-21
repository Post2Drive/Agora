"""Fail-closed construction of provenance-rich scenario inputs.

This adapter deliberately stops at an immutable, serialisable input package. It
does not import or call the simulation engine and never resolves a moving
``latest`` selector.
"""

from __future__ import annotations

from agora import protection as _protection

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .ontology.binding import DataBinding, materialize_instances
from .ontology.registry import OntologyError, OntologyPack
from .ontology.binding import load_binding
from .policy_enforcement import PolicyCallable, PolicyEnforcementError, enforce_policy


class ScenarioInputError(ValueError):
    """Raised when a scenario input violates its provenance or privacy contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_snapshot_metadata(project: Path, import_id: str) -> dict[str, Any]:
    if not isinstance(import_id, str) or not import_id.strip() or import_id == "latest":
        raise ScenarioInputError("an explicit import_id is required; latest is not allowed")
    database = project / "data" / "tabular.sqlite3"
    if not database.is_file():
        raise ScenarioInputError("snapshot database was not found")
    try:
        conn = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT manifest_json FROM imports WHERE import_id=? AND status='committed'", (import_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        raise ScenarioInputError("snapshot metadata could not be read") from exc
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    if row is None:
        raise ScenarioInputError("explicit committed snapshot was not found")
    manifest = json.loads(row[0])
    if manifest.get("import_id") != import_id:
        raise ScenarioInputError("snapshot import_id does not match the requested import")
    if not manifest.get("schema_fingerprint") or not manifest.get("file_sha256"):
        raise ScenarioInputError("snapshot manifest is missing required hashes")
    return manifest


def _policy_fingerprint(policy: Mapping[str, Any] | None) -> str | None:
    return None if policy is None else _sha256(dict(policy))


def _check_policy(instances: list[dict[str, Any]], policy: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sensitive = {
        property_id
        for instance in instances
        for property_id, level in instance.get("property_sensitivity", {}).items()
        if level in {"personal", "sensitive"}
    }
    if not sensitive:
        return instances, []
    if not isinstance(policy, Mapping):
        raise ScenarioInputError("personal or sensitive values require an explicit transformation policy")
    scalar_required = {"policy_id", "purpose", "retention", "reviewer", "approved_at", "audit_reference"}
    required = scalar_required | {"authorized_property_ids"}
    if not required.issubset(policy) or any(not isinstance(policy[key], str) or not policy[key].strip() for key in scalar_required):
        if "authorized_property_ids" in policy and not isinstance(policy["authorized_property_ids"], (list, tuple, set)):
            raise ScenarioInputError("transformation policy authorized_property_ids must be a list")
        raise ScenarioInputError("transformation policy is incomplete")
    authorized = set(policy["authorized_property_ids"])
    if any(not isinstance(value, str) or not value.strip() for value in authorized):
        raise ScenarioInputError("transformation policy authorized_property_ids must contain text IDs")
    known = set(instances[0].get("property_sensitivity", {})) if instances else set()
    unknown = authorized - known
    if unknown:
        raise ScenarioInputError("transformation policy references an unknown property")
    non_sensitive = authorized - sensitive
    if non_sensitive:
        raise ScenarioInputError("transformation policy can authorize only personal or sensitive properties")
    sanitized = []
    redactions: list[dict[str, Any]] = []
    for instance in instances:
        clone = dict(instance)
        clone["property_values"] = dict(instance.get("property_values", {}))
        for property_id in sorted(sensitive - authorized):
            if property_id in clone["property_values"]:
                clone["property_values"][property_id] = "[REDACTED]"
                redactions.append({"property_id": property_id, "row_id": instance.get("row_id")})
        sanitized.append(clone)
    return sanitized, redactions


def build_scenario_input(
    binding: DataBinding | Mapping[str, Any],
    pack: OntologyPack,
    project: str | Path,
    import_id: str,
    *,
    scenario_parameters: Mapping[str, Any] | None = None,
    transformation_policy: Mapping[str, Any] | None = None,
    policy: PolicyCallable | None = None,
    audit: Any | None = None,
) -> dict[str, Any]:
    """Build a deterministic scenario-input package from one explicit snapshot.

    When supplied, policy is called as policy("simulation_input", resource)
    before the snapshot database is opened. A policy is mandatory: None is denied (and audited).
    """
    if not isinstance(import_id, str) or not import_id.strip() or import_id == "latest":
        raise ScenarioInputError("an explicit import_id is required; latest is not allowed")
    project = Path(project)
    if policy is not None or _protection.POLICY_REQUIRED:
        try:
            policy_binding = binding if isinstance(binding, DataBinding) else load_binding(binding)
            properties = {item.property_id: item for item in pack.property_types}
            sensitivity_rank = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}
            source_sensitivity = max(
                (policy_binding.property_sensitivity.get(
                    property_id, properties[property_id].sensitivity
                 ) for property_id in policy_binding.column_map.values()),
                key=lambda value: sensitivity_rank[value],
            )
            enforce_policy(
                policy,
                audit=audit,
                project=project,
                operation="simulation_input",
                require_policy=_protection.POLICY_REQUIRED,
                resource={
                    "project_id": project.name or str(project),
                    "resource_ids": [import_id, policy_binding.binding_id],
                    "import_id": import_id,
                    "binding_id": policy_binding.binding_id,
                    "dataset_id": policy_binding.dataset_id,
                    "source_role": "scenario_input",
                    "source_sensitivity": source_sensitivity,
                    "target_sensitivity": source_sensitivity,
                    "purpose": transformation_policy.get("purpose") if isinstance(transformation_policy, Mapping) else None,
                    "retention": transformation_policy.get("retention") if isinstance(transformation_policy, Mapping) else None,
                },
            )
        except PolicyEnforcementError as exc:
            raise ScenarioInputError("Policy denied scenario-input construction.") from exc
        except (OntologyError, ValueError) as exc:
            raise ScenarioInputError(str(exc)) from exc
    snapshot = _read_snapshot_metadata(project, import_id)
    role = snapshot.get("data_role")
    if role == "sealed_holdout":
        raise ScenarioInputError("sealed_holdout snapshots cannot feed scenario inputs")
    if role not in {"context", "scenario_input"}:
        raise ScenarioInputError("snapshot data role is unsupported")
    try:
        instances = materialize_instances(
            binding, pack, project, import_id, policy=policy, audit=audit,
            purpose=transformation_policy.get("purpose") if isinstance(transformation_policy, Mapping) else None,
            retention=transformation_policy.get("retention") if isinstance(transformation_policy, Mapping) else None,
        )
    except (OntologyError, ValueError) as exc:
        raise ScenarioInputError(str(exc)) from exc
    instances, redactions = _check_policy(instances, transformation_policy)
    parameters = dict(scenario_parameters or {})
    policy_fp = _policy_fingerprint(transformation_policy)
    binding_fingerprint = binding.fingerprint if isinstance(binding, DataBinding) else _sha256(binding)
    payload = {
        "import_id": import_id,
        "snapshot_manifest_hash": _sha256(snapshot),
        "schema_fingerprint": snapshot["schema_fingerprint"],
        "binding_fingerprint": binding_fingerprint,
        "ontology_pack_fingerprint": pack.fingerprint,
        "transformation_policy_fingerprint": policy_fp,
        "scenario_parameters": parameters,
    }
    scenario_hash = _sha256({"domain": "agora-scenario-input-v1", "payload": payload})
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        **payload,
        "dataset_id": snapshot["dataset_id"],
        "schema_id": snapshot["schema_id"],
        "schema_version": snapshot["schema_version"],
        "file_sha256": snapshot["file_sha256"],
        "source_registry_id": snapshot.get("source_registry_id"),
        "data_role": role,
        "binding_id": binding.binding_id if isinstance(binding, DataBinding) else binding.get("binding_id"),
        "binding_version": binding.binding_version if isinstance(binding, DataBinding) else binding.get("binding_version"),
        "ontology_pack_id": pack.pack_id,
        "ontology_schema_version": pack.schema_version,
        "engine_application_version": "0.3.0",
        "created_at": created_at,
        "scenario_hash": scenario_hash,
        "run_provenance_reference": f"scenario:{scenario_hash}",
        "redactions": redactions,
    }
    return {
        "manifest": manifest,
        "scenario_hash": scenario_hash,
        "import_id": import_id,
        "instances": instances,
        "run_record": {"import_id": import_id, "scenario_hash": scenario_hash, "input_manifest": manifest},
        "validated_prediction_enabled": False,
    }


__all__ = ["ScenarioInputError", "build_scenario_input"]

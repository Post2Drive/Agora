"""Read-only bindings from tabular snapshots to ontology instances."""

from __future__ import annotations

from agora import protection as _protection

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping
import uuid

import yaml

from ..identity import stable_record_key
from ..audit_anchor import require_anchored
from ..policy_enforcement import PolicyCallable, PolicyEnforcementError, enforce_policy
from ..tabular import (
    SnapshotIntegrityError, iter_snapshot_rows, read_snapshot_row,
    verify_snapshot_manifest, verify_snapshot_row,
)
from .loader import _UniqueKeyLoader, _load_unique_json
from .registry import LOGICAL_DATA_TYPES, OntologyError, OntologyPack, PropertyType, ProposalMismatchError


_ALLOWED_KEYS = {
    "binding_id", "binding_version", "object_type_id", "object_type_version",
    "dataset_id", "schema_id", "schema_version", "column_map", "identity",
    "property_sensitivity", "fingerprint",
}
_REQUIRED_KEYS = _ALLOWED_KEYS - {"property_sensitivity", "fingerprint"}
_COMPATIBLE = {
    "string": {"string", "identifier", "enum"},
    "integer": {"integer", "decimal"},
    "decimal": {"decimal"},
    "boolean": {"boolean"},
    "date": {"date"},
    "timestamp": {"timestamp"},
    "enum": {"enum", "string"},
}
_SENSITIVITY_RANK = {"public": 0, "internal": 1, "personal": 2, "sensitive": 3}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OntologyError(f"{field} must be a non-empty string")
    return value.strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _fingerprint(value: Mapping[str, Any]) -> str:
    body = {key: value[key] for key in sorted(value) if key != "fingerprint"}
    return "sha256:" + hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdentityBinding:
    strategy: str
    primary_key_column: str


@dataclass(frozen=True)
class DataBinding:
    binding_id: str
    binding_version: str
    object_type_id: str
    object_type_version: str
    dataset_id: str
    schema_id: str
    schema_version: str
    column_map: dict[str, str]
    identity: IdentityBinding
    property_sensitivity: dict[str, str]
    fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "binding_version": self.binding_version,
            "object_type_id": self.object_type_id,
            "object_type_version": self.object_type_version,
            "dataset_id": self.dataset_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "column_map": dict(self.column_map),
            "identity": {"strategy": self.identity.strategy, "primary_key_column": self.identity.primary_key_column},
            "property_sensitivity": dict(self.property_sensitivity),
        }


def load_binding(path_or_payload: str | Path | Mapping[str, Any]) -> DataBinding:
    """Load and validate a binding from YAML/JSON or a mapping."""
    if isinstance(path_or_payload, Mapping):
        raw = dict(path_or_payload)
    else:
        source = Path(path_or_payload)
        try:
            content = source.read_text(encoding="utf-8")
            raw = _load_unique_json(content) if source.suffix.lower() == ".json" else yaml.load(content, Loader=_UniqueKeyLoader)
        except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, TypeError) as exc:
            raise OntologyError(f"invalid binding: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise OntologyError("binding must be an object")
    if any(not isinstance(key, str) for key in raw):
        raise OntologyError("binding field names must be strings")
    unknown = sorted(set(raw) - _ALLOWED_KEYS)
    missing = sorted(_REQUIRED_KEYS - set(raw))
    if unknown:
        raise OntologyError(f"binding has unknown keys: {', '.join(unknown)}")
    if missing:
        raise OntologyError(f"binding is missing required fields: {', '.join(missing)}")
    column_map = raw["column_map"]
    if not isinstance(column_map, Mapping) or not column_map or any(not isinstance(k, str) or not isinstance(v, str) for k, v in column_map.items()):
        raise OntologyError("column_map must map non-empty column names to property IDs")
    if len(set(column_map.values())) != len(column_map):
        raise OntologyError("column_map cannot map multiple columns to one property")
    identity = raw["identity"]
    if not isinstance(identity, Mapping) or set(identity) != {"strategy", "primary_key_column"}:
        raise OntologyError("identity must contain strategy and primary_key_column")
    if identity["strategy"] != "record_key":
        raise OntologyError("binding identity strategy must be record_key")
    if not isinstance(identity["primary_key_column"], str) or identity["primary_key_column"] not in column_map:
        raise OntologyError("identity primary_key_column must be mapped")
    sensitivities = raw.get("property_sensitivity", {})
    if not isinstance(sensitivities, Mapping) or any(
        not isinstance(k, str) or not isinstance(v, str) or v not in _SENSITIVITY_RANK for k, v in sensitivities.items()
    ):
        raise OntologyError("property_sensitivity must contain valid classifications")
    if set(sensitivities) - set(column_map.values()):
        # An ignored key would let a mistyped override look applied when it is not.
        raise OntologyError("property_sensitivity may only name mapped property IDs")
    body = {
        "binding_id": _text(raw["binding_id"], "binding_id"),
        "binding_version": _text(raw["binding_version"], "binding_version"),
        "object_type_id": _text(raw["object_type_id"], "object_type_id"),
        "object_type_version": _text(raw["object_type_version"], "object_type_version"),
        "dataset_id": _text(raw["dataset_id"], "dataset_id"),
        "schema_id": _text(raw["schema_id"], "schema_id"),
        "schema_version": _text(raw["schema_version"], "schema_version"),
        "column_map": dict(column_map),
        "identity": {"strategy": "record_key", "primary_key_column": identity["primary_key_column"]},
        "property_sensitivity": dict(sensitivities),
    }
    expected = _fingerprint(body)
    supplied = raw.get("fingerprint")
    if supplied is not None and supplied != expected:
        raise OntologyError("binding fingerprint does not match content")
    return DataBinding(**{**body, "identity": IdentityBinding(**body["identity"]), "fingerprint": expected})


def _properties(pack: OntologyPack, binding: DataBinding) -> tuple[Any, dict[str, PropertyType]]:
    objects = [item for item in pack.object_types if item.type_id == binding.object_type_id and item.version == binding.object_type_version]
    if len(objects) != 1:
        raise OntologyError("binding object type/version does not resolve")
    properties = {item.property_id: item for item in pack.property_types}
    missing = sorted(set(binding.column_map.values()) - set(properties))
    if missing:
        raise OntologyError(f"binding references unknown properties: {', '.join(missing)}")
    object_properties = set(objects[0].properties)
    if set(binding.column_map.values()) != object_properties:
        raise OntologyError("binding must map exactly the ObjectType properties")
    if objects[0].identity_strategy != "record_key":
        raise OntologyError("binding identity strategy does not match the ObjectType")
    for property_id, level in binding.property_sensitivity.items():
        if property_id not in object_properties or level not in _SENSITIVITY_RANK:
            raise OntologyError("property_sensitivity must classify mapped property IDs")
        if _SENSITIVITY_RANK[level] < _SENSITIVITY_RANK[properties[property_id].sensitivity]:
            raise OntologyError("sensitivity downgrade below the declared property classification")
    return objects[0], properties


def declared_sensitivity(pack: OntologyPack, binding: DataBinding) -> str:
    """Highest classification the pack and binding declare, for a pre-read policy decision.

    A binding may raise a property's classification and never lower it, so an
    override cannot understate what the policy decision point is asked about.
    """
    _object, properties = _properties(pack, binding)
    return max(
        (binding.property_sensitivity.get(property_id, properties[property_id].sensitivity)
         for property_id in binding.column_map.values()),
        key=lambda value: _SENSITIVITY_RANK[value],
    )


def _is_allowed_value(value: Any, prop: PropertyType) -> bool:
    for allowed in prop.allowed_values:
        if prop.data_type == "decimal":
            if allowed is None or isinstance(allowed, bool):
                continue
            try:
                if Decimal(str(allowed)) == Decimal(str(value)):
                    return True
            except InvalidOperation:
                continue
        elif type(allowed) is type(value) and allowed == value:
            return True
    return False


def _check_row_values(
    values: Mapping[str, Any], binding: DataBinding, properties: Mapping[str, PropertyType],
) -> None:
    """Enforce the pack's nullability and allowed values; errors never carry source values."""
    for column, property_id in binding.column_map.items():
        prop = properties[property_id]
        value = values.get(column)
        if value is None:
            if not prop.nullable:
                raise OntologyError(f"null value for non-nullable property {property_id}")
        elif prop.allowed_values and not _is_allowed_value(value, prop):
            raise OntologyError(f"value is not allowed by property {property_id}")


def _comparable(value: Any, prop: PropertyType) -> str:
    """Encode one non-null value so that equal values of a property encode equally."""
    if prop.data_type != "decimal":
        return _canonical(value)
    # Exact: Decimal.normalize() would round to the context precision.
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError) as exc:
        raise OntologyError(f"value of property {prop.property_id} is not a finite decimal") from exc
    sign, digits, exponent = number.as_tuple()
    significant = "".join(map(str, digits)).rstrip("0")
    if not significant:
        return "0"
    return f"{sign}:{significant}:{exponent + len(digits) - len(significant)}"


class _UniqueKeyCheck:
    """Refuse two rows of one import that share all values of a declared unique key.

    A key with a null component is not compared. Only digests of seen keys are
    retained, never source values; memory grows with the number of rows.
    """

    def __init__(self, object_type: Any, binding: DataBinding, properties: Mapping[str, PropertyType]) -> None:
        columns = {property_id: column for column, property_id in binding.column_map.items()}
        self._keys: list[tuple[tuple[str, ...], list[tuple[str, PropertyType]], set[bytes]]] = []
        for key in object_type.unique_keys:
            if not key or any(property_id not in columns for property_id in key):
                raise OntologyError("a declared unique key is empty or has a property that is not mapped")
            parts = [(columns[property_id], properties[property_id]) for property_id in key]
            self._keys.append((key, parts, set()))

    def add(self, values: Mapping[str, Any]) -> None:
        for key, parts, seen in self._keys:
            if any(values.get(column) is None for column, _prop in parts):
                continue
            encoded = _canonical([_comparable(values[column], prop) for column, prop in parts])
            digest = hashlib.sha256(encoded.encode("utf-8")).digest()
            if digest in seen:
                raise OntologyError(
                    f"snapshot rows repeat a value of the unique key ({', '.join(key)})"
                )
            seen.add(digest)


def validate_binding(pack: OntologyPack, snapshot_manifest: Mapping[str, Any], binding: DataBinding | Mapping[str, Any]) -> DataBinding:
    """Validate a binding against an ontology pack and explicit snapshot manifest."""
    binding = binding if isinstance(binding, DataBinding) else load_binding(binding)
    _object, properties = _properties(pack, binding)
    required_manifest = {"import_id", "dataset_id", "schema_id", "schema_version", "schema_fingerprint", "column_sensitivity", "column_types"}
    missing = sorted(required_manifest - set(snapshot_manifest))
    if missing:
        raise OntologyError(f"snapshot manifest is missing required fields: {', '.join(missing)}")
    for key in ("dataset_id", "schema_id", "schema_version"):
        if snapshot_manifest[key] != getattr(binding, key):
            raise OntologyError(f"snapshot {key} does not match binding")
    if not snapshot_manifest["import_id"] or snapshot_manifest["import_id"] == "latest":
        raise OntologyError("an explicit import_id is required")
    if snapshot_manifest.get("data_role") == "sealed_holdout":
        raise OntologyError("sealed_holdout snapshots cannot be materialized")
    columns = snapshot_manifest["column_sensitivity"]
    if not isinstance(columns, Mapping) or set(columns) != set(binding.column_map):
        raise OntologyError("snapshot columns do not match binding")
    types = snapshot_manifest["column_types"]
    if not isinstance(types, Mapping) or set(types) != set(binding.column_map):
        raise OntologyError("stored snapshot column types are missing or incomplete")
    policies = snapshot_manifest.get("column_policies", {})
    for column, property_id in binding.column_map.items():
        prop = properties[property_id]
        source_sensitivity = columns[column]
        target_sensitivity = binding.property_sensitivity.get(property_id, prop.sensitivity)
        if source_sensitivity not in _SENSITIVITY_RANK or target_sensitivity not in _SENSITIVITY_RANK:
            raise OntologyError("unknown sensitivity classification")
        if _SENSITIVITY_RANK[target_sensitivity] < _SENSITIVITY_RANK[source_sensitivity]:
            raise OntologyError(f"sensitivity downgrade for {column}")
        if source_sensitivity == "personal" and target_sensitivity not in {"personal", "sensitive"}:
            raise OntologyError(f"personal column {column} requires personal or sensitive property")
        if source_sensitivity == "personal":
            policy = policies.get(column, {})
            if not policy.get("purpose") or not policy.get("retention"):
                raise OntologyError(f"personal column {column} requires purpose and retention")
        source_type = types[column]
        if source_type not in _COMPATIBLE or prop.data_type not in _COMPATIBLE[source_type]:
            raise OntologyError(f"type mismatch for {column}")
    return binding


def _snapshot_manifest(project: Path, import_id: str) -> dict[str, Any]:
    if not import_id or import_id == "latest":
        raise OntologyError("an explicit import_id is required")
    db = project / "data" / "tabular.sqlite3"
    if not db.is_file():
        raise OntologyError("snapshot database was not found")
    try:
        conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
        row = conn.execute("SELECT manifest_json FROM imports WHERE import_id=? AND status='committed'", (import_id,)).fetchone()
    except sqlite3.Error as exc:
        raise OntologyError("snapshot metadata could not be read") from exc
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    if row is None:
        raise OntologyError("explicit committed snapshot was not found")
    try:
        manifest = json.loads(row[0])
        verify_snapshot_manifest(manifest, import_id)
    except (TypeError, ValueError) as exc:
        raise OntologyError(f"snapshot integrity check failed: {exc}") from exc
    return manifest


def _verified_rows(
    project: Path, manifest: Mapping[str, Any], batch_size: int = 512,
) -> Iterator[dict[str, Any]]:
    """Yield an import's rows, each checked against its row ID, then check the count."""
    count = 0
    try:
        for row in iter_snapshot_rows(project, manifest["import_id"], batch_size=batch_size):
            verify_snapshot_row(row, manifest)
            count += 1
            yield row
    except (SnapshotIntegrityError, json.JSONDecodeError) as exc:
        raise OntologyError(f"snapshot integrity check failed: {exc}") from exc
    accepted = manifest.get("accepted_records")
    if type(accepted) is not int or count != accepted:
        raise OntologyError("snapshot integrity check failed: row count differs from the manifest")


def materialize_instances(
    binding: DataBinding | Mapping[str, Any],
    pack: OntologyPack,
    project: str | Path,
    import_id: str,
    *,
    policy: PolicyCallable | None = None,
    audit: Any | None = None,
    purpose: str | None = None,
    retention: str | None = None,
) -> list[dict[str, Any]]:
    """Read one explicit snapshot and return provenance-rich ontology instances.

    When supplied, policy is called as policy("binding", resource) before the
    snapshot database is opened. A policy is mandatory: None is denied (and audited).

    The policy runs before any read, so the snapshot's column policies are not
    available to it. Callers that bind personal or sensitive data declare the
    purpose and retention explicitly; the policy decision point denies such
    data when either is missing. Both default to None (fail closed).
    """
    binding = binding if isinstance(binding, DataBinding) else load_binding(binding)
    project = Path(project)
    if policy is not None or _protection.POLICY_REQUIRED:
        source_sensitivity = declared_sensitivity(pack, binding)
        try:
            enforce_policy(
                policy,
                audit=audit,
                project=project,
                operation="binding",
                resource={
                    "project_id": project.name or str(project),
                    "resource_ids": [binding.binding_id, binding.dataset_id],
                    "binding_id": binding.binding_id,
                    "dataset_id": binding.dataset_id,
                    "source_sensitivity": source_sensitivity,
                    "target_sensitivity": source_sensitivity,
                    "purpose": purpose,
                    "retention": retention,
                },
            )
        except PolicyEnforcementError as exc:
            raise OntologyError("Policy denied ontology materialization.") from exc
    manifest = _snapshot_manifest(project, import_id)
    validate_binding(pack, manifest, binding)
    rows = list(_verified_rows(project, manifest))
    if not rows:
        raise OntologyError("snapshot contains no materializable rows")
    values_by_column = set(manifest.get("column_sensitivity", {}))
    if values_by_column != set(binding.column_map):
        raise OntologyError("snapshot columns do not match binding")
    reverse = {column: property_id for column, property_id in binding.column_map.items()}
    properties = {item.property_id: item for item in pack.property_types}
    effective_sensitivity = {
        property_id: max(
            (binding.property_sensitivity.get(property_id, "public"),
             manifest["column_sensitivity"][column],
             properties[property_id].sensitivity),
            key=lambda value: _SENSITIVITY_RANK[value],
        )
        for column, property_id in binding.column_map.items()
    }
    instances = []
    seen_keys: set[str] = set()
    unique_keys = _UniqueKeyCheck(_properties(pack, binding)[0], binding, properties)
    for row in rows:
        primary_value = row["values"].get(binding.identity.primary_key_column)
        if primary_value is None:
            raise OntologyError("primary key value is missing")
        _check_row_values(row["values"], binding, properties)
        key = stable_record_key(binding.dataset_id, primary_value)
        if key in seen_keys:
            # The binding's key column need not be the one the import enforced as unique.
            raise OntologyError("binding primary key is not unique in the snapshot")
        seen_keys.add(key)
        unique_keys.add(row["values"])
        instances.append({
            "object_type_id": binding.object_type_id,
            "object_type_version": binding.object_type_version,
            "property_values": {reverse[column]: row["values"].get(column) for column in reverse},
            "record_key": key,
            "row_id": row["row_id"],
            "import_id": import_id,
            "dataset_id": binding.dataset_id,
            "schema_id": binding.schema_id,
            "schema_version": binding.schema_version,
            "source_registry_id": row["source_locator"].get("source_registry_id"),
            "file_sha256": row["source_locator"].get("file_sha256"),
            "source_locator": row["source_locator"],
            "binding_id": binding.binding_id,
            "binding_version": binding.binding_version,
            "binding_fingerprint": binding.fingerprint,
            "property_sensitivity": effective_sensitivity,
        })
    return instances



def _authorize_source_snapshot(
    binding: DataBinding, pack: OntologyPack, project: Path, import_id: str, *,
    policy: PolicyCallable | None, audit: Any | None, purpose: str | None,
    retention: str | None,
) -> tuple[DataBinding, dict[str, Any]]:
    """Authorize before reading import metadata or snapshot rows."""
    binding = load_binding(binding.as_dict() if isinstance(binding, DataBinding) else binding)
    decision = None
    source_sensitivity = declared_sensitivity(pack, binding)
    if policy is not None or _protection.POLICY_REQUIRED:
        try:
            decision = enforce_policy(
                policy, audit=audit, project=project, operation="binding",
                resource={
                    "project_id": project.name or str(project),
                    "resource_ids": [binding.binding_id, binding.dataset_id, import_id],
                    "binding_id": binding.binding_id,
                    "dataset_id": binding.dataset_id,
                    "import_id": import_id,
                    "source_sensitivity": source_sensitivity,
                    "target_sensitivity": source_sensitivity,
                    "purpose": purpose,
                    "retention": retention,
                    "downstream_use": True,
                },
            )
        except PolicyEnforcementError as exc:
            raise OntologyError("Policy denied ontology materialization.") from exc
        if audit is not None or _protection.ANCHOR_REQUIRED:
            writer = require_anchored(audit) if _protection.ANCHOR_REQUIRED else audit
            writer.append({
                "event_id": f"ontology-binding-{uuid.uuid4().hex}",
                "event_type": "ontology_binding_read_authorized",
                "operation": "binding",
                "decision": "allow",
                "subject_id": str(decision.get("subject_id", "unknown")) if decision else "unknown",
                "policy_version": str(decision.get("policy_version", "unknown")) if decision else "unknown",
                "resource_ids": [binding.binding_id, binding.dataset_id, import_id],
                "reason": "policy_allow",
            })
    manifest = _snapshot_manifest(project, import_id)
    validate_binding(pack, manifest, binding)
    return binding, manifest


def _effective_property_sensitivity(
    pack: OntologyPack, binding: DataBinding, manifest: Mapping[str, Any],
) -> dict[str, str]:
    properties = {item.property_id: item for item in pack.property_types}
    return {
        property_id: max(
            (binding.property_sensitivity.get(property_id, "public"),
             manifest["column_sensitivity"][column],
             properties[property_id].sensitivity),
            key=lambda value: _SENSITIVITY_RANK[value],
        )
        for column, property_id in binding.column_map.items()
    }


def iter_source_object_refs(
    binding: DataBinding | Mapping[str, Any], pack: OntologyPack,
    project: str | Path, import_id: str, *,
    policy: PolicyCallable | None = None, audit: Any | None = None,
    purpose: str | None = None, retention: str | None = None,
    batch_size: int = 512,
) -> Iterator[dict[str, Any]]:
    """Yield bounded provenance references without retaining source property values."""
    project = Path(project)
    binding, manifest = _authorize_source_snapshot(
        binding if isinstance(binding, DataBinding) else load_binding(binding),
        pack, project, import_id, policy=policy, audit=audit,
        purpose=purpose, retention=retention,
    )
    effective_sensitivity = _effective_property_sensitivity(pack, binding, manifest)
    properties = {item.property_id: item for item in pack.property_types}
    unique_keys = _UniqueKeyCheck(_properties(pack, binding)[0], binding, properties)
    for row in _verified_rows(project, manifest, batch_size):
        primary_value = row["values"].get(binding.identity.primary_key_column)
        if primary_value is None:
            raise OntologyError("primary key value is missing")
        _check_row_values(row["values"], binding, properties)
        unique_keys.add(row["values"])
        locator = row["source_locator"]
        yield {
            "object_type_id": binding.object_type_id,
            "object_type_version": binding.object_type_version,
            "record_key": stable_record_key(binding.dataset_id, primary_value),
            "row_id": row["row_id"],
            "import_id": import_id,
            "dataset_id": binding.dataset_id,
            "schema_id": binding.schema_id,
            "schema_version": binding.schema_version,
            "schema_fingerprint": manifest["schema_fingerprint"],
            "source_registry_id": locator.get("source_registry_id"),
            "file_sha256": locator.get("file_sha256"),
            "source_locator": locator,
            "binding_id": binding.binding_id,
            "binding_version": binding.binding_version,
            "binding_fingerprint": binding.fingerprint,
            "property_sensitivity": effective_sensitivity,
        }


def materialize_source_object(
    binding: DataBinding | Mapping[str, Any], pack: OntologyPack,
    project: str | Path, import_id: str, row_id: str, expected_record_key: str, *,
    policy: PolicyCallable | None = None, audit: Any | None = None,
    purpose: str | None = None, retention: str | None = None,
) -> dict[str, Any]:
    """Read one exact source row after policy and binding validation.

    One row cannot show whether a declared unique key holds. The object store
    only has references from imports that ``iter_source_object_refs`` accepted.
    """
    project = Path(project)
    binding, manifest = _authorize_source_snapshot(
        binding if isinstance(binding, DataBinding) else load_binding(binding),
        pack, project, import_id, policy=policy, audit=audit,
        purpose=purpose, retention=retention,
    )
    try:
        row = read_snapshot_row(project, import_id, row_id)
        if row is not None:
            verify_snapshot_row(row, manifest)
    except SnapshotIntegrityError as exc:
        raise ProposalMismatchError(f"snapshot integrity check failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OntologyError(f"snapshot integrity check failed: {exc}") from exc
    if row is None:
        raise ProposalMismatchError("referenced snapshot row was not found")
    primary_value = row["values"].get(binding.identity.primary_key_column)
    if primary_value is None or stable_record_key(binding.dataset_id, primary_value) != expected_record_key:
        raise ProposalMismatchError("referenced snapshot row does not match the stable object identity")
    _check_row_values(row["values"], binding, {item.property_id: item for item in pack.property_types})
    reverse = {column: property_id for column, property_id in binding.column_map.items()}
    return {
        "object_type_id": binding.object_type_id,
        "object_type_version": binding.object_type_version,
        "property_values": {reverse[column]: row["values"].get(column) for column in reverse},
        "record_key": expected_record_key,
        "row_id": row["row_id"],
        "import_id": import_id,
        "dataset_id": binding.dataset_id,
        "schema_id": binding.schema_id,
        "schema_version": binding.schema_version,
        "schema_fingerprint": manifest["schema_fingerprint"],
        "source_registry_id": row["source_locator"].get("source_registry_id"),
        "file_sha256": row["source_locator"].get("file_sha256"),
        "source_locator": row["source_locator"],
        "binding_id": binding.binding_id,
        "binding_version": binding.binding_version,
        "binding_fingerprint": binding.fingerprint,
        "property_sensitivity": _effective_property_sensitivity(pack, binding, manifest),
    }

"""Versioned, fail-closed domain ontology registry contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any, Mapping

class OntologyError(ValueError):
    """Raised when an ontology pack violates the registry contract."""


SENSITIVITY_LEVELS = frozenset({"public", "internal", "personal", "sensitive"})
LOGICAL_DATA_TYPES = frozenset({"string", "integer", "decimal", "boolean", "date", "timestamp", "enum", "identifier", "structured_object"})
_ACTION_GUARDS = {
    "simulated_only": True,
    "execution_mode": "simulation_only",
    "external_writeback": "prohibited",
}
# ASCII digits only: ``\d`` also matches other Unicode digits, which no portable
# validator of the published schema would accept.
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OntologyError(f"value is not canonically serializable: {exc}") from exc


def _fingerprint(value: Any) -> str:
    payload = _canonical_json(value).encode("utf-8")
    return sha256(payload).hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OntologyError(f"{field} must be a non-empty string")
    return value.strip()


def _namespaced_id(value: Any, field: str) -> str:
    result = _required_text(value, field)
    namespace, separator, local = result.partition(":")
    if not separator or not namespace or not local:
        raise OntologyError(f"{field} must be a stable namespaced ID")
    return result


def _version(value: Any, field: str) -> str:
    result = _required_text(value, field)
    if not _VERSION_RE.fullmatch(result):
        raise OntologyError(f"{field} must be a semantic version")
    return result


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise OntologyError(f"{field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise OntologyError(f"{field} must be an object")
    return value


def _check_keys(value: Mapping[str, Any], allowed: set[str], required: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise OntologyError(f"{context} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise OntologyError(f"{context} is missing required fields: {', '.join(missing)}")


@dataclass(frozen=True)
class SourceBinding:
    source_registry_id: str
    locator: str


@dataclass(frozen=True)
class ObjectType:
    type_id: str
    version: str
    name: str
    description: str
    properties: tuple[str, ...]
    identity_strategy: str
    source_binding: SourceBinding | None = None
    unique_keys: tuple[tuple[str, ...], ...] = ()

    @property
    def fingerprint(self) -> str:
        return _fingerprint(_object_document(self))


def _object_document(item: ObjectType) -> dict[str, Any]:
    """Canonical form of an object type.

    ``unique_keys`` is left out when empty, so definitions written before it
    existed keep their fingerprints and stored bytes.
    """
    document = asdict(item)
    if not document["unique_keys"]:
        del document["unique_keys"]
    return document


@dataclass(frozen=True)
class PropertyType:
    property_id: str
    version: str
    name: str
    data_type: str
    required: bool
    nullable: bool
    sensitivity: str
    source_binding: SourceBinding | None = None
    allowed_values: tuple[Any, ...] = ()
    units: str | None = None
    precision: int | None = None
    scale: int | None = None
    timezone: str | None = None

    @property
    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True)
class LinkType:
    link_type_id: str
    version: str
    name: str
    source_type_id: str
    target_type_id: str
    predicate: str
    cardinality: str

    @property
    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True)
class ActionType:
    action_type_id: str
    version: str
    name: str
    actor_type_id: str
    target_type_id: str
    inputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    effects: tuple[str, ...]
    permissions: tuple[str, ...]
    simulated_only: bool
    execution_mode: str
    external_writeback: str

    @property
    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True)
class OntologyPack:
    pack_id: str
    schema_version: str
    object_types: tuple[ObjectType, ...]
    property_types: tuple[PropertyType, ...]
    link_types: tuple[LinkType, ...]
    action_types: tuple[ActionType, ...]

    @property
    def fingerprint(self) -> str:
        return _fingerprint(pack_document(self))

    def definitions(self) -> tuple[tuple[str, Any], ...]:
        return (
            *(("ObjectType", item) for item in self.object_types),
            *(("PropertyType", item) for item in self.property_types),
            *(("LinkType", item) for item in self.link_types),
            *(("ActionType", item) for item in self.action_types),
        )


def pack_document(pack: OntologyPack) -> dict[str, Any]:
    """The canonical document of a pack: what is fingerprinted and stored."""
    document = asdict(pack)
    document["object_types"] = [_object_document(item) for item in pack.object_types]
    return document


@dataclass(frozen=True)
class RegistryChange:
    kind: str
    type_id: str
    old_version: str | None
    new_version: str | None
    old_fingerprint: str | None
    new_fingerprint: str | None


class OntologyRegistry:
    """In-memory, version-aware registry with immutable version keys."""

    def __init__(self, pack_id: str, schema_version: str) -> None:
        self.pack_id = pack_id
        self.schema_version = schema_version
        self._definitions: dict[tuple[str, str, str], Any] = {}

    @classmethod
    def from_pack(cls, pack: OntologyPack) -> "OntologyRegistry":
        registry = cls(pack.pack_id, pack.schema_version)
        registry.register(pack)
        return registry

    def register(self, pack: OntologyPack) -> None:
        if pack.pack_id != self.pack_id:
            raise OntologyError("cannot register definitions from a different pack")
        pending = []
        for kind, definition in pack.definitions():
            type_id = _definition_id(kind, definition)
            key = (kind, type_id, definition.version)
            previous = self._definitions.get(key)
            if previous is not None and previous.fingerprint != definition.fingerprint:
                raise OntologyError("same type ID and version has a different content fingerprint")
            pending.append((key, definition))
        self._definitions.update(pending)
        self.schema_version = pack.schema_version

    @property
    def fingerprint(self) -> str:
        body = [
            {"kind": kind, "type_id": type_id, "version": version, "fingerprint": definition.fingerprint}
            for (kind, type_id, version), definition in sorted(self._definitions.items())
        ]
        return _fingerprint({"pack_id": self.pack_id, "schema_version": self.schema_version, "definitions": body})

    def get(self, kind: str, type_id: str, version: str) -> Any:
        try:
            return self._definitions[(kind, type_id, version)]
        except KeyError as exc:
            raise OntologyError(f"unknown {kind} definition {type_id}@{version}") from exc

    def changes_from(self, previous: "OntologyRegistry") -> tuple[RegistryChange, ...]:
        if self.pack_id != previous.pack_id:
            raise OntologyError("cannot compare registries from different packs")
        current_latest = _latest_by_type(self._definitions)
        previous_latest = _latest_by_type(previous._definitions)
        changes = []
        for key in sorted(set(current_latest) | set(previous_latest)):
            old = previous_latest.get(key)
            new = current_latest.get(key)
            old_fp = old.fingerprint if old is not None else None
            new_fp = new.fingerprint if new is not None else None
            old_version = old.version if old is not None else None
            new_version = new.version if new is not None else None
            if old_version != new_version or old_fp != new_fp:
                kind, type_id = key
                changes.append(RegistryChange(kind, type_id, old_version, new_version, old_fp, new_fp))
        return tuple(changes)


def _definition_id(kind: str, definition: Any) -> str:
    if kind == "ObjectType":
        return definition.type_id
    if kind == "PropertyType":
        return definition.property_id
    if kind == "LinkType":
        return definition.link_type_id
    return definition.action_type_id


def _latest_by_type(definitions: Mapping[tuple[str, str, str], Any]) -> dict[tuple[str, str], Any]:
    result: dict[tuple[str, str], Any] = {}
    for (kind, type_id, _version), definition in definitions.items():
        key = (kind, type_id)
        previous = result.get(key)
        if previous is None or _version_key(definition.version) > _version_key(previous.version):
            result[key] = definition
    return result


def _version_key(value: str) -> tuple[int, int, int, int, str]:
    core, _, suffix = value.partition("-")
    core = core.partition("+")[0]
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, (1 if not suffix else 0), suffix


def parse_domain_pack(data: Any) -> OntologyPack:
    """Validate and convert a parsed YAML/JSON domain pack."""
    root = _mapping(data, "domain pack")
    _check_keys(root, {"pack_id", "schema_version", "object_types", "property_types", "link_types", "action_types"},
                {"pack_id", "schema_version", "object_types", "property_types", "link_types", "action_types"}, "domain pack")
    pack_id = _required_text(root["pack_id"], "pack_id")
    schema_version = _version(root["schema_version"], "schema_version")

    properties = tuple(_parse_property(item, index) for index, item in enumerate(_list(root["property_types"], "property_types")))
    objects = tuple(_parse_object(item, index) for index, item in enumerate(_list(root["object_types"], "object_types")))
    links = tuple(_parse_link(item, index) for index, item in enumerate(_list(root["link_types"], "link_types")))
    actions = tuple(_parse_action(item, index) for index, item in enumerate(_list(root["action_types"], "action_types")))

    _unique_definitions(objects, "ObjectType", lambda item: item.type_id)
    _unique_definitions(properties, "PropertyType", lambda item: item.property_id)
    _unique_definitions(links, "LinkType", lambda item: item.link_type_id)
    _unique_definitions(actions, "ActionType", lambda item: item.action_type_id)

    property_ids = {item.property_id for item in properties}
    object_ids = {item.type_id for item in objects}
    for item in objects:
        missing = sorted(set(item.properties) - property_ids)
        if missing:
            raise OntologyError(f"ObjectType {item.type_id} references unknown properties: {', '.join(missing)}")
    data_types = {item.property_id: item.data_type for item in properties}
    for item in objects:
        for key in item.unique_keys:
            if any(data_types[property_id] == "structured_object" for property_id in key):
                raise OntologyError(f"ObjectType {item.type_id} unique key cannot include a structured_object property")
    for item in links:
        if item.source_type_id not in object_ids:
            raise OntologyError(f"LinkType {item.link_type_id} source_type_id does not resolve")
        if item.target_type_id not in object_ids:
            raise OntologyError(f"LinkType {item.link_type_id} target_type_id does not resolve")
    for item in actions:
        if item.actor_type_id not in object_ids or item.target_type_id not in object_ids:
            raise OntologyError(f"ActionType {item.action_type_id} actor_type_id/target_type_id does not resolve")
    from . import preconditions

    by_property = {item.property_id: item for item in properties}
    by_object = {item.type_id: item.properties for item in objects}
    for item in actions:
        try:
            preconditions.validate(item, by_object, by_property)
        except preconditions.PreconditionError as exc:
            raise OntologyError(f"ActionType {item.action_type_id} precondition is not valid: {exc}") from exc

    pack = OntologyPack(pack_id, schema_version, objects, properties, links, actions)
    pack.fingerprint
    return pack


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise OntologyError(f"{field} must be a list")
    return value


def _unique_definitions(items: tuple[Any, ...], label: str, get_id: Any) -> None:
    seen: dict[str, str] = {}
    for item in items:
        type_id = get_id(item)
        previous_version = seen.get(type_id)
        if previous_version is not None:
            if previous_version == item.version:
                raise OntologyError(f"duplicate {label} ID/version: {type_id}@{item.version}")
            raise OntologyError(
                f"ambiguous {label} ID {type_id}: multiple versions in one pack "
                f"({previous_version}, {item.version})"
            )
        seen[type_id] = item.version


def _parse_source_binding(value: Any, context: str) -> SourceBinding | None:
    if value is None:
        return None
    source = _mapping(value, f"{context}.source_binding")
    _check_keys(source, {"source_registry_id", "locator"}, {"source_registry_id", "locator"}, f"{context}.source_binding")
    return SourceBinding(
        _required_text(source["source_registry_id"], f"{context}.source_binding.source_registry_id"),
        _required_text(source["locator"], f"{context}.source_binding.locator"),
    )


def _parse_object(value: Any, index: int) -> ObjectType:
    context = f"object_types[{index}]"
    row = _mapping(value, context)
    allowed = {"type_id", "version", "name", "description", "properties", "identity_strategy", "source_binding",
               "unique_keys"}
    _check_keys(row, allowed, allowed - {"source_binding", "unique_keys"}, context)
    strategy = _required_text(row["identity_strategy"], f"{context}.identity_strategy")
    if strategy not in {"record_key", "assigned"}:
        raise OntologyError(f"{context}.identity_strategy is unsupported")
    properties = _string_tuple(row["properties"], f"{context}.properties")
    if len(set(properties)) != len(properties):
        raise OntologyError(f"{context}.properties must not repeat a property ID")
    return ObjectType(
        _namespaced_id(row["type_id"], f"{context}.type_id"), _version(row["version"], f"{context}.version"),
        _required_text(row["name"], f"{context}.name"), _required_text(row["description"], f"{context}.description"),
        properties, strategy,
        _parse_source_binding(row.get("source_binding"), context),
        _parse_unique_keys(row.get("unique_keys", []), properties, f"{context}.unique_keys"),
    )


def _parse_unique_keys(value: Any, properties: tuple[str, ...], context: str) -> tuple[tuple[str, ...], ...]:
    keys: list[tuple[str, ...]] = []
    seen: set[frozenset[str]] = set()
    for position, item in enumerate(_list(value, context)):
        key = _string_tuple(item, f"{context}[{position}]")
        if not key:
            raise OntologyError(f"{context}[{position}] must name at least one property")
        if len(set(key)) != len(key):
            raise OntologyError(f"{context}[{position}] must not repeat a property ID")
        if set(key) - set(properties):
            raise OntologyError(f"{context}[{position}] names an ID that is not a property of this object type")
        if frozenset(key) in seen:
            raise OntologyError(f"{context} declares the same unique key twice")
        seen.add(frozenset(key))
        keys.append(key)
    return tuple(keys)


def _parse_property(value: Any, index: int) -> PropertyType:
    context = f"property_types[{index}]"
    row = _mapping(value, context)
    allowed = {"property_id", "version", "name", "data_type", "required", "nullable", "sensitivity",
               "source_binding", "allowed_values", "units", "precision", "scale", "timezone"}
    required = {"property_id", "version", "name", "data_type", "required", "nullable", "sensitivity"}
    _check_keys(row, allowed, required, context)
    if not isinstance(row["required"], bool) or not isinstance(row["nullable"], bool):
        raise OntologyError(f"{context}.required and nullable must be booleans")
    data_type = _required_text(row["data_type"], f"{context}.data_type")
    if data_type not in LOGICAL_DATA_TYPES:
        raise OntologyError(f"{context}.data_type is unsupported")
    sensitivity = _required_text(row["sensitivity"], f"{context}.sensitivity")
    if sensitivity not in SENSITIVITY_LEVELS:
        raise OntologyError(f"{context}.sensitivity must be one of public, internal, personal or sensitive")
    source = _parse_source_binding(row.get("source_binding"), context)
    precision = row.get("precision")
    scale = row.get("scale")
    if precision is not None and (type(precision) is not int or precision <= 0):
        raise OntologyError(f"{context}.precision must be a positive integer")
    if scale is not None and (type(scale) is not int or scale < 0 or (precision is not None and scale > precision)):
        raise OntologyError(f"{context}.scale must be a non-negative integer no greater than precision")
    allowed_values = row.get("allowed_values", [])
    if not isinstance(allowed_values, list) or any(not isinstance(item, (str, int, float, bool, type(None))) for item in allowed_values):
        raise OntologyError(f"{context}.allowed_values must be a list of scalar values")
    for position, item in enumerate(allowed_values):
        if item is None:
            if not row["nullable"]:
                raise OntologyError(f"{context}.allowed_values[{position}] is null but the property is not nullable")
        elif not _matches_data_type(item, data_type):
            raise OntologyError(f"{context}.allowed_values[{position}] does not match data_type {data_type}")
    return PropertyType(
        _namespaced_id(row["property_id"], f"{context}.property_id"), _version(row["version"], f"{context}.version"),
        _required_text(row["name"], f"{context}.name"), data_type,
        row["required"], row["nullable"], sensitivity, source, tuple(allowed_values),
        _optional_text(row.get("units"), f"{context}.units"), precision, scale,
        _optional_text(row.get("timezone"), f"{context}.timezone"),
    )


def _matches_data_type(value: Any, data_type: str) -> bool:
    """Whether a listed value could ever equal a source value of this data type.

    The forms follow what tabular ingestion stores: dates and timestamps are
    compared as text, so they must be written in the stored canonical form.
    """
    if data_type in {"string", "identifier", "enum"}:
        return isinstance(value, str)
    if data_type == "integer":
        return type(value) is int
    if data_type == "boolean":
        return type(value) is bool
    if data_type == "decimal":
        # A boolean reads as "True" or "False", which is not a decimal.
        try:
            return Decimal(str(value)).is_finite()
        except (InvalidOperation, ValueError):  # ValueError: an integer too long to print
            return False
    if data_type in {"date", "timestamp"}:
        if not isinstance(value, str):
            return False
        try:
            if data_type == "date":
                return date.fromisoformat(value).isoformat() == value
            parsed = datetime.fromisoformat(value)
            # A time without an offset never equals its converted form.
            return parsed.astimezone(timezone.utc).isoformat() == value
        except (ValueError, OverflowError):
            return False
    # structured_object: a scalar can never equal an object value.
    return False


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _parse_link(value: Any, index: int) -> LinkType:
    context = f"link_types[{index}]"
    row = _mapping(value, context)
    keys = {"link_type_id", "version", "name", "source_type_id", "target_type_id", "predicate", "cardinality"}
    _check_keys(row, keys, keys, context)
    cardinality = _required_text(row["cardinality"], f"{context}.cardinality")
    if cardinality not in {"one_to_one", "one_to_many", "many_to_many"}:
        raise OntologyError(f"{context}.cardinality is unsupported")
    return LinkType(
        _namespaced_id(row["link_type_id"], f"{context}.link_type_id"), _version(row["version"], f"{context}.version"),
        _required_text(row["name"], f"{context}.name"), _namespaced_id(row["source_type_id"], f"{context}.source_type_id"),
        _namespaced_id(row["target_type_id"], f"{context}.target_type_id"), _required_text(row["predicate"], f"{context}.predicate"), cardinality,
    )


def _parse_action(value: Any, index: int) -> ActionType:
    context = f"action_types[{index}]"
    row = _mapping(value, context)
    keys = {"action_type_id", "version", "name", "actor_type_id", "target_type_id", "inputs", "preconditions", "effects",
            "permissions", "simulated_only", "execution_mode", "external_writeback"}
    _check_keys(row, keys, keys, context)
    for field, expected in _ACTION_GUARDS.items():
        if row[field] != expected or type(row[field]) is not type(expected):
            raise OntologyError(f"{context}.{field} must be {expected!r}")
    return ActionType(
        _namespaced_id(row["action_type_id"], f"{context}.action_type_id"), _version(row["version"], f"{context}.version"),
        _required_text(row["name"], f"{context}.name"), _namespaced_id(row["actor_type_id"], f"{context}.actor_type_id"),
        _namespaced_id(row["target_type_id"], f"{context}.target_type_id"), _string_tuple(row["inputs"], f"{context}.inputs"),
        _string_tuple(row["preconditions"], f"{context}.preconditions"), _string_tuple(row["effects"], f"{context}.effects"),
        _string_tuple(row["permissions"], f"{context}.permissions"), True, "simulation_only", "prohibited",
    )

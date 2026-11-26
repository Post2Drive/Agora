"""Published JSON Schemas for domain packs and data bindings.

The schemas are built here from the same constants the parsers use, and the
files under ``schemas/`` are the published copies (a test fails if they differ).
They describe document **structure** only. A document the schema accepts can
still be refused by Agora; ``docs/ONTOLOGY_PORTABLE_SCHEMAS.md`` lists why.

Print a schema with ``python -m agora.ontology.schema domain-pack`` or
``python -m agora.ontology.schema data-binding``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .binding import _ALLOWED_KEYS, _REQUIRED_KEYS, _SENSITIVITY_RANK
from .registry import _ACTION_GUARDS, LOGICAL_DATA_TYPES, SENSITIVITY_LEVELS


DIALECT = "https://json-schema.org/draft/2020-12/schema"
_ID_BASE = "urn:agora:ontology:schema"

# The characters Python's ``str.strip`` removes, spelled out because ``\s``
# means a different set in other regular-expression engines.
_WS = (
    "\\u0009-\\u000d\\u001c-\\u0020\\u0085\\u00a0\\u1680\\u2000-\\u200a"
    "\\u2028\\u2029\\u202f\\u205f\\u3000"
)
_PAD = f"[{_WS}]*"


def _object(properties: dict[str, Any], required: set[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(properties if required is None else required),
        "properties": properties,
    }


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _padded_enum(values: Any) -> dict[str, Any]:
    """One of ``values``; the pack parser ignores surrounding whitespace."""
    choices = "|".join(sorted(values))
    return {"type": "string", "pattern": f"^{_PAD}(?:{choices}){_PAD}(?![\\s\\S])"}


def domain_pack_schema() -> dict[str, Any]:
    text = _ref("text")
    identifier = _ref("namespacedId")
    version = _ref("version")
    texts = _array(text)
    source = {"anyOf": [{"type": "null"}, _object({"source_registry_id": text, "locator": text})]}
    optional_text = {"anyOf": [{"type": "null"}, text]}
    object_type = {
        "type_id": identifier, "version": version, "name": text, "description": text,
        "properties": texts, "identity_strategy": _padded_enum({"record_key", "assigned"}),
        "source_binding": source,
    }
    property_type = {
        "property_id": identifier, "version": version, "name": text,
        "data_type": _padded_enum(LOGICAL_DATA_TYPES),
        "required": {"type": "boolean"}, "nullable": {"type": "boolean"},
        "sensitivity": _padded_enum(SENSITIVITY_LEVELS),
        "source_binding": source,
        "allowed_values": _array({"type": ["string", "number", "boolean", "null"]}),
        "units": optional_text,
        "precision": {"type": ["integer", "null"], "minimum": 1},
        "scale": {"type": ["integer", "null"], "minimum": 0},
        "timezone": optional_text,
    }
    link_type = {
        "link_type_id": identifier, "version": version, "name": text,
        "source_type_id": identifier, "target_type_id": identifier, "predicate": text,
        "cardinality": _padded_enum({"one_to_one", "one_to_many", "many_to_many"}),
    }
    action_type = {
        "action_type_id": identifier, "version": version, "name": text,
        "actor_type_id": identifier, "target_type_id": identifier,
        "inputs": texts, "preconditions": texts, "effects": texts, "permissions": texts,
        **{field: {"const": value} for field, value in _ACTION_GUARDS.items()},
    }
    root = _object({
        "pack_id": text, "schema_version": version,
        "object_types": _array(_object(
            object_type, set(object_type) - {"source_binding"},
        )),
        "property_types": _array(_object(
            property_type, {"property_id", "version", "name", "data_type", "required", "nullable", "sensitivity"},
        )),
        "link_types": _array(_object(link_type)),
        "action_types": _array(_object(action_type)),
    })
    return {
        "$schema": DIALECT,
        "$id": f"{_ID_BASE}:domain-pack:1",
        "title": "Agora ontology domain pack (structure)",
        "$defs": {
            "text": {"type": "string", "pattern": f"[^{_WS}]"},
            "namespacedId": {"type": "string", "pattern": f"^{_PAD}[^:{_WS}][^:]*:{_PAD}[^{_WS}]"},
            # ``(?![\s\S])`` is end of input in every engine; ``$`` is not.
            "version": {
                "type": "string",
                "pattern": f"^{_PAD}[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?{_PAD}(?![\\s\\S])",
            },
        },
        **root,
    }


def data_binding_schema() -> dict[str, Any]:
    text = _ref("text")
    sensitivity = {"type": "string", "enum": sorted(_SENSITIVITY_RANK)}
    fields: dict[str, Any] = {
        "binding_id": text, "binding_version": text,
        "object_type_id": text, "object_type_version": text,
        "dataset_id": text, "schema_id": text, "schema_version": text,
        "column_map": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "string"}},
        "identity": _object({"strategy": {"const": "record_key"}, "primary_key_column": {"type": "string"}}),
        "property_sensitivity": {"type": "object", "additionalProperties": sensitivity},
        "fingerprint": {"type": ["string", "null"], "pattern": "^sha256:[0-9a-f]{64}(?![\\s\\S])"},
    }
    if set(fields) != _ALLOWED_KEYS:
        raise RuntimeError("binding schema fields differ from the binding parser")
    return {
        "$schema": DIALECT,
        "$id": f"{_ID_BASE}:data-binding:1",
        "title": "Agora ontology data binding (structure)",
        "$defs": {"text": {"type": "string", "pattern": f"[^{_WS}]"}},
        **_object(fields, set(_REQUIRED_KEYS)),
    }


SCHEMAS = {"domain-pack": domain_pack_schema, "data-binding": data_binding_schema}


def render(name: str) -> str:
    """Return the published text of one schema (stable bytes, ASCII, LF)."""
    return json.dumps(SCHEMAS[name](), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in SCHEMAS:
        print(f"usage: python -m agora.ontology.schema {{{'|'.join(SCHEMAS)}}}", file=sys.stderr)
        return 2
    sys.stdout.write(render(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

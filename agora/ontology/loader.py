"""Domain pack parsing and file loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .registry import OntologyError, OntologyPack, parse_domain_pack


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(None, None, "mapping keys must be scalar", key_node.start_mark) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_domain_pack(path: str | Path) -> OntologyPack:
    """Load a domain pack from a UTF-8 JSON, YAML, or YML file."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        raise OntologyError("domain pack file must use .json, .yaml or .yml")
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise OntologyError(f"cannot read domain pack: {exc}") from exc
    try:
        if suffix == ".json":
            data: Any = json.loads(content)
        else:
            data = yaml.load(content, Loader=_UniqueKeyLoader)
    except (json.JSONDecodeError, yaml.YAMLError, TypeError) as exc:
        raise OntologyError(f"invalid domain pack syntax: {exc}") from exc
    return parse_domain_pack(data)

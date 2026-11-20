"""Strict JSON input helpers for governance and validation data.

Reject duplicate object keys and JavaScript-style non-standard numeric constants
so that every governance input has one unambiguous interpretation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def strict_json_loads(text: str) -> Any:
    """Parse a JSON string, rejecting duplicate keys and non-standard constants."""
    if not isinstance(text, str):
        raise TypeError("JSON input must be text")
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def strict_json_load(path: str | Path) -> Any:
    """Read UTF-8 JSON from *path* with the same strict parsing rules."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"JSON file is not valid UTF-8: {path}") from exc
    return strict_json_loads(text)

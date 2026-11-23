"""Pure, deterministic projection of a scenario-input package into Scenario segments.

Slice 4.1 of docs/M3_DESIGN.md. No engine import, no I/O, no network, no randomness.
Every segment field must come from an explicit, declared mapping; nothing is inferred.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .scenario import Scenario, Segment


class ProjectionError(ValueError):
    """Raised when a package or mapping cannot be projected safely."""


# field -> (min, max) hard bounds
_BOUNDS = {
    "stance_mean": (-1.0, 1.0), "stance_sd": (0.0, 1.0), "stubbornness": (0.0, 1.0),
    "activity": (0.0, 1.0), "influence": (0.0, 10.0), "openness": (0.0, 1.0),
}
_ALLOWED_SENSITIVITY = {"public", "internal"}  # explicit allow-list; anything else is refused
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH_RE.fullmatch(value) is not None


def project_segments(package: Mapping[str, Any], mapping: Mapping[str, Any], base: Scenario) -> tuple[Scenario, dict[str, Any]]:
    """Return (derived Scenario, projection record). Fails closed on any violation."""
    if not isinstance(package, Mapping) or package.get("validated_prediction_enabled") is not False:
        raise ProjectionError("package must be a scenario-input package with validated_prediction_enabled False")
    manifest = package.get("manifest")
    instances = package.get("instances")
    if not isinstance(manifest, Mapping) or not _valid_hash(manifest.get("scenario_hash")) or not isinstance(instances, list) or not instances:
        raise ProjectionError("package has no manifest hash or no rows")
    if not isinstance(mapping, Mapping) or set(mapping) - {"segment_property", "numeric", "personas"}:
        raise ProjectionError("mapping has unknown keys")
    seg_prop = mapping.get("segment_property")
    numeric = mapping.get("numeric")
    personas = mapping.get("personas")
    if not isinstance(seg_prop, str) or not isinstance(numeric, Mapping) or not isinstance(personas, Mapping):
        raise ProjectionError("mapping needs segment_property, numeric and personas")
    if set(numeric) != set(_BOUNDS):
        raise ProjectionError(f"numeric must map exactly the segment fields {sorted(_BOUNDS)}")
    used = {seg_prop, *numeric.values()}
    if any(not isinstance(p, str) or not p for p in used):
        raise ProjectionError("mapping property ids must be non-empty text")

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for inst in instances:
        if not isinstance(inst, Mapping):
            raise ProjectionError("row is not an object")
        values = inst.get("property_values", {})
        sens = inst.get("property_sensitivity")
        if not isinstance(values, Mapping) or not isinstance(sens, Mapping):
            raise ProjectionError("row needs property_values and property_sensitivity objects")
        for pid in used:
            if pid not in values:
                raise ProjectionError(f"row is missing mapped property {pid}")
            if sens.get(pid) not in _ALLOWED_SENSITIVITY:
                raise ProjectionError(f"property {pid} has missing or non-projectable sensitivity")
            v = values[pid]
            if v is None or v == "[REDACTED]":
                raise ProjectionError(f"property {pid} is null or redacted")
        key = values[seg_prop]
        if not isinstance(key, str) or not key.strip():
            raise ProjectionError("segment key must be non-empty text")
        groups.setdefault(key, []).append(values)

    if set(personas) != set(groups):
        raise ProjectionError("personas must be declared for exactly the observed segments")
    total = len(instances)
    segments: list[Segment] = []
    for name in sorted(groups):
        rows = groups[name]
        fields: dict[str, float] = {}
        for fld, pid in sorted(numeric.items()):
            nums = []
            for row in rows:
                x = row[pid]
                if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                    raise ProjectionError(f"{pid} must be a finite number")
                nums.append(float(x))
            mean = math.fsum(nums) / len(nums)
            lo, hi = _BOUNDS[fld]
            if not lo <= mean <= hi:
                raise ProjectionError(f"{fld} for segment {name} is out of bounds")
            fields[fld] = mean
        persona = personas[name]
        if not isinstance(persona, str) or not persona.strip():
            raise ProjectionError("persona must be non-empty text")
        segments.append(Segment(name=name, share=len(rows) / total, persona=persona, **fields))

    derived = dataclasses.replace(base, segments=segments)
    # scenario_hash covers only the manifest payload, not the rows; bind the actual rows (order-independent).
    instances_hash = _hash(sorted(_hash({"property_values": dict(i["property_values"]), "property_sensitivity": dict(i["property_sensitivity"])}) for i in instances))
    record = {
        "scenario_hash": manifest["scenario_hash"],
        "instances_hash": instances_hash,
        "mapping_hash": _hash(dict(mapping)),
        "projection_hash": _hash({
            "scenario_hash": manifest["scenario_hash"], "instances_hash": instances_hash,
            "mapping": dict(mapping), "segments": [dataclasses.asdict(s) for s in segments],
        }),
        "assumptions": [
            "segment share = row count / total rows",
            "numeric fields = arithmetic mean of the mapped property within the segment",
            "personas are declared by the mapping, not inferred",
            "every segment numeric field is explicitly mapped; none keeps a default",
            "only public/internal classified properties are projected (allow-list)",
        ],
        "validated_prediction_enabled": False,
    }
    return derived, record


__all__ = ["ProjectionError", "project_segments"]

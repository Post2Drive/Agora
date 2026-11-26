"""Deterministic old-to-new domain pack compatibility check.

See docs/ONTOLOGY_COMPATIBILITY.md. This is a library and command-line check.
The ontology store does not call it, so it does not stop a pack from being
registered.

Fail closed: a changed field is breaking unless it is listed here as compatible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, fields
from typing import Any, Sequence

from .loader import load_domain_pack
from .registry import OntologyError, OntologyPack, _canonical_json

BREAKING = "breaking"
COMPATIBLE = "compatible"

# Display labels. Nothing resolves a definition by these.
_LABEL_FIELDS = {
    "ObjectType": frozenset({"name", "description"}),
    "PropertyType": frozenset({"name"}),
    "LinkType": frozenset({"name"}),
    "ActionType": frozenset({"name"}),
}
_ID_FIELD = {
    "ObjectType": "type_id",
    "PropertyType": "property_id",
    "LinkType": "link_type_id",
    "ActionType": "action_type_id",
}
_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class Change:
    kind: str
    type_id: str
    code: str
    level: str


@dataclass(frozen=True)
class Violation:
    kind: str
    type_id: str
    code: str
    old_version: str
    new_version: str


@dataclass(frozen=True)
class CompatibilityReport:
    pack_id: str
    old_fingerprint: str
    new_fingerprint: str
    changes: tuple[Change, ...]
    violations: tuple[Violation, ...]

    @property
    def breaking(self) -> bool:
        return any(item.level != COMPATIBLE for item in self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "breaking": self.breaking}


def _precedence(version: str) -> tuple[Any, ...]:
    """Semantic version precedence. Build metadata does not count."""
    match = _SEMVER.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise OntologyError("pack contains a version that is not a semantic version")
    core = tuple(int(part) for part in match.group(1, 2, 3))
    if match.group(4) is None:
        return (*core, 1, ())
    # Numeric identifiers compare as numbers and sort below text identifiers.
    pre = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in match.group(4).split("."))
    return (*core, 0, pre)


def _increased(old: str, new: str) -> bool:
    return _precedence(new) > _precedence(old)


def _major_increased(old: str, new: str) -> bool:
    return _precedence(new)[0] > _precedence(old)[0]


def _index(pack: OntologyPack) -> dict[tuple[str, str], Any]:
    result: dict[tuple[str, str], Any] = {}
    for kind, definition in pack.definitions():
        key = (kind, getattr(definition, _ID_FIELD[kind]))
        if key in result:
            raise OntologyError(f"pack contains more than one {kind} {key[1]}")
        result[key] = definition
    return result


def _encoded(values: Sequence[Any]) -> list[str]:
    # Encoded form keeps 1, 1.0 and true distinct.
    return sorted(_canonical_json(value) for value in values)


def _field_changes(kind: str, type_id: str, old: Any, new: Any) -> list[Change]:
    before, after = asdict(old), asdict(new)
    result = []
    for field in fields(old):
        name = field.name
        if name == "version" or _canonical_json(before[name]) == _canonical_json(after[name]):
            continue
        code, level = f"{name}_changed", BREAKING
        if name in _LABEL_FIELDS[kind]:
            level = COMPATIBLE
        elif kind == "ObjectType" and name == "properties":
            added, removed = set(after[name]) - set(before[name]), set(before[name]) - set(after[name])
            if sorted(before[name]) == sorted(after[name]):
                code, level = "properties_reordered", COMPATIBLE
            else:
                # A binding must map exactly the object's properties, so an
                # addition breaks it just as a removal does.
                if added:
                    result.append(Change(kind, type_id, "property_added_to_object", BREAKING))
                if removed:
                    result.append(Change(kind, type_id, "property_removed_from_object", BREAKING))
                if added or removed:
                    continue
        elif kind == "PropertyType" and name == "allowed_values":
            if _encoded(before[name]) == _encoded(after[name]):
                code, level = "allowed_values_reordered", COMPATIBLE
        elif kind == "PropertyType" and name == "sensitivity":
            order = ("public", "internal", "personal", "sensitive")
            if before[name] in order and after[name] in order:
                raised = order.index(after[name]) > order.index(before[name])
                code = "sensitivity_raised" if raised else "sensitivity_lowered"
        result.append(Change(kind, type_id, code, level))
    return result


def compare_packs(old: OntologyPack, new: OntologyPack) -> CompatibilityReport:
    """Classify every change from ``old`` to ``new`` and list version rule breaches."""
    if old.pack_id != new.pack_id:
        raise OntologyError("cannot compare different packs")
    before, after = _index(old), _index(new)
    changes: list[Change] = []
    violations: list[Violation] = []
    breaking_properties: set[str] = set()

    for key in sorted(set(before) | set(after)):
        kind, type_id = key
        first, second = before.get(key), after.get(key)
        if first is None:
            _precedence(second.version)
            changes.append(Change(kind, type_id, "definition_added", COMPATIBLE))
            continue
        if second is None:
            _precedence(first.version)
            changes.append(Change(kind, type_id, "definition_removed", BREAKING))
            continue
        found = _field_changes(kind, type_id, first, second)
        changes.extend(found)
        breaks = any(item.level != COMPATIBLE for item in found)
        if kind == "PropertyType" and breaks:
            breaking_properties.add(type_id)

        def refuse(code: str) -> None:
            violations.append(Violation(kind, type_id, code, first.version, second.version))

        if _precedence(second.version) < _precedence(first.version):
            refuse("version_decreased")
        elif found and not _increased(first.version, second.version):
            refuse("content_changed_without_version_increase")
        elif breaks and not _major_increased(first.version, second.version):
            refuse("breaking_change_without_major_increase")

    # Bindings pin only the object type version, so a breaking property change
    # must also move every object that carries the property to a new major.
    for key in sorted(set(before) & set(after)):
        kind, type_id = key
        if kind != "ObjectType":
            continue
        first, second = before[key], after[key]
        if breaking_properties & set(first.properties) & set(second.properties):
            if not _major_increased(first.version, second.version):
                violations.append(Violation(
                    kind, type_id, "object_without_major_increase_for_property_change",
                    first.version, second.version,
                ))

    version_bumped = any(
        before[key].version != after[key].version for key in set(before) & set(after)
    )
    breaking = any(item.level != COMPATIBLE for item in changes)

    def refuse_pack(code: str) -> None:
        violations.append(Violation("OntologyPack", old.pack_id, code, old.schema_version, new.schema_version))

    if _precedence(new.schema_version) < _precedence(old.schema_version):
        refuse_pack("version_decreased")
    elif (changes or version_bumped) and not _increased(old.schema_version, new.schema_version):
        refuse_pack("content_changed_without_version_increase")
    elif breaking and not _major_increased(old.schema_version, new.schema_version):
        refuse_pack("breaking_change_without_major_increase")

    return CompatibilityReport(
        old.pack_id, old.fingerprint, new.fingerprint, tuple(changes), tuple(violations)
    )


def require_release(old: OntologyPack, new: OntologyPack, *, allow_breaking: bool = False) -> CompatibilityReport:
    """Return the report, or raise if the new pack may not replace the old one.

    Version rule breaches are always refused. Correctly versioned breaking
    changes are refused unless ``allow_breaking`` is exactly ``True``.
    """
    report = compare_packs(old, new)
    if report.violations:
        listed = "; ".join(f"{v.kind} {v.type_id}: {v.code}" for v in report.violations)
        raise OntologyError(f"pack release breaks version rules: {listed}")
    if report.breaking and allow_breaking is not True:
        listed = "; ".join(f"{c.kind} {c.type_id}: {c.code}" for c in report.changes if c.level != COMPATIBLE)
        raise OntologyError(f"pack release has breaking changes: {listed}")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Exit 0: release allowed. 1: release refused. 2: input could not be used."""
    parser = argparse.ArgumentParser(prog="python -m agora.ontology.compat", description=main.__doc__)
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--allow-breaking", action="store_true", help="accept correctly versioned breaking changes")
    args = parser.parse_args(argv)
    try:
        report = compare_packs(load_domain_pack(args.old), load_domain_pack(args.new))
    except OntologyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    allowed = not report.violations and (args.allow_breaking or not report.breaking)
    print(json.dumps({**report.to_dict(), "release_allowed": allowed}, indent=2, sort_keys=True))
    return 0 if allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())

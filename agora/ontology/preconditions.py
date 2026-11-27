"""Machine-checkable action preconditions: a small, closed grammar inside the existing precondition strings.

A precondition that starts with ``expr:`` is evaluated; any other string stays free text and is not.
Grammar (nothing else is accepted, there is no function call, arithmetic, attribute walk or ``or``)::

    expr:   "expr:" clause ( " and " clause )*
    clause: operand OP operand          OP is one of == != < <= > >=
    operand: actor.<property_id> | target.<property_id> | param.<property_id> | literal
    literal: "text" | integer | decimal | true | false | null

``actor`` and ``target`` read the proposal's two objects, ``param`` reads the action's input values. A
reference must name a property of that object type (or an input of the action), and both sides must have
the same kind: number (integer and decimal), text (string, identifier, enum), date, or boolean. Ordering
(``<``, ``<=``, ``>``, ``>=``) is for numbers and dates only. Properties of other data types cannot be
used. A pack with a malformed ``expr:`` precondition is refused when it is parsed.

Evaluation fails closed: a missing value, a null compared with anything but ``==``/``!=`` against null, or
a value that does not have the declared kind makes the clause false. Messages never carry values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

PREFIX = "expr:"
_MAX_CLAUSES = 8
_MAX_LENGTH = 512
_OPS = ("==", "!=", "<=", ">=", "<", ">")
_REF = re.compile(r"(actor|target|param)\.([A-Za-z0-9_.:\-]{1,200})")
_STRING = re.compile(r'"([^"\\\x00-\x1f]{0,200})"')
_INTEGER = re.compile(r"-?(0|[1-9][0-9]{0,17})")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]{0,17})\.[0-9]{1,18}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_KINDS = {"integer": "number", "decimal": "number", "string": "text", "identifier": "text", "enum": "text",
          "date": "date", "boolean": "bool"}


class PreconditionError(ValueError):
    """The precondition text is outside the grammar or does not fit the pack."""


@dataclass(frozen=True)
class Ref:
    role: str
    property_id: str


@dataclass(frozen=True)
class Lit:
    kind: str  # number, text, date, bool, null
    value: Any


@dataclass(frozen=True)
class Clause:
    left: Ref | Lit
    op: str
    right: Ref | Lit


def is_expression(text: str) -> bool:
    return isinstance(text, str) and text.startswith(PREFIX)


def _operand(text: str) -> Ref | Lit:
    text = text.strip()
    if (match := _REF.fullmatch(text)):
        return Ref(match.group(1), match.group(2))
    if (match := _STRING.fullmatch(text)):
        return Lit("text", match.group(1))
    if text in ("true", "false"):
        return Lit("bool", text == "true")
    if text == "null":
        return Lit("null", None)
    if _DECIMAL.fullmatch(text):
        return Lit("number", Decimal(text))
    if _INTEGER.fullmatch(text):
        return Lit("number", Decimal(text))
    raise PreconditionError("an operand is not a reference or a literal")


def _split_clause(text: str) -> Clause:
    found = []
    quoted = False
    index = 0
    while index < len(text):
        if text[index] == '"':
            quoted = not quoted
        elif not quoted:
            for op in _OPS:
                if text.startswith(op, index):
                    found.append((index, op))
                    index += len(op) - 1
                    break
        index += 1
    if len(found) != 1:
        raise PreconditionError("a clause needs exactly one comparison")
    at, op = found[0]
    return Clause(_operand(text[:at]), op, _operand(text[at + len(op):]))


def parse(text: str) -> tuple[Clause, ...]:
    if not is_expression(text) or len(text) > _MAX_LENGTH or not text.isascii():
        raise PreconditionError("a precondition expression must be short ASCII text starting with expr:")
    body = text[len(PREFIX):].strip()
    pieces = []
    current, quoted, index = "", False, 0
    while index < len(body):
        if body[index] == '"':
            quoted = not quoted
        if not quoted and body.startswith(" and ", index):
            pieces.append(current)
            current, index = "", index + 5
            continue
        current += body[index]
        index += 1
    pieces.append(current)
    if quoted or not 1 <= len(pieces) <= _MAX_CLAUSES or any(not p.strip() for p in pieces):
        raise PreconditionError("a precondition has 1 to 8 clauses joined by ' and '")
    return tuple(_split_clause(p) for p in pieces)


def _kind_of(operand: Ref | Lit, properties: Mapping[str, Any], names: Mapping[str, frozenset[str]]) -> str:
    if isinstance(operand, Lit):
        return operand.kind
    if operand.property_id not in names[operand.role]:
        raise PreconditionError("a reference names a property the object type or action does not have")
    kind = _KINDS.get(properties[operand.property_id].data_type)
    if kind is None:
        raise PreconditionError("a reference names a property of a data type that cannot be compared")
    return kind


def validate(action: Any, object_properties: Mapping[str, tuple[str, ...]],
             properties: Mapping[str, Any]) -> None:
    """Raise ``PreconditionError`` unless every ``expr:`` precondition of the action fits the pack."""
    names = {"actor": frozenset(object_properties[action.actor_type_id]),
             "target": frozenset(object_properties[action.target_type_id]),
             "param": frozenset(action.inputs)}
    for text in action.preconditions:
        if not is_expression(text):
            continue
        for clause in parse(text):
            left, right = (_kind_of(x, properties, names) for x in (clause.left, clause.right))
            if "null" in (left, right):
                if clause.op not in ("==", "!="):
                    raise PreconditionError("null can only be compared with == or !=")
                continue
            if left != right and not (left == "date" and right == "text" and isinstance(clause.right, Lit)
                                      and _DATE.fullmatch(clause.right.value)) \
                    and not (right == "date" and left == "text" and isinstance(clause.left, Lit)
                             and _DATE.fullmatch(clause.left.value)):
                raise PreconditionError("the two sides of a comparison are not of the same kind")
            if clause.op not in ("==", "!=") and "date" not in (left, right) and left != "number":
                raise PreconditionError("ordering applies to numbers and dates only")


def _value(operand: Ref | Lit, properties: Mapping[str, Any], values: Mapping[str, Mapping[str, Any]]) -> Any:
    if isinstance(operand, Lit):
        return operand.value
    raw = values[operand.role].get(operand.property_id)
    if raw is None:
        return None
    kind = _KINDS[properties[operand.property_id].data_type]
    try:
        if kind == "number":
            if type(raw) is int:
                return Decimal(raw)
            return Decimal(raw) if isinstance(raw, str) else _Bad
        if kind == "bool":
            return raw if type(raw) is bool else _Bad
        if kind == "date":
            if not isinstance(raw, str) or not _DATE.fullmatch(raw):
                return _Bad
            date.fromisoformat(raw)
            return raw
        return raw if isinstance(raw, str) else _Bad
    except (InvalidOperation, ValueError):
        return _Bad


class _BadValue:
    pass


_Bad = _BadValue()


def _holds(clause: Clause, properties: Mapping[str, Any], values: Mapping[str, Mapping[str, Any]]) -> bool:
    left, right = _value(clause.left, properties, values), _value(clause.right, properties, values)
    if left is _Bad or right is _Bad:
        return False
    if left is None or right is None:
        if clause.op == "==":
            return left is None and right is None
        if clause.op == "!=":
            return not (left is None and right is None)
        return False
    if type(left) is not type(right):
        return False
    if clause.op == "==":
        return left == right
    if clause.op == "!=":
        return left != right
    if isinstance(left, bool):
        return False
    return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[clause.op]


def evaluate(text: str, properties: Mapping[str, Any], values: Mapping[str, Mapping[str, Any]]) -> bool:
    """True only if every clause holds. ``values`` maps actor, target and param to name -> value."""
    return all(_holds(clause, properties, values) for clause in parse(text))


__all__ = ["PREFIX", "PreconditionError", "evaluate", "is_expression", "parse", "validate"]

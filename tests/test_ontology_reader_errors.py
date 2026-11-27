"""Redacted read failures: one fixed error for every cause. All data is synthetic."""

from __future__ import annotations

import re
import sqlite3
import traceback

import pytest

from agora.ontology import OntologyError
from agora.ontology.reader import ObjectRef, OntologyReadError
from test_import_attestation import anchored  # noqa: F401
from test_ontology_reader import _deny, _key, _reader, world  # noqa: F401
from test_ontology_store import _allow
from test_snapshot_row_integrity import ROWS

_MESSAGE = re.compile(r"ontology read failed \(reference [0-9a-f]{32}\)\Z")


def _deny_source_only(operation, resource):
    """Allow the catalog reads and refuse the source snapshot read."""
    return (_deny if operation == "binding" else _allow)(operation, resource)


def _sql(world, statement):
    conn = sqlite3.connect(world.store.path)
    try:
        # Drop the triggers that make stored references immutable.
        for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            conn.execute(f'DROP TRIGGER "{name}"')
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _missing(world, sink):
    reader = _reader(world, error_sink=sink)
    return lambda: reader.get(world.types.Customer, _key("NO-SUCH"), world.import_id)


def _denied(world, sink):
    reader = _reader(world, error_sink=sink, policy=_deny)
    return lambda: reader.get(world.types.Customer, _key("C-1"), world.import_id)


def _source_denied(world, sink):
    reader = _reader(world, error_sink=sink, policy=_deny_source_only)
    return lambda: reader.get(world.types.Customer, _key("C-1"), world.import_id)


def _bad_filter(world, sink):
    reader = _reader(world, error_sink=sink)
    return lambda: reader.query(
        world.types.Customer, world.import_id, {"no_such_property": {"op": "eq", "value": 1}})


def _bad_cursor(world, sink):
    reader = _reader(world, error_sink=sink)
    return lambda: reader.query(world.types.Customer, world.import_id, cursor="not a cursor!")


def _bad_stored_json(world, sink):
    """The store lets this one out as a raw JSON error that keeps the text."""
    _sql(world, "UPDATE ontology_object_refs SET source_locator_json='{secret-text'")
    reader = _reader(world, error_sink=sink)
    return lambda: reader.get(world.types.Customer, _key("C-1"), world.import_id)


def _bad_link_request(world, sink):
    reader = _reader(world, error_sink=sink)
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    return lambda: reader.links("no_such_link", "1", one)


def _resolve_missing(world, sink):
    reader = _reader(world, error_sink=sink)
    cls = world.types.Customer
    ref = ObjectRef(cls.TYPE_ID, cls.TYPE_VERSION, world.import_id, _key("NO-SUCH"))
    return lambda: reader.resolve(ref)


CASES = [_missing, _denied, _source_denied, _bad_filter, _bad_cursor, _bad_stored_json,
         _bad_link_request, _resolve_missing]


@pytest.mark.parametrize("case", CASES)
def test_every_failure_reaches_the_caller_as_the_same_error(world, case):
    seen = []
    call = case(world, lambda reference, error: seen.append((reference, error)))
    with pytest.raises(OntologyReadError) as caught:
        call()
    raised = caught.value
    assert type(raised) is OntologyReadError
    assert isinstance(raised, OntologyError)
    assert _MESSAGE.match(str(raised))
    assert raised.args == (str(raised),)
    assert vars(raised) == {"reference": raised.reference}
    assert raised.__cause__ is None and raised.__context__ is None
    [(reference, original)] = seen
    assert reference == raised.reference
    assert not isinstance(original, OntologyReadError)
    printed = "".join(traceback.format_exception(type(raised), raised, raised.__traceback__))
    assert str(original) not in printed
    assert "secret-text" not in printed
    assert all(row[1] not in printed for row in ROWS)


def test_without_a_sink_the_store_messages_still_differ(world):
    """The default is unchanged, which is why it is for trusted code only."""
    cls = world.types.Customer
    with pytest.raises(OntologyError, match="not found in the exact import") as missing:
        _reader(world).get(cls, _key("NO-SUCH"), world.import_id)
    with pytest.raises(OntologyError, match="policy denied") as denied:
        _reader(world, policy=_deny).get(cls, _key("C-1"), world.import_id)
    assert not isinstance(missing.value, OntologyReadError)
    assert not isinstance(denied.value, OntologyReadError)


def test_each_failure_gets_its_own_reference(world):
    seen = []
    call = _missing(world, lambda reference, error: seen.append(reference))
    for _ in range(2):
        with pytest.raises(OntologyReadError):
            call()
    assert len(set(seen)) == 2


def test_a_failing_sink_does_not_expose_the_detail(world):
    def sink(reference, error):
        raise RuntimeError(f"sink failed on {error}")

    with pytest.raises(OntologyReadError) as caught:
        _missing(world, sink)()
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert _MESSAGE.match(str(caught.value))


def test_a_successful_read_does_not_call_the_sink(world):
    seen = []
    reader = _reader(world, error_sink=lambda *args: seen.append(args))
    one = reader.get(world.types.Customer, _key("C-1"), world.import_id)
    assert one.id == ROWS[0][0]
    assert len(reader.query(world.types.Customer, world.import_id).objects) == len(ROWS)
    assert seen == []


def test_request_refusals_keep_their_own_message(world):
    seen = []
    reader = _reader(world, error_sink=lambda *args: seen.append(args))
    with pytest.raises(OntologyError, match="not an object type"):
        reader.get(dict, _key("C-1"), world.import_id)
    with pytest.raises(OntologyError, match="needs an ObjectRef"):
        reader.resolve("C-1")
    with pytest.raises(OntologyError, match="no such object type"):
        reader.resolve(ObjectRef("nope", "1", world.import_id, "k"))
    assert seen == []


@pytest.mark.parametrize("sink", ["log", 1, False])
def test_a_sink_that_cannot_be_called_is_refused(world, sink):
    with pytest.raises(OntologyError, match="error_sink must be callable"):
        _reader(world, error_sink=sink)

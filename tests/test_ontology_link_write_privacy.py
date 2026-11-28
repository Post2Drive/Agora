"""Link writes over personal records need the caller's purpose and retention. All data is synthetic."""

from __future__ import annotations

import pytest

from agora.ontology import OntologyError
from agora.policy import decide
from test_import_attestation import _query, anchored  # noqa: F401
from test_ontology_link_read_privacy import MISSING
from test_ontology_reader import world  # noqa: F401
from test_ontology_read_attestation import _cite

LINK = ("backup:knows", "1.0.0")
CALLER = {"purpose": "case-review", "retention": "7d"}
CATALOG = ("ontology_catalog", "project_lifetime")


class _OperatorPolicy:
    """The product's own decision rules for the ``operator`` role, recording what it is asked."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.asked = []

    def __call__(self, operation, resource):
        self.asked.append((operation, resource["source_sensitivity"],
                           resource.get("purpose"), resource.get("retention")))
        return decide({"subject_id": "operator-1", "project_id": self.project_id},
                      "operator", operation, resource)


def _rows(world):
    return [_query(world.project, "ontology.sqlite3", f"SELECT * FROM {table} ORDER BY link_id")
            for table in ("ontology_links", "ontology_link_retractions")]


def _provenance(world):
    return {"kind": "source", "source_refs": [_cite(world.project, world.import_id)]}


def _add(world, **privacy):
    return world.store.add_link(
        world.pack_fp, *LINK, world.endpoint(world.import_id, "C-1"),
        world.endpoint(world.import_id, "C-2"), "2026-01-01T00:00:00+00:00", None,
        "referral", _provenance(world), policy=world.policy, audit=world.audit, **privacy)


def _supersede(world, **privacy):
    return world.store.supersede_link(
        world.pack_fp, world.existing, world.endpoint(world.import_id, "C-1"),
        world.endpoint(world.import_id, "C-2"), "2026-01-01T00:00:00+00:00",
        "2026-06-01T00:00:00+00:00", "ended", _provenance(world),
        policy=world.policy, audit=world.audit, **privacy)


def _retract(world, **privacy):
    return world.store.retract_link(
        world.pack_fp, world.existing, "entered in error", {"kind": "manual_assertion"},
        policy=world.policy, audit=world.audit, **privacy)


@pytest.fixture
def writable(world):  # noqa: F811
    world.policy = _OperatorPolicy(world.store.project_id)
    return world


@pytest.fixture
def linked(writable):
    writable.existing = _add(writable, **CALLER)
    writable.policy.asked.clear()
    return writable


def _assert_refused(world, write, privacy):
    before = _rows(world)
    with pytest.raises(OntologyError, match="policy denied"):
        write(world, **privacy)
    assert world.policy.asked[-1][:2] == ("ontology_write", "sensitive")
    assert _rows(world) == before


def _assert_asked_about_the_caller(world):
    record_level = [item for item in world.policy.asked if item[1] == "sensitive"]
    assert record_level == [("ontology_write", "sensitive", "case-review", "7d")]
    assert {item[2:] for item in world.policy.asked if item[1] == "internal"} == {CATALOG}


@pytest.mark.parametrize("privacy", MISSING)
def test_adding_a_personal_link_is_refused_without_purpose_and_retention(writable, privacy):
    _assert_refused(writable, _add, privacy)


@pytest.mark.parametrize("write", [_supersede, _retract])
@pytest.mark.parametrize("privacy", MISSING)
def test_changing_a_personal_link_is_refused_without_purpose_and_retention(linked, write, privacy):
    _assert_refused(linked, write, privacy)


def test_adding_asks_the_policy_about_the_callers_purpose(writable):
    assert _add(writable, **CALLER).startswith("link-")
    _assert_asked_about_the_caller(writable)


@pytest.mark.parametrize("write", [_supersede, _retract])
def test_changing_asks_the_policy_about_the_callers_purpose(linked, write):
    before = _rows(linked)
    write(linked, **CALLER)
    assert _rows(linked) != before
    _assert_asked_about_the_caller(linked)

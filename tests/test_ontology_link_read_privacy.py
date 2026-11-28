"""Link reads over personal records need the caller's purpose and retention. All data is synthetic."""

from __future__ import annotations

import pytest

from agora.ontology import OntologyError, OntologyObjectStore
from agora.policy import decide
from test_import_attestation import anchored  # noqa: F401
from test_ontology_reader import _key, _reader, world  # noqa: F401
from test_ontology_read_attestation import PRIVACY, _cite

LINK = ("backup:knows", "1.0.0")
MISSING = [
    {},
    {"purpose": PRIVACY["purpose"]},
    {"retention": PRIVACY["retention"]},
    {"purpose": "  ", "retention": PRIVACY["retention"]},
]


class _RolePolicy:
    """The product's own decision rules for the ``reader`` role, recording what it is asked."""

    def __init__(self, project_id):
        self.project_id = project_id
        self.asked = []

    def __call__(self, operation, resource):
        self.asked.append((operation, resource["source_sensitivity"],
                           resource.get("purpose"), resource.get("retention")))
        return decide({"subject_id": "reader-1", "project_id": self.project_id},
                      "reader", operation, resource)


@pytest.fixture
def linked(world):  # noqa: F811
    world.link(world.import_id, _cite(world.project, world.import_id))
    world.policy = _RolePolicy(world.store.project_id)
    world.endpoint = {
        "project_id": world.store.project_id, "pack_fingerprint": world.pack_fp,
        "type_id": "backup:Customer", "type_version": "1.0.0",
        "import_id": world.import_id, "record_key": _key("C-1"),
    }
    return world


def _list(world, **privacy):
    return world.store.get_links(world.pack_fp, *LINK, policy=world.policy,
                                 audit=world.audit, **privacy)


def _walk(world, **privacy):
    return world.store.traverse_links(
        world.pack_fp, *LINK, world.endpoint, world.import_id, 10, None,
        policy=world.policy, audit=world.audit, **privacy)["links"]


@pytest.mark.parametrize("read", [_list, _walk])
@pytest.mark.parametrize("privacy", MISSING)
def test_personal_links_are_refused_without_purpose_and_retention(linked, read, privacy):
    with pytest.raises(OntologyError, match="policy denied"):
        read(linked, **privacy)
    assert linked.policy.asked[-1][:2] == ("ontology_read", "sensitive")


@pytest.mark.parametrize("read", [_list, _walk])
def test_the_policy_is_asked_about_the_callers_purpose(linked, read):
    assert len(read(linked, purpose="case-review", retention="7d")) == 1
    record_level = [item for item in linked.policy.asked if item[1] == "sensitive"]
    assert record_level == [("ontology_read", "sensitive", "case-review", "7d")]


def test_a_reader_without_a_purpose_cannot_follow_personal_links(linked):
    one = _reader(linked).get(linked.types.Customer, _key("C-1"), linked.import_id)
    reader = _reader(linked, policy=linked.policy, purpose=None, retention=None)
    with pytest.raises(OntologyError, match="policy denied"):
        reader.links(*LINK, one)


def test_a_reader_passes_its_purpose_to_the_link_check(linked):
    one = _reader(linked).get(linked.types.Customer, _key("C-1"), linked.import_id)
    reader = _reader(linked, policy=linked.policy, purpose="case-review", retention="7d")
    assert len(reader.links(*LINK, one).links) == 1
    assert ("ontology_read", "sensitive", "case-review", "7d") in linked.policy.asked


def test_catalog_checks_keep_the_catalog_purpose(linked):
    """Pack and link-set checks carry no record data and need no caller purpose."""
    _list(linked, purpose="case-review", retention="7d")
    internal = {item[2:] for item in linked.policy.asked if item[1] == "internal"}
    assert internal == {("ontology_catalog", "project_lifetime")}


@pytest.mark.parametrize("level,needs_caller", [
    ("public", False), ("internal", False), ("personal", True), ("sensitive", True),
])
def test_which_levels_use_the_callers_purpose(level, needs_caller):
    result = OntologyObjectStore._record_privacy(level, "case-review", "7d")
    assert result == ({"privacy": ("case-review", "7d")} if needs_caller else {})


def test_an_empty_link_set_needs_no_purpose(world):  # noqa: F811
    policy = _RolePolicy(world.store.project_id)
    assert world.store.get_links(world.pack_fp, *LINK, policy=policy, audit=world.audit) == []

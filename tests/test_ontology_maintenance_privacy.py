"""Integrity verification, backup and restore ask the policy about the caller's purpose and retention.

The policy here is the product's own rule (``agora.policy.decide``) with an operator subject, so
the refusals are the ones the product would make. All data is synthetic.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore
from agora.ontology import store as store_module
from agora.policy import decide
from test_ontology_store import _allow, _binding, _import, _pack

GIVEN = {"purpose": "disaster recovery drill", "retention": "30 days"}
MISSING = [{}, {"purpose": GIVEN["purpose"]}, {"retention": GIVEN["retention"]},
           {"purpose": "  ", "retention": GIVEN["retention"]}]


class _Rules:
    """The product's decision rules; records what each check was handed."""

    def __init__(self, project_id, role="operator"):
        self.project_id, self.role, self.asked = project_id, role, []

    def __call__(self, operation, resource):
        self.asked.append((operation, tuple(resource["resource_ids"]), resource["source_sensitivity"],
                           resource["purpose"], resource["retention"]))
        subject = {"subject_id": "maintainer", "project_id": self.project_id}
        return decide(subject, self.role, operation, resource)


@pytest.fixture
def env(tmp_path):
    """A store holding one personal/sensitive record, with an anchored audit outside it."""
    project = tmp_path / "live" / "project"
    (project / "data").mkdir(parents=True)
    (tmp_path / "ops").mkdir()
    chain = AuditChainStore(tmp_path / "ops" / "audit.sqlite3")
    anchors = AnchorStore(tmp_path / "ops" / "anchor.jsonl", "ontology-test")
    bootstrap_anchor(chain, anchors, performed_by="test-operator")
    audit = AnchoredAuditChain(chain, anchors)
    store = OntologyObjectStore(project)
    pack_fp = store.register_pack(_pack(), policy=_allow, audit=audit)
    binding_fp = store.register_binding(pack_fp, _binding(), policy=_allow, audit=audit)
    import_id = _import(project, audit, "customers.csv", "C-1,one@example.test\n")
    store.materialize_binding(
        pack_fp, binding_fp, import_id,
        policy=_allow, audit=audit, purpose="account support", retention="90 days",
    )
    try:
        yield {"tmp": tmp_path, "project": project, "store": store, "audit": audit,
               "rules": _Rules(store.project_id)}
    finally:
        chain.close()


def _made(env):
    """A good backup, its manifest, and a fresh restore target with the same project name."""
    backup = env["project"] / "data" / "good.sqlite3"
    manifest = env["store"].create_anchored_backup(
        backup, policy=env["rules"], audit=env["audit"], **GIVEN)
    data = env["tmp"] / "target" / "project" / "data"
    data.mkdir(parents=True)
    shutil.copyfile(backup, data / backup.name)
    shutil.copyfile(env["project"] / "data" / "tabular.sqlite3", data / "tabular.sqlite3")
    env["rules"].asked.clear()
    return backup, manifest, OntologyObjectStore(data.parent), data / backup.name


def _leftovers(directory):
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


@pytest.mark.parametrize("given", MISSING)
def test_verification_of_personal_records_needs_purpose_and_retention(env, given):
    with pytest.raises(OntologyError, match="policy denied"):
        env["store"].verify_integrity(policy=env["rules"], audit=env["audit"], **given)


def test_verification_asks_about_the_callers_values_at_the_stored_classification(env):
    report = env["store"].verify_integrity(policy=env["rules"], audit=env["audit"], **GIVEN)
    assert report["ok"] is True
    assert env["rules"].asked == [
        ("ontology_read", ("store_integrity",), "internal", "ontology_catalog", "project_lifetime"),
        ("ontology_read", ("store_integrity",), "sensitive", GIVEN["purpose"], GIVEN["retention"]),
    ]


@pytest.mark.parametrize("given", MISSING)
def test_backup_of_personal_records_publishes_nothing_without_them(env, given):
    destination = env["project"] / "data" / "refused.sqlite3"
    with pytest.raises(OntologyError, match="policy denied"):
        env["store"].backup(destination, policy=env["rules"], audit=env["audit"], **given)
    assert not destination.exists()
    assert _leftovers(destination.parent) == []


def test_backup_with_them_is_published(env):
    destination = env["project"] / "data" / "ok.sqlite3"
    env["store"].backup(destination, policy=env["rules"], audit=env["audit"], **GIVEN)
    assert destination.is_file()


@pytest.mark.parametrize("given", MISSING)
def test_dependency_manifest_needs_them(env, given):
    destination = env["project"] / "data" / "plain.sqlite3"
    env["store"].backup(destination, policy=_allow, audit=env["audit"])
    env["rules"].asked.clear()
    with pytest.raises(OntologyError, match="policy denied"):
        env["store"].backup_dependency_manifest(
            destination, policy=env["rules"], audit=env["audit"], **given)
    # Refused at the record-level check, before the source rows were asked for.
    assert [row[1] for row in env["rules"].asked] == [("store_backup_dependencies",)] * 2
    assert _leftovers(destination.parent) == []


@pytest.mark.parametrize("given", MISSING)
def test_restore_of_personal_records_publishes_nothing_without_them(env, given):
    _, manifest, target, copy = _made(env)
    with pytest.raises(OntologyError, match="policy denied"):
        target.restore_anchored(copy, dependency_manifest=manifest, policy=env["rules"],
                                audit=env["audit"], **given)
    assert not target.path.exists()
    assert _leftovers(target.path.parent) == []
    # The anchor check passes (catalog labels); the refusal is at the record-level restore check.
    assert env["rules"].asked[-1][:3] == ("ontology_write", ("store_restore",), "sensitive")


def test_anchored_backup_and_restore_carry_the_callers_values(env):
    _, manifest, target, copy = _made(env)
    target.restore_anchored(copy, dependency_manifest=manifest, policy=env["rules"],
                            audit=env["audit"], **GIVEN)
    assert target.path.is_file()
    values = {row[1][0]: row[3:] for row in env["rules"].asked if row[2] == "sensitive"
              and row[1][0] != "store_restore_anchored"}
    expected = (GIVEN["purpose"], GIVEN["retention"])
    assert values == {"store_restore": expected, "store_source_attestation": expected}


@pytest.mark.parametrize("given", MISSING)
def test_anchored_backup_without_them_leaves_no_file(env, given):
    destination = env["project"] / "data" / "anchored.sqlite3"
    with pytest.raises(OntologyError, match="policy denied"):
        env["store"].create_anchored_backup(
            destination, policy=env["rules"], audit=env["audit"], **given)
    assert not destination.exists()


def test_a_caller_with_no_grant_is_refused_before_the_records_are_classified(env, monkeypatch):
    def _never(conn):
        raise AssertionError("classified for a caller with no grant")

    backup = env["project"] / "data" / "plain.sqlite3"
    env["store"].backup(backup, policy=_allow, audit=env["audit"])
    manifest = env["store"].backup_dependency_manifest(backup, policy=_allow, audit=env["audit"])
    monkeypatch.setattr(OntologyObjectStore, "_stored_sensitivity", staticmethod(_never))
    nobody = _Rules(env["store"].project_id, role="nobody")
    fresh = env["project"] / "data" / "other.sqlite3"
    calls = [
        lambda: env["store"].verify_integrity(policy=nobody, audit=env["audit"], **GIVEN),
        lambda: env["store"].backup(fresh, policy=nobody, audit=env["audit"], **GIVEN),
        lambda: env["store"].backup_dependency_manifest(
            backup, policy=nobody, audit=env["audit"], **GIVEN),
        lambda: env["store"].restore(
            backup, dependency_manifest=manifest,
            expected_manifest_sha256=manifest["manifest_sha256"],
            policy=nobody, audit=env["audit"], **GIVEN),
    ]
    for call in calls:
        with pytest.raises(OntologyError, match="policy denied"):
            call()


def test_a_catalog_only_store_needs_nothing_more(tmp_path):
    project = tmp_path / "project"
    (project / "data").mkdir(parents=True)
    audit = AuditChainStore(project / "data" / "audit_chain.sqlite3")
    try:
        store = OntologyObjectStore(project)
        store.register_pack(_pack(), policy=_allow, audit=audit)
        rules = _Rules(store.project_id)
        assert store.verify_integrity(policy=rules, audit=audit)["ok"] is True
        store.backup(project / "data" / "empty.sqlite3", policy=rules, audit=audit)
        assert [row[2] for row in rules.asked] == ["internal", "internal"]
    finally:
        audit.close()


def _refs(*values):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ontology_object_refs(property_sensitivity_json TEXT)")
    conn.executemany("INSERT INTO ontology_object_refs VALUES (?)", [(v,) for v in values])
    return conn


@pytest.mark.parametrize("values, expected", [
    ((), "internal"),
    (('{}',), "internal"),
    (('{"a":"public"}',), "internal"),
    (('{"a":"personal"}', '{"a":"internal"}'), "personal"),
    (('{"a":"personal"}', '{"a":"sensitive"}'), "sensitive"),
    # Anything unreadable or unrecognised is not assumed to be harmless.
    (('{"a":"secret"}',), "sensitive"),
    (('{"a":["personal"]}',), "sensitive"),
    (('["personal"]',), "sensitive"),
    (('not json',), "sensitive"),
    ((None,), "sensitive"),
])
def test_stored_classification(values, expected):
    conn = _refs(*values)
    try:
        assert OntologyObjectStore._stored_sensitivity(conn) == expected
    finally:
        conn.close()


def test_a_missing_table_counts_as_sensitive():
    conn = sqlite3.connect(":memory:")
    try:
        assert OntologyObjectStore._stored_sensitivity(conn) == "sensitive"
    finally:
        conn.close()


@pytest.fixture
def discards(monkeypatch):
    """Record, at each discard of a staged copy, whether SQLite still had that file open.

    Windows cannot delete an open file, so a discard before the close leaves the copy behind
    there while passing on Linux. This makes the ordering visible on every platform.
    """
    opened, seen = [], []
    real_connect, real_discard = sqlite3.connect, store_module._discard_staged_copy

    def _connect(database, *args, **kwargs):
        conn = real_connect(database, *args, **kwargs)
        opened.append((str(database), conn))
        return conn

    def _is_open(conn):
        try:
            conn.total_changes
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return False
        return True

    def _discard(path):
        still_open = any(path.name in name and _is_open(conn) for name, conn in opened)
        seen.append((path.name, still_open))
        real_discard(path)

    monkeypatch.setattr(sqlite3, "connect", _connect)
    monkeypatch.setattr(store_module, "_discard_staged_copy", _discard)
    return seen


def _staged_operations(env):
    """Each operation that works on a staged copy, with the folder the copy is made in."""
    backup, manifest, target, copy = _made(env)
    source = env["project"] / "data"
    return {
        "backup": (source, lambda policy: env["store"].backup(
            source / "refused.sqlite3", policy=policy, audit=env["audit"])),
        "manifest": (source, lambda policy: env["store"].backup_dependency_manifest(
            backup, policy=policy, audit=env["audit"])),
        "restore": (target.path.parent, lambda policy: target.restore(
            copy, dependency_manifest=manifest,
            expected_manifest_sha256=manifest["manifest_sha256"],
            policy=policy, audit=env["audit"])),
    }


@pytest.mark.parametrize("operation", ["backup", "manifest", "restore"])
def test_a_refused_copy_is_closed_before_it_is_discarded(env, discards, operation):
    folder, call = _staged_operations(env)[operation]
    discards.clear()
    with pytest.raises(OntologyError, match="policy denied"):
        call(env["rules"])  # no purpose or retention
    assert discards and [still_open for _, still_open in discards] == [False] * len(discards)
    assert _leftovers(folder) == []


@pytest.mark.parametrize("operation", ["backup", "manifest", "restore"])
@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_an_unlisted_failure_leaves_no_staged_copy(env, discards, monkeypatch, operation, failure):
    folder, call = _staged_operations(env)[operation]
    discards.clear()

    def _fail(conn):
        raise failure("stopped while the copy was staged")

    monkeypatch.setattr(OntologyObjectStore, "_verify_connection_integrity", staticmethod(_fail))
    with pytest.raises(failure):
        call(_allow)
    assert discards and [still_open for _, still_open in discards] == [False] * len(discards)
    assert _leftovers(folder) == []

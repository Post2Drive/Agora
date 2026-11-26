"""The ontology backup manifest digest anchored in the audit chain."""

from __future__ import annotations

import shutil

import pytest

from agora.audit_anchor import (
    AnchorRequiredError, AnchorStore, AnchoredAuditChain, bootstrap_anchor,
)
from agora.audit_chain import AuditChainStore
from agora.ontology import OntologyError, OntologyObjectStore
from test_ontology_store import _allow, _binding, _import, _pack, _resealed

PREFIX = "ontology-backup-anchor-"


@pytest.fixture
def env(tmp_path):
    """A source-backed store, an anchored audit outside the project, and a restore target."""
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
               "chain": chain, "anchors": anchors}
    finally:
        chain.close()


def _backup(env, name="one.sqlite3"):
    path = env["project"] / "data" / name
    return path, env["store"].create_anchored_backup(path, policy=_allow, audit=env["audit"])


def _target(env, backup_path):
    data = env["tmp"] / "target" / "project" / "data"
    data.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(backup_path, data / backup_path.name)
    shutil.copyfile(env["project"] / "data" / "tabular.sqlite3", data / "tabular.sqlite3")
    return OntologyObjectStore(data.parent), data / backup_path.name


def _restore(env, target, copy, manifest, policy=_allow, audit=None):
    return target.restore_anchored(
        copy, dependency_manifest=manifest, policy=policy,
        audit=env["audit"] if audit is None else audit,
    )


def _refused(env, target, copy, manifest, match, **kwargs):
    with pytest.raises(OntologyError, match=match):
        _restore(env, target, copy, manifest, **kwargs)
    assert not target.path.exists()


def _anchor_events(env):
    return env["chain"].db.execute(
        "SELECT COUNT(*) FROM audit_events WHERE event_id LIKE ?", (PREFIX + "%",)
    ).fetchone()[0]


def test_backup_digest_is_recorded_unredacted_and_restore_uses_it(env):
    path, manifest = _backup(env)
    event = env["audit"].find_event(PREFIX + manifest["manifest_sha256"])
    assert event["manifest_hash"] == manifest["manifest_sha256"]
    assert event["backup_hash"] == manifest["ontology_backup"]["sha256"]
    assert event["subject_id"] == "ontology-test-operator"
    assert event["resource_ids"] == ["project:project"]
    target, copy = _target(env, path)
    assert _restore(env, target, copy, manifest) == target.path
    assert target.path.read_bytes() == path.read_bytes()


def test_unanchored_manifest_is_refused(env):
    path = env["project"] / "data" / "plain.sqlite3"
    env["store"].backup(path, policy=_allow, audit=env["audit"])
    manifest = env["store"].backup_dependency_manifest(path, policy=_allow, audit=env["audit"])
    target, copy = _target(env, path)
    _refused(env, target, copy, manifest, "no anchored ontology backup")


def test_resealed_manifest_is_refused(env):
    path, manifest = _backup(env)
    forged = _resealed({**manifest, "created_at": "2000-01-01T00:00:00Z"})["dependency_manifest"]
    target, copy = _target(env, path)
    _refused(env, target, copy, forged, "not the newest anchored")


def test_superseded_backup_is_refused_and_newest_restores(env):
    old_path, old = _backup(env)
    new_path, new = _backup(env, "two.sqlite3")
    target, old_copy = _target(env, old_path)
    _refused(env, target, old_copy, old, "not the newest anchored")
    _, new_copy = _target(env, new_path)
    assert _restore(env, target, new_copy, new) == target.path


def test_changed_backup_bytes_are_refused(env):
    path, manifest = _backup(env)
    target, copy = _target(env, path)
    copy.write_bytes(copy.read_bytes() + b"x")
    _refused(env, target, copy, manifest, "backup bytes do not match")


def test_anchor_for_another_project_is_ignored(env):
    path, manifest = _backup(env)
    other = env["tmp"] / "live" / "other"
    (other / "data").mkdir(parents=True)
    other_store = OntologyObjectStore(other)
    other_store.register_pack(_pack(), policy=_allow, audit=env["audit"])
    other_store.create_anchored_backup(
        other / "data" / "b.sqlite3", policy=_allow, audit=env["audit"])
    target, copy = _target(env, path)
    assert _restore(env, target, copy, manifest) == target.path


@pytest.mark.parametrize("change", [
    {"event_type": "something_else"}, {"decision": "deny"}, {"manifest_hash": "0" * 64},
])
def test_malformed_newer_anchor_does_not_fall_back(env, change):
    path, manifest = _backup(env)
    event = {"event_id": PREFIX + "f" * 64, "event_type": "ontology_backup_anchored",
             "decision": "allow", "manifest_hash": "f" * 64,
             "resource_ids": ["project:project"]}
    env["audit"].append({**event, **change})
    target, copy = _target(env, path)
    _refused(env, target, copy, manifest, "not well formed")


def test_chain_ahead_of_anchor_is_refused(env):
    path, manifest = _backup(env)
    target, copy = _target(env, path)
    env["chain"].append({"event_id": "unanchored-tail"})
    with pytest.raises(AnchorRequiredError, match="unanchored_tail"):
        _restore(env, target, copy, manifest)
    assert not target.path.exists()


def test_anchor_reader_itself_rejects_unanchored_chain(env):
    _backup(env)
    env["chain"].append({"event_id": "unanchored-tail"})
    with pytest.raises(OntologyError, match="not cleanly anchored"):
        env["store"]._newest_anchored_manifest_hash(env["audit"])


@pytest.mark.parametrize("which", ["backup", "restore"])
def test_plain_audit_chain_is_refused_even_when_anchoring_is_relaxed(env, monkeypatch, which):
    from agora import protection
    path, manifest = _backup(env)
    target, copy = _target(env, path)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    with pytest.raises(OntologyError, match="requires an anchored audit writer"):
        if which == "backup":
            env["store"].create_anchored_backup(
                env["project"] / "data" / "x.sqlite3", policy=_allow, audit=env["chain"])
        else:
            _restore(env, target, copy, manifest, audit=env["chain"])
    assert not target.path.exists()
    assert not (env["project"] / "data" / "x.sqlite3").exists()


@pytest.mark.parametrize("subject", [None, "", "  ", "unknown"])
def test_unidentified_actor_cannot_anchor(env, subject):
    def policy(operation, resource):
        decision = dict(_allow(operation, resource))
        if subject is None:
            decision.pop("subject_id")
        else:
            decision["subject_id"] = subject
        return decision
    path = env["project"] / "data" / "x.sqlite3"
    with pytest.raises(OntologyError, match="principal-bound actor"):
        env["store"].create_anchored_backup(path, policy=policy, audit=env["audit"])
    assert not path.exists()
    assert _anchor_events(env) == 0


def _deny_sensitive_write(operation, resource):
    if operation == "ontology_write" and resource["source_sensitivity"] == "sensitive":
        return {**_allow(operation, resource), "decision": "deny", "reason": "role_not_permitted"}
    return _allow(operation, resource)


def test_anchoring_needs_sensitive_write_even_without_source_content(env):
    empty = env["tmp"] / "live" / "empty"
    (empty / "data").mkdir(parents=True)
    store = OntologyObjectStore(empty)
    store.register_pack(_pack(), policy=_allow, audit=env["audit"])
    path = empty / "data" / "x.sqlite3"
    with pytest.raises(OntologyError, match="policy denied"):
        store.create_anchored_backup(path, policy=_deny_sensitive_write, audit=env["audit"])
    assert not path.exists()
    assert _anchor_events(env) == 0


def test_missing_live_store_is_not_recreated_or_anchored(env):
    path, _ = _backup(env)
    missing = env["tmp"] / "lost" / "project"
    (missing / "data").mkdir(parents=True)
    store = OntologyObjectStore(missing)
    with pytest.raises(OntologyError, match="existing live ontology store"):
        store.create_anchored_backup(
            missing / "data" / "x.sqlite3", policy=_allow, audit=env["audit"])
    assert not store.path.exists()
    assert _anchor_events(env) == 1


@pytest.mark.parametrize("error", [OSError("disk"), KeyboardInterrupt()])
def test_failed_anchor_removes_the_new_backup(env, monkeypatch, error):
    real = env["audit"].append

    def append(event, **kwargs):
        if event["event_id"].startswith(PREFIX):
            raise error
        return real(event, **kwargs)

    monkeypatch.setattr(env["audit"], "append", append)
    path = env["project"] / "data" / "x.sqlite3"
    expected = OntologyError if isinstance(error, Exception) else KeyboardInterrupt
    with pytest.raises(expected):
        env["store"].create_anchored_backup(path, policy=_allow, audit=env["audit"])
    assert not path.exists()
    assert _anchor_events(env) == 0


def test_existing_destination_is_never_removed(env):
    path = env["project"] / "data" / "keep.sqlite3"
    path.write_bytes(b"keep")
    with pytest.raises(OntologyError, match="already exists"):
        env["store"].create_anchored_backup(path, policy=_allow, audit=env["audit"])
    assert path.read_bytes() == b"keep"


def test_unauthorized_restore_learns_nothing_about_anchors(env):
    path, manifest = _backup(env)
    target, copy = _target(env, path)
    _refused(env, target, copy, manifest, "policy denied", policy=_deny_sensitive_write)

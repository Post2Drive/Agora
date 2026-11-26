"""Stored, audited decision-cell project record. Synthetic principals only."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from agora.audit_anchor import AnchorStore, AnchoredAuditChain, bootstrap_anchor
from agora.audit_chain import AuditChainStore
from agora.decision_cell import (
    Option, OptionRequest, ProjectRecord, ProjectRecordError, StudyState,
    load_project_record, request_project_option, write_project_record,
)
from agora.decision_cell import project_store as ps
from agora.principal import SyntheticFixtureAdapter

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
EXP = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fx(subject, roles=("approver",), **kw):
    base = {"subject_id": subject, "tenant_id": "t1", "project_ids": ["p1"], "roles": list(roles),
            "assurance": "HIGH", "expires_at": EXP}
    base.update(kw)
    return base


AD = SyntheticFixtureAdapter({
    "owner": _fx("owner"), "delegate": _fx("dee"), "second": _fx("sam"),
    "owner_operator": _fx("owner", ["operator"]),
    "owner_low": _fx("owner", assurance="STANDARD"),
    "outsider": _fx("owner", project_ids=["p2"]),
    "other_tenant": _fx("owner", tenant_id="t2"),
})
OWNER = AD.issue("owner")
RECORD = ProjectRecord("p1", "t1", "owner")


@pytest.fixture
def audit(tmp_path):
    chain = AuditChainStore(tmp_path / "audit.db")
    anchors = AnchorStore(tmp_path / "audit.anchor", "c1")
    bootstrap_anchor(chain, anchors, performed_by="test")
    writer = AnchoredAuditChain(chain, anchors)
    yield writer
    writer.close()


def write(audit, record=RECORD, expected=0, principal=OWNER):
    return write_project_record(principal, record, expected_version=expected, audit=audit, now=NOW)


def load(audit, tenant="t1", project="p1"):
    return load_project_record(tenant_id=tenant, project_id=project, audit=audit)


def events(audit):
    import json
    return [json.loads(r[0]) for r in audit.chain.db.execute("SELECT event_json FROM audit_events ORDER BY seq")]


def refused(code, call):
    with pytest.raises(ProjectRecordError) as caught:
        call()
    assert caught.value.code == code, str(caught.value)


def test_nothing_stored_reads_as_none(audit):
    assert load(audit) is None


def test_create_and_update_round_trip_with_audited_hashes(audit):
    first = write(audit)
    changed = replace(RECORD, delegate_subject_ids=frozenset({"dee"}),
                      second_approver_subject_id="sam", requires_second_approval=True)
    second = write(audit, changed, expected=1)
    assert (first.version, second.version) == (1, 2)
    assert load(audit) == second and second.record == changed
    assert [e["record_hash"] for e in events(audit)] == [first.record_hash, second.record_hash]
    assert audit.verify()["valid"]
    assert load(audit, tenant="t2") is None and load(audit, project="p2") is None


@pytest.mark.parametrize("who", [None, "owner_operator", "owner_low", "outsider", "other_tenant"])
def test_writes_need_a_high_assurance_approver_of_the_project(audit, who):
    principal = AD.issue(who) if who else None
    refused("NOT_PERMITTED", lambda: write(audit, principal=principal))
    assert load(audit) is None
    assert [e["decision"] for e in events(audit)] == ["deny"]


def test_a_creator_cannot_appoint_someone_else_as_owner(audit):
    refused("NOT_OWNER", lambda: write(audit, replace(RECORD, owner_subject_id="dee")))
    assert load(audit) is None


@pytest.mark.parametrize("who", ["delegate", "second"])
def test_only_the_stored_owner_can_change_the_record(audit, who):
    write(audit, replace(RECORD, delegate_subject_ids=frozenset({"dee"}), second_approver_subject_id="sam"))
    intruder = AD.issue(who)
    # Claiming ownership in the new version must not grant the right to write it.
    takeover = ProjectRecord("p1", "t1", intruder.subject_id)
    refused("NOT_OWNER", lambda: write(audit, takeover, expected=1, principal=intruder))
    refused("NOT_OWNER", lambda: write(audit, RECORD, expected=1, principal=intruder))
    assert load(audit).version == 1


def test_owner_cannot_be_changed(audit):
    write(audit)
    refused("OWNER_IMMUTABLE", lambda: write(audit, replace(RECORD, owner_subject_id="dee"), expected=1))


@pytest.mark.parametrize("expected", [0, 2, -1, True, "1"])
def test_stale_or_malformed_expected_version_is_refused(audit, expected):
    write(audit)
    refused("VERSION_CONFLICT", lambda: write(audit, expected=expected))
    assert load(audit).version == 1


def test_a_concurrent_write_of_the_same_version_is_a_conflict(audit, monkeypatch):
    write(audit)
    stale = load(audit)
    write(audit, replace(RECORD, delegate_subject_ids=frozenset({"dee"})), expected=1)
    monkeypatch.setattr(ps, "load_project_record", lambda **kw: stale)  # the check ran before the other commit
    refused("VERSION_CONFLICT", lambda: write(audit, expected=1))
    monkeypatch.undo()
    assert load(audit).record.delegate_subject_ids == frozenset({"dee"})


@pytest.mark.parametrize("change", [
    {"owner_subject_id": " owner"},
    {"delegate_subject_ids": "dee"},
    {"delegate_subject_ids": {"dee"}},
    {"delegate_subject_ids": frozenset({""})},
    {"delegate_subject_ids": frozenset({"dee "})},
    {"delegate_subject_ids": frozenset({"owner"})},
    {"second_approver_subject_id": "owner"},
    {"second_approver_subject_id": ""},
    {"requires_second_approval": True},
    {"requires_second_approval": 1, "second_approver_subject_id": "sam"},
])
def test_invalid_records_are_refused(audit, change):
    refused("RECORD_INVALID", lambda: write(audit, replace(RECORD, **change)))
    assert load(audit) is None


def _two_versions(audit):
    write(audit, replace(RECORD, delegate_subject_ids=frozenset({"dee"})))
    write(audit, expected=1)  # removes the delegate


def _raw(audit, sql, *args):
    db = audit.chain.db
    db.execute("DROP TRIGGER protect_dc_project_record_update")
    db.execute("DROP TRIGGER protect_dc_project_record_delete")
    db.execute(sql, args)
    for name, statement in ps._SCHEMA.items():
        if name != ps.TABLE:
            db.execute(statement)
    db.commit()


@pytest.mark.parametrize("sql", [
    f"DELETE FROM {ps.TABLE} WHERE version=2",  # roll back to the older delegate list
    f"UPDATE {ps.TABLE} SET body_json=replace(body_json,'\"owner\"','\"dee\"') WHERE version=2",
    f"UPDATE {ps.TABLE} SET project_id='p9' WHERE version=2",
    f"INSERT INTO {ps.TABLE} VALUES ('t1','p1',3,'{{}}','forged')",
])
def test_tampered_rows_stop_reads_and_writes(audit, sql):
    _two_versions(audit)
    _raw(audit, sql)
    refused("STORE_INCONSISTENT", lambda: load(audit))
    refused("STORE_INCONSISTENT", lambda: write(audit, expected=2))


def test_dropped_table_is_not_read_as_empty_or_recreated(audit):
    write(audit)
    audit.chain.db.execute(f"DROP TABLE {ps.TABLE}")
    audit.chain.db.commit()
    refused("STORE_INCONSISTENT", lambda: load(audit))
    refused("STORE_INCONSISTENT", lambda: write(audit))


def test_altered_schema_is_refused(audit):
    write(audit)
    audit.chain.db.execute("DROP TRIGGER protect_dc_project_record_delete")
    audit.chain.db.commit()
    refused("STORE_SCHEMA", lambda: load(audit))


def test_rows_are_append_only_in_the_database(audit):
    import sqlite3
    write(audit)
    for sql in (f"DELETE FROM {ps.TABLE}", f"UPDATE {ps.TABLE} SET version=9"):
        with pytest.raises(sqlite3.DatabaseError):
            audit.chain.db.execute(sql)
        audit.chain.db.rollback()


def test_unanchored_chain_is_not_read(audit):
    write(audit)
    audit.chain.append({"event_id": "stray", "event_type": "x"})  # bypasses the anchor
    refused("AUDIT_UNANCHORED", lambda: load(audit))


def test_plain_chain_is_refused(audit):
    refused("AUDIT_REQUIRED", lambda: load(audit.chain))
    refused("AUDIT_REQUIRED", lambda: write(audit.chain))


def test_a_failure_during_the_insert_leaves_no_event_and_no_row(audit, monkeypatch):
    write(audit)
    before = events(audit)
    real = ps._checked_rows

    def fail_inside(db, evs):
        if db.in_transaction:
            raise ps.ProjectRecordError("STORE_INCONSISTENT")
        return real(db, evs)

    monkeypatch.setattr(ps, "_checked_rows", fail_inside)
    refused("STORE_INCONSISTENT", lambda: write(audit, expected=1))
    monkeypatch.undo()
    assert events(audit) == before and load(audit).version == 1


def test_the_in_transaction_check_catches_a_row_removed_after_the_first_read(audit, monkeypatch):
    _two_versions(audit)
    stale = load(audit)
    _raw(audit, f"DELETE FROM {ps.TABLE} WHERE version=1")
    monkeypatch.setattr(ps, "load_project_record", lambda **kw: stale)
    refused("STORE_INCONSISTENT", lambda: write(audit, expected=2))
    assert len(events(audit)) == 2


def _ask(audit, principal, option=Option.RERUN_FROM_START, **kw):
    request = OptionRequest(option=option, event_id="ev", reason="why", budget_units=100)
    return request_project_option(principal, request, tenant_id="t1", project_id="p1", audit=audit,
                                  study=StudyState("s1", 5), branch_cost_units=10, now=NOW, **kw)


@pytest.mark.parametrize("option", [Option.IGNORE, Option.RERUN_FROM_START])
def test_without_a_stored_record_everything_is_blocked_and_audited(audit, option):
    result = _ask(audit, OWNER, option)
    assert not result.executable and "project_record_incomplete" in result.failures
    assert events(audit)[-1]["decision"] == "deny" and "record_hash" not in events(audit)[-1]


def test_gate_follows_the_latest_stored_delegates_and_records_the_version(audit):
    delegate = AD.issue("delegate")
    assert "not_designated_approver" in (write(audit) and _ask(audit, delegate)).failures
    granted = write(audit, replace(RECORD, delegate_subject_ids=frozenset({"dee"})), expected=1)
    assert _ask(audit, delegate).executable
    assert events(audit)[-1]["record_hash"] == granted.record_hash
    write(audit, expected=2)
    assert "not_designated_approver" in _ask(audit, delegate).failures


@pytest.mark.parametrize("extra", [{"record": ProjectRecord("p1", "t1", "dee")}, {"record_hash": "a" * 64}])
def test_caller_cannot_supply_the_record(audit, extra):
    refused("RECORD_INVALID", lambda: _ask(audit, AD.issue("delegate"), **extra))


def test_tampered_store_blocks_the_gate_entirely(audit):
    _two_versions(audit)
    _raw(audit, f"DELETE FROM {ps.TABLE} WHERE version=2")
    refused("STORE_INCONSISTENT", lambda: _ask(audit, AD.issue("delegate")))

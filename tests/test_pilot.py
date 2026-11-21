from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from agora.audit_chain import AuditChainStore
from agora.cli import main as cli_main
from agora.pilot import PROJECT_ID, STAGES, default_identities, run_pilot

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


def _events(project):
    c = AuditChainStore(project / "audit" / "chain.sqlite3")
    try:
        return [json.loads(r[0])["event_type"] for r in c.db.execute("SELECT event_json FROM audit_events ORDER BY rowid")]
    finally:
        c.close()


def test_happy_path_runs_every_stage_and_labels_report_synthetic(tmp_path):
    res = run_pilot(tmp_path, now=NOW)
    assert res.status == "completed" and res.engine_invoked is False
    assert [s.step for s in res.steps] == list(STAGES) and all(s.status == "ok" for s in res.steps)
    text = open(res.report_path, encoding="utf-8").read()
    assert "SIMULATED / SYNTHETIC" in text and "engine_invoked=false" in text
    types = _events(tmp_path / PROJECT_ID)
    for needed in ("decision_proposed", "decision_approved", "decision_outcome_recorded"):
        assert needed in types, types
    anchored = [s for s in res.steps if s.step == "audit_verify"][0]
    assert anchored.data["status"] == "anchored_verified"


def _stopped_at(res, step):
    assert res.status == "stopped" and res.stop_message.startswith(f"STOPPED at '{step}'")
    names = [s.step for s in res.steps]
    assert names == list(STAGES)
    i = names.index(step)
    assert res.steps[i].status in {"denied", "failed"}
    assert all(s.status == "ok" for s in res.steps[:i])
    assert all(s.status == "skipped" for s in res.steps[i + 1:])
    assert res.report_path is None


def test_operator_without_role_is_denied_at_import_and_nothing_downstream(tmp_path):
    ids = default_identities(NOW)
    ids["operator"]["roles"] = ["reader"]
    res = run_pilot(tmp_path, now=NOW, identities=ids)
    _stopped_at(res, "import")
    assert not (tmp_path / PROJECT_ID / "decisions.db").exists()


def test_wrong_approver_role_stops_at_approval_with_no_outcome(tmp_path):
    ids = default_identities(NOW)
    ids["approver"]["roles"] = ["reviewer"]
    res = run_pilot(tmp_path, now=NOW, identities=ids)
    _stopped_at(res, "approval")
    assert "decision_approved" not in _events(tmp_path / PROJECT_ID)


def test_expired_reviewer_stops_at_outcome_review(tmp_path):
    ids = default_identities(NOW)
    ids["reviewer"]["expires_at"] = NOW + timedelta(hours=3, minutes=30)
    _stopped_at(run_pilot(tmp_path, now=NOW, identities=ids), "outcome_review")


def test_missing_anchor_fails_closed_before_any_governed_step(tmp_path):
    res = run_pilot(tmp_path, now=NOW, provision_audit=False)
    _stopped_at(res, "provision_audit")
    assert not (tmp_path / PROJECT_ID / "data").exists()


def test_existing_project_is_refused(tmp_path):
    run_pilot(tmp_path, now=NOW)
    with pytest.raises(FileExistsError):
        run_pilot(tmp_path, now=NOW)


def test_cli_pilot_runs_and_stops_with_exit_code(tmp_path, capsys):
    assert cli_main(["pilot", "--workdir", str(tmp_path / "w")]) == 0
    out = capsys.readouterr().out
    assert "COMPLETED" in out and "no simulation run" in out


def test_broken_audit_chain_stops_before_report(tmp_path, monkeypatch):
    from agora.audit_anchor import AnchoredAuditChain
    real, calls = AnchoredAuditChain.verify, []

    def verify(self):  # intact at open time, broken by the final check
        calls.append(1)
        return real(self) if len(calls) == 1 else {"valid": False, "status": "anchor_mismatch"}
    monkeypatch.setattr(AnchoredAuditChain, "verify", verify)
    res = run_pilot(tmp_path, now=NOW)
    _stopped_at(res, "audit_verify")
    assert "anchor_mismatch" in res.stop_message
    assert not (tmp_path / PROJECT_ID / "report").exists()


def test_pilot_module_never_touches_the_simulation_engine():
    import pathlib
    src = pathlib.Path(__import__("agora.pilot", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    assert "agora.sim" not in src and "from .sim" not in src

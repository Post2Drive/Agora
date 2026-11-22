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


# ---- run records (M2 item 7) -------------------------------------------------

def test_completed_run_persists_record_with_imported_bound_decided_reported(tmp_path):
    from agora.pilot import load_run_record
    res = run_pilot(tmp_path, now=NOW)
    rec = load_run_record(tmp_path / PROJECT_ID)
    assert rec["status"] == "completed" and rec["run_kind"] == "operator_synthetic_pilot"
    assert rec["engine_invoked"] is False and rec["validated_prediction_enabled"] is False
    assert rec["mode"] == "exploratory" and rec["data_class"] == "synthetic"
    assert rec["imported"]["import_id"] and rec["imported"]["rows"] == 3
    assert rec["bound"]["instances"] == 3
    assert rec["decided"]["decision_id"] == "decision-synthetic-001" and rec["decided"]["version"] >= 1
    assert len(rec["outcome_refs"]) == 1
    assert rec["audit_ref"]["status"] == "anchored_verified" and rec["audit_ref"]["head_hash"]
    assert rec["report_ref"]["label"] == "SIMULATED / SYNTHETIC"
    assert [x["step"] for x in rec["stage_results"]] == list(STAGES)
    assert list(rec["fixture_hashes"].values())[0].startswith("sha256:")
    assert "U001" not in json.dumps(rec)  # no raw rows
    assert res.status == "completed"


def test_denied_run_persists_denied_record_with_skipped_stages(tmp_path):
    from agora.pilot import load_run_record
    ids = default_identities(NOW)
    ids["approver"]["roles"] = ["reviewer"]
    run_pilot(tmp_path, now=NOW, identities=ids)
    rec = load_run_record(tmp_path / PROJECT_ID)
    assert rec["status"] == "denied" and rec["report_ref"] is None and rec["outcome_refs"] == []
    results = {x["step"]: x["result"] for x in rec["stage_results"]}
    assert results["approval"] == "denied" and results["outcome_record"] == "skipped"


def test_run_record_is_never_overwritten_and_load_fails_closed(tmp_path):
    import pytest as _p
    from agora.pilot import _write_run_record, load_run_record
    run_pilot(tmp_path, now=NOW)
    project = tmp_path / PROJECT_ID
    with _p.raises(FileExistsError):
        _write_run_record(project, status="completed", started=NOW, steps=[], ctx={},
                          csv_path=project / "synthetic_units.csv", report=None)
    path = project / "run_record.json"
    good = json.loads(path.read_text())
    for patch in ({"engine_invoked": True}, {"validated_prediction_enabled": True}, {"record_version": 2}):
        path.write_text(json.dumps({**good, **patch}))
        with _p.raises(ValueError):
            load_run_record(project)


def test_loader_rejects_missing_mistyped_nonsynthetic_and_bad_hash(tmp_path):
    import pytest as _p
    from agora.pilot import load_run_record
    run_pilot(tmp_path, now=NOW)
    project = tmp_path / PROJECT_ID
    path = project / "run_record.json"
    good = json.loads(path.read_text())
    load_run_record(project)  # a good record loads
    bad = [{"data_class": "real"}, {"run_id": 5}, {"stage_results": [{"step": "x"}]},
           {"fixture_hashes": {"a.csv": "sha256:xyz"}}, {"fixture_hashes": {}},
           {"record_version": True}]
    for patch in bad:
        path.write_text(json.dumps({**good, **patch}))
        with _p.raises(ValueError):
            load_run_record(project)
    for key in ("audit_ref", "imported", "status"):
        broken = {k: v for k, v in good.items() if k != key}
        path.write_text(json.dumps(broken))
        with _p.raises(ValueError):
            load_run_record(project)
    path.write_text("[]")
    with _p.raises(ValueError):
        load_run_record(project)


def test_nonempty_workdir_is_refused_and_left_untouched(tmp_path):
    import pytest as _p
    (tmp_path / "unrelated.txt").write_text("keep")
    with _p.raises(FileExistsError):
        run_pilot(tmp_path, now=NOW)
    assert [p.name for p in tmp_path.iterdir()] == ["unrelated.txt"]
    f = tmp_path.parent / (tmp_path.name + "-file")
    f.write_text("x")
    with _p.raises(FileExistsError):
        run_pilot(f, now=NOW)

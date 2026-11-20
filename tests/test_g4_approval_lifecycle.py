import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from agora.llm.base import LLMConfig
from agora.report import writer
from agora.validation.approval import report_scope
from agora.validation.registry import add_entry, list_entries, require_approval, transition_entry
from conftest import make_project


def _evidence(**overrides):
    row = {
        "registry_id": "validation-001",
        "domain": "consumer research",
        "use_case": "residential sampling uptake",
        "target": "7-day sample registration",
        "population": "Guntur apartment residents aged 18+",
        "geography": "Guntur, Andhra Pradesh, India",
        "horizon": "12 simulated days; evaluation holdout 2026-Q3",
        "data_provenance": {"dataset_id": "ds-01", "source_hashes": {"validation-1": "a" * 64}},
        "holdout_design": {"protocol_fingerprint": "b" * 64, "n_train": 100, "n_test": 40},
        "baselines": {"id": "base-01", "description": "Historical mean"},
        "metrics": {"mae": 0.12},
        "thresholds": {"mae": {"operator": "max", "value": 0.2}},
        "results": {"threshold_assessment": {"overall": "pass", "metrics": {"mae": {"status": "pass"}}}},
        "uncertainty": {"mae_ci95": [0.08, 0.16]},
        "model_version": "mock:unit-test",
        "config_hash": "c" * 64,
        "limitations": ["Single geography"],
        "approved_claims": [],
        "reviewer": "Evaluation owner",
    }
    row.update(overrides)
    return row


def _advance(path, registry_id="validation-001", *, expiry=None, claims=None):
    for state in ("protocol_drafted", "data_reviewed", "evaluation_pending"):
        transition_entry(path, registry_id, state, reviewer="Reviewer", rationale=f"Reviewed {state}",
                         evidence_refs=[f"evidence/{state}.md"])
    return transition_entry(path, registry_id, "passed", reviewer="Approver", rationale="Evidence passed",
                            evidence_refs=["evidence/approval.md"],
                            approved_claims=claims or ["Registration rate is within approved range"],
                            expires_at=expiry or (datetime.now(timezone.utc) + timedelta(days=30)).isoformat())


def test_registry_entry_starts_not_assessed_and_is_immutable(tmp_path):
    path = tmp_path / "validation" / "registry.jsonl"
    row = add_entry(path, _evidence())
    assert row["status"] == "not_assessed"
    assert list_entries(path)[0]["status"] == "not_assessed"
    with pytest.raises(ValueError, match="start at not_assessed"):
        add_entry(path, _evidence(registry_id="bad", status="passed"))
    with pytest.raises(ValueError, match="Duplicate registry_id"):
        add_entry(path, _evidence())


def test_status_transitions_are_ordered_and_review_history_is_append_only(tmp_path):
    path = tmp_path / "validation" / "registry.jsonl"
    add_entry(path, _evidence())
    with pytest.raises(ValueError, match="Invalid status transition"):
        transition_entry(path, "validation-001", "passed", reviewer="R", rationale="skip",
                         evidence_refs=["x"], approved_claims=["claim"],
                         expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    _advance(path)
    rows = list_entries(path)
    assert rows[0]["status"] == "passed"
    review_path = path.with_name("reviews.jsonl")
    events_before = review_path.read_bytes()
    with pytest.raises(ValueError, match="Invalid status transition"):
        transition_entry(path, "validation-001", "failed", reviewer="R", rationale="rewrite",
                         evidence_refs=["x"])
    assert review_path.read_bytes() == events_before


def test_pass_requires_thresholds_and_holdout_provenance(tmp_path):
    path = tmp_path / "validation" / "registry.jsonl"
    add_entry(path, _evidence(results={"threshold_assessment": {"overall": "fail"}}))
    for state in ("protocol_drafted", "data_reviewed", "evaluation_pending"):
        transition_entry(path, "validation-001", state, reviewer="Reviewer", rationale=state,
                         evidence_refs=["evidence.md"])
    with pytest.raises(ValueError, match="threshold_assessment.overall"):
        transition_entry(path, "validation-001", "passed", reviewer="Approver", rationale="No",
                         evidence_refs=["approval.md"], approved_claims=["claim"],
                         expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())


def test_pass_requires_reviewer_evidence_claims_and_future_expiry(tmp_path):
    path = tmp_path / "registry.jsonl"
    add_entry(path, _evidence())
    with pytest.raises(ValueError, match="reviewer"):
        transition_entry(path, "validation-001", "protocol_drafted", reviewer="", rationale="x", evidence_refs=["x"])
    with pytest.raises(ValueError, match="evidence reference"):
        transition_entry(path, "validation-001", "protocol_drafted", reviewer="R", rationale="x", evidence_refs=[])
    for state in ("protocol_drafted", "data_reviewed", "evaluation_pending"):
        transition_entry(path, "validation-001", state, reviewer="R", rationale=state, evidence_refs=["x"])
    with pytest.raises(ValueError, match="approved_claims"):
        transition_entry(path, "validation-001", "passed", reviewer="R", rationale="x", evidence_refs=["x"],
                         expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    with pytest.raises(ValueError, match="future"):
        transition_entry(path, "validation-001", "passed", reviewer="R", rationale="x", evidence_refs=["x"],
                         approved_claims=["claim"], expires_at="2000-01-01T00:00:00+00:00")


def test_require_approval_matches_exact_scope_and_claims(tmp_path):
    path = tmp_path / "registry.jsonl"
    add_entry(path, _evidence())
    _advance(path)
    kwargs = dict(domain="consumer research", use_case="residential sampling uptake",
                  target="7-day sample registration", population="Guntur apartment residents aged 18+",
                  geography="Guntur, Andhra Pradesh, India", horizon="12 simulated days; evaluation holdout 2026-Q3",
                  model_version="mock:unit-test", config_hash="c" * 64,
                  requested_claims=["Registration rate is within approved range"])
    assert require_approval(path, "validation-001", **kwargs)["status"] == "passed"
    for field, value in (("geography", "India"), ("target", "Sales"), ("config_hash", "d" * 64)):
        changed = dict(kwargs); changed[field] = value
        with pytest.raises(PermissionError, match="scope mismatch"):
            require_approval(path, "validation-001", **changed)
    changed = dict(kwargs); changed["requested_claims"] = ["Clinical benefit is proven"]
    with pytest.raises(PermissionError, match="Unapproved claim"):
        require_approval(path, "validation-001", **changed)


def test_expired_approval_is_rejected(tmp_path, monkeypatch):
    import agora.validation.registry as registry_module
    path = tmp_path / "registry.jsonl"
    add_entry(path, _evidence())
    _advance(path)
    real_datetime = registry_module.datetime
    class FutureDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime.now(tz) + timedelta(days=60)
    monkeypatch.setattr(registry_module, "datetime", FutureDateTime)
    kwargs = dict(domain="consumer research", use_case="residential sampling uptake",
                  target="7-day sample registration", population="Guntur apartment residents aged 18+",
                  geography="Guntur, Andhra Pradesh, India", horizon="12 simulated days; evaluation holdout 2026-Q3",
                  model_version="mock:unit-test", config_hash="c" * 64,
                  requested_claims=["Registration rate is within approved range"])
    with pytest.raises(PermissionError, match="expired"):
        require_approval(path, "validation-001", **kwargs)


def test_report_scope_requires_owner_file_and_binds_exact_scenario(tmp_path):
    project = make_project(tmp_path, "scope")
    llm = SimpleNamespace(cfg=LLMConfig(backend="mock"))
    with pytest.raises(PermissionError, match="scope.json"):
        report_scope(project, llm)
    scenario = project / "scenario.yaml"
    digest = hashlib.sha256(scenario.read_bytes()).hexdigest()
    scope = {"scenario_name": "nutrivance-residential-sampling", "scenario_sha256": digest,
             "domain": "consumer research", "use_case": "sampling uptake", "target": "registration",
             "population": "apartment residents", "geography": "Guntur, India", "horizon": "12 days"}
    (project / "validation").mkdir()
    (project / "validation" / "scope.json").write_text(json.dumps(scope), encoding="utf-8")
    assert report_scope(project, llm)["scenario_sha256"] == digest
    scenario.write_text(scenario.read_text(encoding="utf-8") + "\n# modified\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="different scenario"):
        report_scope(project, llm)


def test_validated_report_fails_closed_before_analysis_or_output(tmp_path, monkeypatch):
    project = make_project(tmp_path, "report-gate")
    (project / "validation").mkdir()
    (project / "validation" / "scope.json").write_text("{}", encoding="utf-8")
    class NoAnalysis:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Analysis must not run before the approval gate")
    monkeypatch.setattr(writer, "Analysis", NoAnalysis)
    with pytest.raises(PermissionError, match="scope.json missing"):
        writer.write_report(project, None, mode="validated_prediction", registry_id="missing", claims=["claim"])
    assert not (project / "report" / "report.json").exists()


def test_report_writer_checks_full_approval_then_stays_disabled(tmp_path, monkeypatch):
    from agora.llm.mock import MockBackend
    project = make_project(tmp_path, "full-report-gate")
    (project / "validation").mkdir()
    llm = MockBackend(LLMConfig(backend="mock"))
    scenario = project / "scenario.yaml"
    scope_file = {
        "scenario_name": "nutrivance-residential-sampling",
        "scenario_sha256": hashlib.sha256(scenario.read_bytes()).hexdigest(),
        "domain": "consumer research", "use_case": "sampling uptake",
        "target": "registration", "population": "apartment residents",
        "geography": "Guntur, India", "horizon": "12 days",
    }
    (project / "validation" / "scope.json").write_text(json.dumps(scope_file), encoding="utf-8")
    scope = report_scope(project, llm)
    path = project / "validation" / "registry.jsonl"
    evidence = _evidence(registry_id="report-gate-1", domain=scope["domain"],
                         use_case=scope["use_case"], target=scope["target"],
                         population=scope["population"], geography=scope["geography"],
                         horizon=scope["horizon"], model_version=scope["model_version"],
                         config_hash=scope["config_hash"])
    add_entry(path, evidence)
    _advance(path, registry_id="report-gate-1", claims=["Registration estimate is within the approved range"])

    class NoAnalysis:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Report analysis must remain blocked until separate owner approval")
    monkeypatch.setattr(writer, "Analysis", NoAnalysis)
    with pytest.raises(PermissionError, match="remains disabled"):
        writer.write_report(project, llm, mode="validated_prediction", registry_id="report-gate-1",
                            claims=["Registration estimate is within the approved range"])
    with pytest.raises(PermissionError, match="Unapproved claim"):
        writer.write_report(project, llm, mode="validated_prediction", registry_id="report-gate-1",
                            claims=["Clinical efficacy is proven"])
    assert not (project / "report" / "report.json").exists()



def test_review_history_is_bound_to_immutable_registry_evidence(tmp_path):
    path = tmp_path / "registry.jsonl"
    add_entry(path, _evidence())
    _advance(path)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["metrics"]["mae"] = 999
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="evidence changed"):
        require_approval(path, "validation-001", domain="consumer research",
                         use_case="residential sampling uptake", target="7-day sample registration",
                         population="Guntur apartment residents aged 18+", geography="Guntur, Andhra Pradesh, India",
                         horizon="12 simulated days; evaluation holdout 2026-Q3", model_version="mock:unit-test",
                         config_hash="c" * 64, requested_claims=["Registration rate is within approved range"])
    with pytest.raises(ValueError, match="evidence changed"):
        list_entries(path)


def test_validated_markdown_identifies_scope_and_claims():
    from agora.report.render import to_markdown
    report = {"mode": "validated_prediction", "qualification": {
        "registry_id": "val-123", "reviewer": "Approver", "expires_at": "2027-01-01T00:00:00+00:00",
        "approved_claims": ["Approved claim A"],
        "scope": {"domain": "research", "use_case": "sampling", "target": "registration",
                  "population": "residents", "geography": "Guntur", "horizon": "12 days"}},
        "analysis": {"funnel": [], "choice": None},
        "title": "Qualified report", "generated": "2026-11-19", "model": "mock:test",
        "sections": [], "quotes": {}}
    rendered = to_markdown(report)
    assert rendered.startswith("**VALIDATED PREDICTION")
    assert "val-123" in rendered and "Approved claim A" in rendered and "Guntur" in rendered


def test_validation_cli_add_review_and_list(tmp_path, capsys):
    from agora.cli import main
    project = tmp_path / "cli-project"
    project.mkdir()
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text(json.dumps(_evidence(registry_id="cli-registry")), encoding="utf-8")
    assert main(["validation", "add", str(project), str(evidence_file)]) == 0
    for state in ("protocol_drafted", "data_reviewed", "evaluation_pending", "passed"):
        args = ["validation", "review", str(project), "cli-registry", "--to-status", state,
                "--reviewer", "Reviewer", "--rationale", f"Review {state}",
                "--evidence-ref", f"evidence/{state}.md"]
        if state == "passed":
            args += ["--approved-claim", "Registration rate is within approved range",
                     "--expires-at", (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()]
        assert main(args) == 0
    assert main(["validation", "list", str(project)]) == 0
    out = capsys.readouterr().out
    assert "cli-registry" in out and '"status": "passed"' in out

def test_report_scope_rejects_duplicate_scope_keys(tmp_path):
    project = make_project(tmp_path, "duplicate-scope")
    (project / "validation").mkdir()
    (project / "validation" / "scope.json").write_text(
        '{"domain":"first","domain":"second"}', encoding="utf-8"
    )
    llm = SimpleNamespace(cfg=LLMConfig(backend="mock"))
    with pytest.raises(PermissionError, match="duplicate JSON object key"):
        report_scope(project, llm)


"""Guided synthetic governed pilot: one callable run, fail closed at every gate.

Stages (each recorded as a StepResult; the first denial stops the run):
provision_audit -> import -> bind -> decision -> approval -> outcome_record ->
outcome_review -> report -> audit_verify.

Everything is local and synthetic. Protected mode is always on here:
``require_policy=True`` on import and binding, and a mandatory anchored audit
writer (``require_anchored=True``) on approval and outcome writes. Identities
come from the test-only SyntheticFixtureAdapter and are clearly synthetic.
Nothing is passed to the simulation engine; ``engine_invoked`` is always False.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from agora.audit_anchor import AnchorStore, bootstrap_anchor, open_anchored_audit
from agora.audit_chain import AuditChainStore
from agora.decisions.approval import approve_as, propose
from agora.decisions.outcomes import DecisionOutcomeStore, record_outcome_as, review_outcome_as
from agora.decisions.store import DecisionRecordStore
from agora.ontology import parse_domain_pack
from agora.ontology.binding import load_binding, materialize_instances
from agora.principal import SyntheticFixtureAdapter, principal_policy
from agora.tabular import ingest_csv

PROJECT_ID = "synthetic-pilot"
OPERATOR_ID, APPROVER_ID, REVIEWER_ID = "synthetic-operator-1", "synthetic-approver-1", "synthetic-reviewer-1"
CHAIN_ID = "synthetic-pilot-chain"
STAGES = ("provision_audit", "import", "bind", "decision", "approval",
          "outcome_record", "outcome_review", "audit_verify", "report")

SYNTHETIC_CSV = "unit_id,region,weekly_visits\nU001,north,120\nU002,south,95\nU003,east,143\n"


def _pack():
    return parse_domain_pack({
        "pack_id": "synthetic-pilot-pack", "schema_version": "1.0.0",
        "object_types": [{"type_id": "sp:Unit", "version": "1.0.0", "name": "Unit",
                         "description": "Synthetic unit", "identity_strategy": "record_key",
                         "properties": ["sp:Unit.id", "sp:Unit.region", "sp:Unit.visits"]}],
        "property_types": [
            {"property_id": "sp:Unit.id", "version": "1.0.0", "name": "ID", "data_type": "identifier",
             "required": True, "nullable": False, "sensitivity": "internal"},
            {"property_id": "sp:Unit.region", "version": "1.0.0", "name": "Region", "data_type": "string",
             "required": True, "nullable": False, "sensitivity": "internal"},
            {"property_id": "sp:Unit.visits", "version": "1.0.0", "name": "Visits", "data_type": "integer",
             "required": True, "nullable": False, "sensitivity": "internal"},
        ],
        "link_types": [], "action_types": [],
    })


def _schema():
    col = lambda n, t, **kw: {"name": n, "type": t, "nullable": False, "sensitivity": "internal", **kw}  # noqa: E731
    return {"schema_id": "synthetic-pilot-units", "schema_version": "1.0.0",
            "dataset_name": "synthetic_pilot_units",
            "columns": [col("unit_id", "string", primary_key=True), col("region", "string"),
                        col("weekly_visits", "integer")]}


def _binding():
    return load_binding({
        "binding_id": "sp.unit.v1", "binding_version": "1.0.0",
        "object_type_id": "sp:Unit", "object_type_version": "1.0.0",
        "dataset_id": "synthetic_pilot_units", "schema_id": "synthetic-pilot-units", "schema_version": "1.0.0",
        "column_map": {"unit_id": "sp:Unit.id", "region": "sp:Unit.region", "weekly_visits": "sp:Unit.visits"},
        "identity": {"strategy": "record_key", "primary_key_column": "unit_id"},
        "property_sensitivity": {"sp:Unit.id": "internal", "sp:Unit.region": "internal",
                                 "sp:Unit.visits": "internal"},
    })


def default_identities(now: datetime) -> dict[str, dict[str, Any]]:
    """Fixed, clearly synthetic identities; expiry is relative to the run clock."""
    def fx(sid: str, roles: list[str]) -> dict[str, Any]:
        return {"subject_id": sid, "tenant_id": "synthetic-tenant", "project_ids": [PROJECT_ID],
                "roles": roles, "assurance": "HIGH", "expires_at": now + timedelta(days=1)}
    return {"operator": fx(OPERATOR_ID, ["operator"]), "approver": fx(APPROVER_ID, ["approver"]),
            "reviewer": fx(REVIEWER_ID, ["reviewer"])}


@dataclass
class StepResult:
    step: str
    status: str  # ok | denied | failed | skipped
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PilotResult:
    status: str  # completed | stopped
    project: str
    steps: list[StepResult]
    stop_message: str | None = None
    engine_invoked: bool = False  # structural: this module never calls the engine
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Stop(Exception):
    pass


def _decision_record(import_id: str, moment: datetime) -> dict[str, Any]:
    return {
        "decision_id": "decision-synthetic-001", "version": 1, "project_scope": {"project_id": PROJECT_ID},
        "status": "draft", "statement": "Choose a synthetic pilot cohort", "alternatives": ["A", "B"],
        "evidence_refs": [{"kind": "import", "import_id": import_id, "dataset_id": "synthetic_pilot_units"}],
        "rationale": "Synthetic evidence only.", "assumptions": ["Synthetic data"],
        "uncertainty": ["Invented sample"], "outcome_measures": ["observed weekly visits"],
        "proposer": OPERATOR_ID, "reviewer": REVIEWER_ID,
        "created_at": _stamp(moment), "updated_at": _stamp(moment), "approval_method": "manual",
        "review_date": (moment + timedelta(days=30)).strftime("%Y-%m-%d"),
    }


def _write_report(project: Path, ctx: Mapping[str, Any]) -> Path:
    out = project / "report" / "pilot_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join([
        "# Synthetic governed pilot report",
        "",
        "**SIMULATED / SYNTHETIC — invented data, not real-world evidence.**",
        "No simulation engine was run (engine_invoked=false). VALIDATED_PREDICTION_ENABLED=False.",
        "",
        f"- Import: `{ctx['import_id']}` ({ctx['rows']} synthetic rows)",
        f"- Instances bound: {ctx['instances']}",
        f"- Decision: `{ctx['decision_id']}` v{ctx['version']} approved by `{APPROVER_ID}`",
        f"- Observed outcome (synthetic): `{ctx['outcome_id']}`, reviewed by `{REVIEWER_ID}`",
        f"- Audit chain: {ctx['audit_status']} (trust level: local_sidecar)",
        "",
    ]), encoding="utf-8")
    return out


def run_pilot(workdir: str | Path, *, now: datetime | None = None,
              identities: Mapping[str, Mapping[str, Any]] | None = None,
              provision_audit: bool = True) -> PilotResult:
    """Run the whole synthetic governed pipeline once in a NEW project folder."""
    base = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    project = Path(workdir) / PROJECT_ID
    if project.exists():
        raise FileExistsError(f"{project} already exists; use a new empty work directory")
    project.mkdir(parents=True)
    adapter = SyntheticFixtureAdapter(identities or default_identities(base))
    steps: list[StepResult] = []
    ctx: dict[str, Any] = {}

    def run(step: str, fn):
        try:
            data = fn() or {}
        except Exception as exc:  # fail closed: any error is a stop, never a skip
            kind = "denied" if isinstance(exc, PermissionError) or "denied" in str(exc).lower() else "failed"
            steps.append(StepResult(step, kind, f"{type(exc).__name__}: {exc}"))
            raise _Stop(step) from exc
        steps.append(StepResult(step, "ok", data=dict(data)))

    chain_path = project / "audit" / "chain.sqlite3"
    anchor_path = project / "audit_anchor" / "anchor.jsonl"
    csv_path = project / "synthetic_units.csv"
    csv_path.write_text(SYNTHETIC_CSV, encoding="utf-8")
    try:
        def provision():
            if provision_audit:
                chain_path.parent.mkdir(parents=True, exist_ok=True)
                chain = AuditChainStore(chain_path)
                try:
                    bootstrap_anchor(chain, AnchorStore(anchor_path, CHAIN_ID), performed_by="synthetic-maintainer")
                finally:
                    chain.close()
            return {"chain": str(chain_path), "anchor": str(anchor_path)}
        run("provision_audit", provision)

        try:
            ctxmgr = open_anchored_audit(chain_path, anchor_path, CHAIN_ID)
            audit = ctxmgr.__enter__()
        except Exception as exc:
            steps[:] = [x for x in steps if x.step != "provision_audit"]
            steps.append(StepResult("provision_audit", "denied", f"{type(exc).__name__}: {exc}"))
            raise _Stop("provision_audit") from exc
        try:
            op = principal_policy(adapter.issue("operator"), required_role="operator", now=base)

            def do_import():
                r = ingest_csv(project, csv_path, _schema(), data_role="scenario_input",
                               policy=op, audit=audit, require_policy=True)
                ctx["import_id"], ctx["rows"] = r["import_id"], r.get("accepted_rows", r.get("row_count", 3))
                return {"import_id": r["import_id"]}
            run("import", do_import)

            def do_bind():
                inst = materialize_instances(_binding(), _pack(), project, ctx["import_id"],
                                             policy=op, audit=audit, require_policy=True)
                ctx["instances"] = len(inst)
                return {"instances": len(inst)}
            run("bind", do_bind)

            def do_decision():
                decisions = DecisionRecordStore(project / "decisions.db")
                ctx["decisions"] = decisions
                decisions.append(_decision_record(ctx["import_id"], base))
                p = propose(decisions, "decision-synthetic-001", 1, actor=OPERATOR_ID,
                            now=_stamp(base + timedelta(minutes=1)), audit=audit)
                ctx["proposed"] = p
                return {"decision_id": p.decision_id, "status": p.status}
            run("decision", do_decision)

            def do_approve():
                p = ctx["proposed"]
                a = approve_as(ctx["decisions"], p.decision_id, p.version,
                               principal=adapter.issue("approver"), expected_fingerprint=p.fingerprint,
                               expected_scope={"project_id": PROJECT_ID},
                               expected_evidence_refs=p.evidence_refs,
                               now=_stamp(base + timedelta(minutes=2)), audit=audit, require_anchored=True)
                ctx["approved"] = a
                ctx["decision_id"], ctx["version"] = a.decision_id, a.version
                return {"status": a.status, "approver": APPROVER_ID}
            run("approval", do_approve)

            def do_record():
                outcomes_store = DecisionOutcomeStore(ctx["decisions"])
                ctx["outcomes"] = outcomes_store
                a = ctx["approved"]
                out = record_outcome_as(
                    outcomes_store, principal=adapter.issue("operator"), decision_id=a.decision_id,
                    decision_version=a.version, measure="observed weekly visits", observed_value=358,
                    unit="visits", observed_at=_stamp(base + timedelta(hours=2)),
                    measurement_window={"start": _stamp(base + timedelta(minutes=3)),
                                        "end": _stamp(base + timedelta(hours=2))},
                    source_ref={"source_registry_id": "synthetic-source-1", "evidence_id": "synthetic-evidence-1",
                                "content_hash": "sha256:" + "ab" * 32},
                    provenance_class="observed", validation_status="source_verified",
                    now=_stamp(base + timedelta(hours=3)), audit=audit, require_anchored=True)
                ctx["outcome_id"] = out["outcome_id"]
                return {"outcome_id": out["outcome_id"]}
            run("outcome_record", do_record)

            def do_review():
                a = ctx["approved"]
                r = review_outcome_as(ctx["outcomes"], a.decision_id, a.version, ctx["outcome_id"],
                                      principal=adapter.issue("reviewer"), new_state="reviewed",
                                      rationale_code="source_checked", now=_stamp(base + timedelta(hours=4)),
                                      audit=audit, require_anchored=True)
                return {"new_state": r["new_state"], "reviewer": REVIEWER_ID}
            run("outcome_review", do_review)

            def do_verify():
                v = audit.verify()
                ctx["audit_status"] = v["status"]
                if not v["valid"]:
                    raise PermissionError(f"audit chain is not intact: {v['status']}")
                return {"status": v["status"], "sequence": v.get("sequence")}
            run("audit_verify", do_verify)
            run("report", lambda: {"path": str(_write_report(project, ctx))})
        finally:
            ctxmgr.__exit__(None, None, None)
    except _Stop:
        last = steps[-1]
        done = {s.step for s in steps}
        steps.extend(StepResult(s, "skipped", "not run: an earlier gate stopped the pilot")
                     for s in STAGES if s not in done)
        return PilotResult("stopped", str(project), steps,
                           f"STOPPED at '{last.step}' ({last.status}): {last.detail}. "
                           "No later stage was run; nothing reached the simulation engine.")
    finally:
        if ctx.get("decisions") is not None:
            ctx["decisions"].close()
    return PilotResult("completed", str(project), steps, report_path=str(project / "report" / "pilot_report.md"))


def format_result(result: PilotResult) -> str:
    lines = [f"Synthetic governed pilot: {result.status.upper()}"]
    lines += [f"  [{s.status:<7}] {s.step}" + (f" - {s.detail}" if s.detail else "") for s in result.steps]
    if result.stop_message:
        lines.append(result.stop_message)
    if result.report_path:
        lines.append(f"Report (SYNTHETIC, no simulation run): {result.report_path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="agora pilot", description="Run the guided synthetic governed pilot.")
    ap.add_argument("--workdir", required=True, help="new empty directory for this run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = run_pilot(args.workdir)
    print(json.dumps(result.to_dict(), indent=2, default=str) if args.json else format_result(result))
    return 0 if result.status == "completed" else 2


__all__ = ["PilotResult", "StepResult", "run_pilot", "format_result", "main"]

# Operator Runbook — Governed Synthetic Pilot

**Status:** Draft skeleton only; not an executable runbook, rehearsal record, approval or readiness declaration.  
**Assessment base:** `25231d68b6f9d5684b76b6204265cd225cc29449` (21 November 2026)  
**Milestone dependency:** `docs/MILESTONE_OPERATOR_PILOT.md` is not present on this mainline. This file is a provisional status map only; reconcile it with Claude's M2 milestone document when that document is created.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

A green CI run, a draft runbook or a component API does not authorise an operator rehearsal. Only Claude's exact milestone confirmation can declare a milestone reached; owner-only actions require separate explicit approval.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `25231d68` | Evidence / missing item |
|---|---|---|
| One-command install/start | **NOT YET** | No single operator install/start command is documented or verified. |
| Checked-in synthetic dataset | **NOT YET VERIFIED** | The older how-to references `fixtures/pilot.csv`, `fixtures/pilot-schema.yaml` and `fixtures/pilot-binding.yaml`; those exact paths are absent on main. No replacement checked-in dataset has been verified in this review. |
| Guided end-to-end run with per-step results and clear gate-denial stops | **NOT YET** | No single pilot orchestrator/CLI exists. Import, binding, scenario-input, approval and report components remain separate. |
| Anchor and policy checks enabled by default everywhere | **NOT YET** | `require_policy=False` and `require_anchored=False` remain defaults; legacy `policy=None` and optional audit paths remain. |
| Legacy paths removed or test-only | **NOT YET** | Public role-string `approve()` remains; outcome wrappers still delegate to legacy role-string functions; other optional policy/audit paths remain. |
| Readable audit timeline and plain-language chain/anchor verification | **PARTIAL / NOT OPERATOR-READY** | Hash-chain and local-sidecar verification APIs exist; no integrated operator timeline/verification command has been verified. Trust is `local_sidecar`, not independent external anchoring. |
| Backup/restore and tamper drill | **NOT YET** | Design guidance exists; no operator commands, tested procedure or logged drill is evidenced. |
| Minimal reconciliation and held-outcome listing | **NOT YET** | Decision/audit reconciliation (#57) and outcome dependency markers (#60) are specifications only; no queue, worker or held-outcome listing exists. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **PARTIAL** | Provenance contracts and scenario-input run-record fields exist; no M2 operator flow writes and verifies the complete run record end to end. |
| Operator runbook commands executed by a test | **NOT YET** | This skeleton has no executable command set and no test that executes it. |
| Logged dress rehearsal | **NOT YET** | No rehearsal is recorded or authorised by this draft. |

## 3. Existing components (not a complete operator workflow)

- **AVAILABLE — local CSV import CLI:** `agora data import-csv`, `agora data snapshots`, `agora data show` and `agora data rejected`.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PARTIAL — protected policy:** #78/#79 provide a Principal-bound callback and opt-in missing-policy denial; data-boundary defaults remain unprotected.
- **PARTIAL — anchored audit:** #71/#74 wire append points and opt-in gates; legacy optional-audit paths remain.
- **NOT YET — single orchestrator:** no `agora pilot` or governed-pipeline command is present.
- **NOT YET — reconciliation/held outcomes:** no implementation beyond #57/#60 specifications.

Do not execute a component command as though it were the full M2 workflow.

## 4. Future operator sequence — NOT EXECUTABLE

The following headings reserve the runbook structure. Each step must be replaced with exact, tested commands only after the relevant interface exists and Claude's M2 milestone specification is available.

1. **Preflight and installation — NOT YET:** verify supported Python/runtime, one-command install/start, clean local workspace and explicit synthetic-only mode.
2. **Fixture selection — NOT YET:** select the checked-in synthetic dataset and record exact immutable fixture/schema/binding IDs and hashes.
3. **Policy and anchor verification — NOT YET:** verify principal, scope, required policy, anchored writer, chain ID and anchor state before any protected read or write.
4. **Guided import/bind/scenario-input — NOT YET:** run each stage with exact IDs, per-step results and fail-closed stop codes; no simulation engine call.
5. **Decision and principal approval — PARTIAL API ONLY:** use principal-native approval; legacy role-string entry points must first be removed or test-gated and the anchor requirement made default-on.
6. **Audit timeline and verification — NOT YET:** show event sequence, chain verification and anchor comparison in plain language without exposing raw values.
7. **Reconciliation and held outcomes — NOT YET:** list unmatched/held records; no automatic repair without explicit independent approval.
8. **Backup/restore and tamper drill — NOT YET:** document and test copy/restore, anchor continuity, tamper detection and fail-closed recovery.
9. **Run record and report — PARTIAL:** persist and verify the complete provenance envelope; any report must remain exploratory/simulated-labelled and must not call the engine as part of this M2 flow.
10. **Dress rehearsal — NOT YET:** only after the M2 checklist, tested runbook, exact-head CI and separate owner approval; log the exact command, SHA, fixture hashes, stage results, denials and operator sign-off.

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence to record when the runbook becomes executable

Record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper drill outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text.

This skeleton does not declare M1 or M2 reached and does not authorise a rehearsal.

# Operator Runbook — Governed Synthetic Pilot

**Status:** Draft skeleton only; not an executable runbook, rehearsal record, approval or readiness declaration.  
**Assessment base:** `ff736a71ff87335a4133411492c4d7ee975ef035` (22 November 2026).
**Milestone dependency:** the owner-approved scope checklist `docs/MILESTONE_OPERATOR_PILOT.md` and the synthetic fixture specification are merged documentation. This file remains a provisional status map, not an executable runbook or rehearsal authorisation.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

A green CI run, a draft runbook or a component API does not authorise an operator rehearsal. Only Claude's exact milestone confirmation can declare a milestone reached; owner-only actions require separate explicit approval.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `ff736a71` | Evidence / missing item |
|---|---|---|
| One-command install/start | **NOT YET** | `agora pilot --workdir <new-empty-directory>` exists (#88), but it is not a one-command installer/start or clean-checkout setup workflow. |
| Checked-in synthetic dataset | **NOT YET** | #88 embeds `SYNTHETIC_CSV`, schema and binding in `agora/pilot.py`; `fixtures/pilot.csv`, `fixtures/pilot-schema.yaml` and `fixtures/pilot-binding.yaml` remain absent on main. |
| Guided end-to-end run with per-step results and clear gate-denial stops | **AVAILABLE — partial M2 evidence** | #88 merges `agora pilot --workdir`; it reports nine stages, stops at the first denial/failure and marks later stages skipped. Exact-head CI run `44945307064` passed 4/4. It does not persist the M2 run record or use a checked-in fixture set. |
| Anchor and policy checks enabled by default everywhere | **PARTIAL** | #96 removes public policy/anchor opt-outs; #97 removes the unanchored fallback; #99 removes the direct helper override and requires `require_anchored()` for protected denial writes. Low-level decision lifecycle methods still accept optional audit arguments; prove all production service/harness paths supply the anchored writer. `local_sidecar` trust remains limited. |
| Legacy paths removed or test-only | **PARTIAL** | #92 retires public role-string outcome exports; #96 removes public wrapper opt-outs; #97 removes the legacy approval env switch and confines enablement to the test-only module flag. |
| Readable audit timeline and plain-language chain/anchor verification | **PARTIAL / NOT OPERATOR-READY** | #88 includes an `audit_verify` stage in the guided run, but there is no standalone timeline/verification command. Trust remains `local_sidecar`. |
| Backup/restore and tamper drill | **NOT YET** | Design guidance exists; no operator commands, tested procedure or logged drill is evidenced. |
| Minimal reconciliation and held-outcome listing | **PARTIAL** | #100 adds a read-only decision lifecycle/audit detector with chain verification and stable classifications. No anchor check, queue, repair, outcome/review reconciliation or held-outcome listing exists; #60 remains open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **NOT YET** | #88 returns an in-memory `PilotResult`; it does not persist and verify the immutable M2 run-record envelope. |
| Operator runbook commands executed by a test | **NOT YET** | This skeleton has no executable command set and no test that executes it. |
| Logged dress rehearsal | **NOT YET** | No rehearsal is recorded or authorised by this draft. |

## 3. Existing components (not a complete operator workflow)

- **AVAILABLE — local CSV import CLI:** `agora data import-csv`, `agora data snapshots`, `agora data show` and `agora data rejected`.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PROTECTED — policy enforcement:** #96 removes public `require_policy` opt-out kwargs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct helper override and requires an anchored writer for protected denial events.
- **PARTIAL — principal approval:** #80/#84 provide `approve_as()` with server-derived policy inputs; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains.
- **PARTIAL — anchored audit:** #71/#74/#75 wire append points; #96 removes public `require_anchored=False` kwargs, #92 retires public role-string outcome exports, #97 removes the unanchored denial fallback, and #99 validates the policy-denial writer. Trust remains `local_sidecar`; low-level lifecycle and private outcome helpers still have optional audit arguments.
- **AVAILABLE — guided synthetic command:** `agora pilot --workdir <new-empty-directory>` (#88) runs nine stages and stops on first denial without invoking the engine. #94 keeps CLI pilot/data dispatch engine-import-free; fresh-process coverage exercises `--help`, not a complete `--workdir` invocation.
- **PARTIAL — reconciliation / NOT YET — held outcomes:** #100 implements a read-only decision lifecycle detector only. It does not verify the anchor, reconcile outcome/review rows, persist a queue or repair gaps. #60 held-outcome markers/listing remain unimplemented.

Do not execute a component command as though it were the full M2 workflow.

## 4. Future operator sequence — NOT EXECUTABLE

The following headings reserve the runbook structure. Each step must be replaced with exact, tested commands only after the relevant interface exists and Claude's M2 milestone specification is available.

1. **Preflight and installation — NOT YET:** verify supported Python/runtime, one-command install/start, clean local workspace and explicit synthetic-only mode.
2. **Fixture selection — NOT YET:** select the checked-in synthetic dataset and record exact immutable fixture/schema/binding IDs and hashes.
3. **Policy and anchor verification — NOT YET:** verify principal, scope, required policy, anchored writer, chain ID and anchor state before any protected read or write.
4. **Guided import/bind/scenario-input — PARTIAL:** #88 guides import and binding with per-step results and first-denial stop, but does not call `build_scenario_input()`; no simulation-engine call is in scope.
5. **Decision and principal approval — DEFAULT-ON PRINCIPAL PATH:** #80/#84 make `approve_as()` Principal-native; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval environment switch; `approve()` remains disabled by default and can be enabled only through the test-only `agora.protection.LEGACY_APPROVE_ENABLED` module flag. #92 retires the public role-string outcome APIs. #99 closes direct policy-helper bypasses.
6. **Audit timeline and verification — NOT YET:** show event sequence, chain verification and anchor comparison in plain language without exposing raw values.
7. **Reconciliation and held outcomes — PARTIAL:** `agora reconcile --decisions <db> --audit <db>` (#100) lists decision lifecycle/audit gaps read-only; it returns 0 for intact, 1 for detected gaps and 2 when blocked. It does not check the anchor, repair gaps, or cover outcome/review rows. #60 held-outcome listing remains NOT YET.
8. **Backup/restore and tamper drill — NOT YET:** document and test copy/restore, anchor continuity, tamper detection and fail-closed recovery.
9. **Run record and report — PARTIAL:** #88 writes a synthetic-labelled report but does not persist the immutable run-record envelope in `docs/PILOT_RUN_RECORD_FIELDS.md` / `docs/RUN_PROVENANCE_SPEC.md`.
10. **Dress rehearsal — NOT YET:** only after the M2 checklist, tested runbook, exact-head CI and separate owner approval; log the exact command, SHA, fixture hashes, stage results, denials and operator sign-off.

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence to record when the runbook becomes executable

Record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper drill outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text.

This skeleton does not declare M1 or M2 reached and does not authorise a rehearsal.

# M2 — Operator-Usable Synthetic Pilot

**Status:** M2 scope approved by the owner; this checklist remains a planning contract, not an execution authorisation or readiness declaration.  
**Assessment base:** `9031dba2e318f43b64a0b9155e3f44ee65155cdf` (22 November 2026).
**Prerequisite:** M1 PILOT-READY must first be confirmed by Claude in the AI Collaboration Log.  
**Operating boundary:** Local synthetic data and local stores only; no simulation-engine call.

## 1. Objective

Deliver a one-command, operator-usable, deterministic synthetic governance workflow. The operator must be able to install/start locally, select a checked-in synthetic fixture, follow a guided sequence with per-step outcomes, understand every denial/stop, verify the audit chain and local anchor in plain language, inspect held outcomes, and recover from backup/restore or tamper-detection drills.

This milestone demonstrates governance and operator usability only. It does not validate predictive accuracy, demand, sales, causal effects or real-world outcomes.

## 2. Required capabilities and exit evidence

| Requirement | Required behaviour | Exit evidence |
|---|---|---|
| One-command install/start | Clean checkout can install the supported local dependencies and start the synthetic workflow with one documented command; no network identity or external service required. | Exact command executed by a clean-checkout test; supported Python/runtime and failure messages documented. |
| Checked-in synthetic dataset | Fixture, schema and binding are checked in, pinned and invented; exact IDs and content hashes are recorded. | Fixture paths, schema validation, immutable import/manifest IDs and fixture hashes verified by tests. See `docs/SYNTHETIC_PILOT_FIXTURE_SPEC.md`. |
| Guided end-to-end run | Local orchestrator reports each stage, immutable IDs and result; a denied gate stops before the next protected read or write. | Test executes the command and asserts stage order, results, denial codes and absence of later state changes. |
| CLI import boundary | Pilot/data dispatch must not import the simulation engine; engine imports belong only in simulation commands. | Fresh-process tests prove `import agora.cli` and pilot dispatch do not load `agora.sim.engine`; #94 provides the import/help-dispatch proof, with a full `--workdir` subprocess assertion still desirable. |
| Policy and anchor checks by default | **PARTIAL — protected lifecycle entry points now guarded** | #96 removes public opt-outs, #97 removes the unanchored fallback and legacy approval env switch, and #99 removes the direct `require_policy` override and validates denial writers with `require_anchored()`. #109 guards `propose()`, `reject()`, `expire()` and `supersede()` before state mutation when `ANCHOR_REQUIRED=True`; their optional audit annotations do not permit missing/plain writers on the protected path. Principal-first PDP/permission migration and the `local_sidecar` trust limitation remain. |
| Legacy path retirement | **PARTIAL — public outcome roles retired; legacy approval test-only** | #92 retires public role-string outcome exports; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | **IMPLEMENTED COMPONENT — #107** adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>`; merged tests cover selected-decision filtering, ordering, redaction and read-only behaviour. Runbook-command execution test remains outstanding. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | **IMPLEMENTED COMPONENT — #107** adds `agora audit verify --audit <db> --anchor <file> --chain-id <id>` with plain-language verdicts and a `local_sidecar` trust note; tests cover intact, tampered, truncated, missing-anchor and wrong-chain cases. Coordinated rollback of both local files remains an explicit undetectable trust limitation; runbook-command execution test remains outstanding. |
| Backup/restore and tamper drill | Documented local backup/restore preserves chain/anchor continuity; tampering is detected and protected operations stop. | Tests exercise backup, restore, missing/corrupt backup and tamper cases; rehearsal log records outcomes. |
| Minimal reconciliation | **PARTIAL — hardened read-only detector** | #100 provides a read-only `agora reconcile` detector for decision lifecycle/approval rows; #104 validates immutable source metadata, expected audit operation/exact resource IDs and partial-open cleanup. It still does not verify the anchor, cover outcome/review rows, persist a queue or repair gaps. |
| Held-outcome listing | **PARTIAL — read-only list exists** | #102 adds `agora outcomes held --decisions <db>` for disputed, never-reviewed, invalid-history and orphan-review cases, with opaque IDs/stable reason codes and exit 0/1/2; #106 normalizes connection-open SQLite errors to `STORE_UNREADABLE` / exit 2. It does not inspect source-hash changes, create dependency markers or propagate holds through dependent artifacts. |
| Run records | Persist and verify the immutable envelope defined by `docs/RUN_PROVENANCE_SPEC.md`; do not call the simulation engine. | Tests assert exact import ID, fixture/schema/binding/manifest hashes, ontology and policy fingerprints, repository SHA and synthetic/exploratory label. The operator-specific field mapping is specified in `docs/PILOT_RUN_RECORD_FIELDS.md`. |
| Operator runbook | Every command and expected output/stop condition in `docs/OPERATOR_RUNBOOK.md` is exercised by an automated test. | Test loads or validates the runbook command inventory and executes each safe local synthetic command. |
| Logged dress rehearsal | A separately owner-approved local synthetic rehearsal records command, SHA, fixture hashes, stage results, denial stops, audit verification, backup/restore/tamper outcomes and operator sign-off. | Verified Notion log entry with exact evidence and Claude's milestone confirmation. |

## 3. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Required implementation order

1. Complete and confirm M1 using `docs/MILESTONE_PILOT_READY.md`; #92 retires public outcome-role exports, #94 closes the CLI engine-import boundary, #96 removes public policy/anchor opt-out kwargs, #97 removes the legacy approval env switch/unanchored fallback, #99 closes direct policy-helper bypasses, #100 adds the read-only decision/audit detector; #104 hardens immutable source-metadata checks and partial-open cleanup; #102 adds the read-only held-outcome list; #106 makes held-list connection-open failures fail closed; #107 adds read-only audit timeline and chain/anchor verification components; and #109 closes the remaining decision-lifecycle pre-mutation anchor bypass. Outcome dependency markers/manual-recovery evidence and the remaining M1 exit gates remain open.
2. Add and verify the synthetic fixture set using `docs/SYNTHETIC_PILOT_FIXTURE_SPEC.md`.
3. The public policy/anchor bypasses are closed by #96/#97/#99/#109. Complete the remaining principal-first identity/call-site migration; #109 enforces the anchored writer at the decision-lifecycle entry points before mutation. Do not introduce role-string or caller-controlled authority. Keep the trusted identity adapter synthetic-only and do not add credentials/connectors.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Complete run-record persistence using `docs/PILOT_RUN_RECORD_FIELDS.md`, reconciliation gaps and outcome dependency markers. The audit timeline and chain/anchor verification CLI components are merged in #107; operator-runbook test coverage remains outstanding.
6. Add backup/restore and tamper tests; make the operator runbook command inventory executable by tests.
7. Obtain separate owner approval for the local synthetic dress rehearsal; record the rehearsal and exact evidence in Notion.

The sequence is a planning dependency, not permission to modify code. Claude owns implementation slices; this document is a proposed acceptance contract for review.

## 5. Confirmation rule

Only Claude's exact confirmation entry in the AI Collaboration Log may state that M2 is reached. The entry must cite main SHA, merged PRs, exact-head CI, the tested one-command workflow, fixture and run-record hashes, audit verification, reconciliation/held-outcome evidence, backup/restore/tamper results, runbook test and the logged dress rehearsal. ChatGPT must not declare M2 reached.

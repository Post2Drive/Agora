# M2 — Operator-Usable Synthetic Pilot

**Status:** The owner has approved local synthetic M2 implementation in the current instruction. This checklist is an acceptance contract, not a readiness declaration; M2 remains incomplete and no rehearsal is claimed.  
**Assessment base:** `527476bb4e0450050843dd23a2aa6d5417627ded` (22 November 2026).
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST log entry on main `83d0645b983365dddd9da07d4d1352e0b66e3d00`; #119 and #120 are subsequently merged on current main `527476bb4e0450050843dd23a2aa6d5417627ded`. The current owner instruction authorizes local synthetic M2 implementation only; prohibited categories remain blocked.  
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
| Policy and anchor checks by default | **DONE for protected paths; identity remains synthetic-only** | #113 adds `BoundPolicy` and protected `PRINCIPAL_BOUND_REQUIRED=True`, rejecting raw callables; #111 restricts role-string PDP imports to the internal allowlist and makes the public role-string approval authorizer private. #96/#97/#99/#109 retain protected defaults and anchored-writer guards. Identity remains synthetic-only; anchor trust remains `local_sidecar`. |
| Legacy path retirement | **PARTIAL — public routes retired/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | **IMPLEMENTED COMPONENT — #107** adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>`; merged tests cover selected-decision filtering, ordering, redaction and read-only behaviour. Runbook-command execution test remains outstanding. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | **IMPLEMENTED COMPONENT — #107** adds `agora audit verify --audit <db> --anchor <file> --chain-id <id>` with plain-language verdicts and a `local_sidecar` trust note; tests cover intact, tampered, truncated, missing-anchor and wrong-chain cases. Coordinated rollback of both local files remains an explicit undetectable trust limitation; runbook-command execution test remains outstanding. |
| Backup/restore and tamper drill | **PARTIAL — CLI component merged (#120)** | `agora backup`, `agora backup verify` and `agora restore` verify source/backup chain-anchor integrity, manifest file hashes and empty destinations. Exact-head Actions run `44986367729` passed 4/4. Review found source verify-to-copy and restore verify-to-copy races: lock the source chain/anchor pair across snapshot and re-hash every restored file after copy. Add deterministic concurrency/mutation tests, then record the operator tamper drill. |
| Minimal reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar anchor before classification and requires `--anchor` / `--chain-id`; #115 adds approver-authorised, anchored, exact-head, idempotent repair for missing events only. Repair is API-only, has no CLI, excludes outcome/review rows and blocks unanchored-tail recovery. A TOCTOU review finding remains open. |
| Held-outcome listing | **PARTIAL — read-only list plus first marker slice** | #102/#106 provide `agora outcomes held --decisions <db>` with opaque IDs/stable reason codes and fail-closed connection errors. #116 adds marker creation/propagation for disputed, corrected and source-hash-mismatch triggers over explicit edges. Before operator reliance, fix the merged lifecycle audit-failure gap (unaudited `resolved(valid)`/`superseded` can clear the hold) and require supersession to match the same decision/version/affected object with a persisted reason. Retention/erasure triggers, automatic report/run edges, CLI and marker/audit reconciliation remain open. |
| Run records | Persist and verify the immutable envelope defined by `docs/RUN_PROVENANCE_SPEC.md`; do not call the simulation engine. | Tests assert exact import ID, fixture/schema/binding/manifest hashes, ontology and policy fingerprints, repository SHA and synthetic/exploratory label. The operator-specific field mapping is specified in `docs/RUN_PROVENANCE_SPEC.md`. |
| Operator runbook | Every command and expected output/stop condition in `docs/OPERATOR_RUNBOOK.md` is exercised by an automated test. | Test loads or validates the runbook command inventory and executes each safe local synthetic command. |
| Logged dress rehearsal | A separately owner-approved local synthetic rehearsal records command, SHA, fixture hashes, stage results, denial stops, audit verification, backup/restore/tamper outcomes and operator sign-off. | Verified Notion log entry with exact evidence and Claude's milestone confirmation. |

## 3. M2 authorisation gate

M1 is Claude-confirmed. The current owner instruction explicitly marks M2 owner-approved for local synthetic implementation, superseding Claude's earlier 10:42 hold for this scope only. Continue only within this checklist and the safety boundaries below. #120 is a merged backup/verify/restore component, not a completed operator drill. No rehearsal has been run or recorded; the dress rehearsal remains a later evidence step after implementation, exact-head CI and runbook-test acceptance.

## 4. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Required implementation order

1. M1 was explicitly confirmed by Claude in the 09:05 IST log entry on main `83d0645b983365dddd9da07d4d1352e0b66e3d00`; current main `527476bb4e0450050843dd23a2aa6d5417627ded` includes #119's sidecar-anchor check and #120's local backup/verify/restore CLI. #111/#113 close the public role-string approval and protected Principal-bound policy gaps; #115 adds missing-decision-event repair; #116 merges the first outcome dependency-marker slice. M2 is owner-approved for local synthetic implementation but remains incomplete.
2. Add and verify the synthetic fixture set using `docs/SYNTHETIC_PILOT_FIXTURE_SPEC.md`.
3. The public policy/anchor bypasses are closed by #96/#97/#99/#109. Principal-bound policy gate is implemented by #113; #109 enforces anchored writers before decision-lifecycle mutation. Identity adapter remains synthetic-only. Do not introduce role-string or caller-controlled authority. Keep the trusted identity adapter synthetic-only and do not add credentials/connectors.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Persist and verify the immutable run-provenance envelope using `docs/RUN_PROVENANCE_SPEC.md`; #88 currently returns only an in-memory `PilotResult`. #116's first marker slice is merged, but retention/erasure triggers, automatic report/run edge registration, CLI and marker/audit reconciliation remain open. Use #115 repair only through separately reviewed code paths. #119 adds sidecar verification to reconciliation; its concurrent-writer TOCTOU finding must be hardened. Operator-runbook test coverage remains outstanding.
6. Harden #120's backup/restore concurrency and post-copy file verification; add the synthetic tamper drill and make the operator runbook command inventory executable by tests.
7. Obtain separate owner approval for the local synthetic dress rehearsal; record the rehearsal and exact evidence in Notion.

The sequence is a planning dependency, not permission to modify code. Claude owns implementation slices; this document is a proposed acceptance contract for review.

## 5. Confirmation rule

Only Claude's exact confirmation entry in the AI Collaboration Log may state that M2 is reached. The entry must cite main SHA, merged PRs, exact-head CI, the tested one-command workflow, fixture and run-record hashes, audit verification, reconciliation/held-outcome evidence, backup/restore/tamper results, runbook test and the logged dress rehearsal. ChatGPT must not declare M2 reached.

## 6. M2 planning specifications

The following companion documents define the operator workflow for later implementation. They are plans only; none authorises execution or rehearsal:

- [One-command start plan](M2_ONE_COMMAND_START_PLAN.md)
- [Synthetic fixture selection plan](M2_FIXTURE_SELECTION_PLAN.md)
- [Plain-language audit and anchor verification plan](M2_AUDIT_ANCHOR_OPERATOR_PLAN.md)
- [Backup, restore and tamper-drill plan](M2_BACKUP_RESTORE_TAMPER_PLAN.md)

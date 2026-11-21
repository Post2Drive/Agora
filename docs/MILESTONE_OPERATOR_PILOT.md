# M2 — Operator-Usable Synthetic Pilot

**Status:** M2 scope approved by the owner; this checklist remains a planning contract, not an execution authorisation or readiness declaration.  
**Assessment base:** `7afa1414acd9c2e68361faab81a5d246597a5919` (22 November 2026)  
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
| Policy and anchor checks by default | Principal/policy and the same configured anchored writer are mandatory on every protected path; no silent `policy=None` or unanchored `audit=None` fallback. | Default-path tests and mutation proofs show missing policy/Principal/anchor denies before protected reads or writes. |
| Legacy path retirement | Caller-supplied role/subject authority cannot reach a production path; any compatibility surface is test-only and cannot be enabled by a production runtime setting. | Call-site inventory, fail-closed tests and mutations that restore caller-controlled authority all fail. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | Command-level test for ordering, redaction and deterministic output. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | Tests for clean chain, truncated chain, modified event, missing anchor, mismatched anchor and coordinated local rollback limitation. |
| Backup/restore and tamper drill | Documented local backup/restore preserves chain/anchor continuity; tampering is detected and protected operations stop. | Tests exercise backup, restore, missing/corrupt backup and tamper cases; rehearsal log records outcomes. |
| Minimal reconciliation | Cross-store mismatches are listed and classified without rewriting decision or audit history. | Deterministic report/test for unmatched decision/outcome/audit references; no automatic repair. |
| Held-outcome listing | Outcomes requiring source/dependency review are surfaced as held, with stable reason codes and no silent approval. | Tests for changed/missing source evidence, reviewer holds and listing filters. |
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

1. Complete and confirm M1 using `docs/MILESTONE_PILOT_READY.md`.
2. Add and verify the synthetic fixture set using `docs/SYNTHETIC_PILOT_FIXTURE_SPEC.md`.
3. Complete default-on principal/policy and anchored-writer enforcement across the protected local path; retire runtime-enableable role-string compatibility.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Complete run-record persistence using `docs/PILOT_RUN_RECORD_FIELDS.md`, reconciliation listing, held-outcome markers, audit timeline and plain-language verification.
6. Add backup/restore and tamper tests; make the operator runbook command inventory executable by tests.
7. Obtain separate owner approval for the local synthetic dress rehearsal; record the rehearsal and exact evidence in Notion.

The sequence is a planning dependency, not permission to modify code. Claude owns implementation slices; this document is a proposed acceptance contract for review.

## 5. Confirmation rule

Only Claude's exact confirmation entry in the AI Collaboration Log may state that M2 is reached. The entry must cite main SHA, merged PRs, exact-head CI, the tested one-command workflow, fixture and run-record hashes, audit verification, reconciliation/held-outcome evidence, backup/restore/tamper results, runbook test and the logged dress rehearsal. ChatGPT must not declare M2 reached.

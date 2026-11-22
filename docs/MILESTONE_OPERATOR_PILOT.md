# M2 — Operator-Usable Synthetic Pilot

**Status:** Owner-approved scope is local synthetic M2 only. #141 executes the command inventory, not `docs/OPERATOR_RUNBOOK.md`. #142 adds the pilot `input_provenance` envelope; #144/#145 prove isolated-venv install/start, exact `run_record.json` and false-valued flags, and installed console-script no-engine-import (CI `45021238785`, 4/4). #147 adds a marker-open outbox but does not close recovery: replay after chain-append/done-commit crash hits the real `AuditChainStore` unique-event-ID guard; its tests use a fake audit. Transition-event recovery, concurrent delivery and legacy-marker backfill remain open. M2 also still requires strict provenance validation/report/atomic publication, backup snapshot locking, pilot ancestor-`lstat` proof, direct runbook binding and separately approved logged rehearsal.
**Assessment base:** `main` at `5a579eb2c75257764ec8752273f3241544cf4bf8` (22 November 2026).
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST log entry. The owner approved local synthetic M2 after #122. #142 now adds the `input_provenance` envelope; remaining gaps are strict legacy/new record distinction, strict RFC3339/version typing, manifest schema/time consistency, complete report provenance and failure-atomic publication. Prohibited categories remain blocked.
**Operating boundary:** Local synthetic data and local stores only; no simulation-engine call.

## 1. Objective

Deliver a one-command, operator-usable, deterministic synthetic governance workflow. The operator must be able to install/start locally, select a checked-in synthetic fixture, follow a guided sequence with per-step outcomes, understand every denial/stop, verify the audit chain and local anchor in plain language, inspect held outcomes, and recover from backup/restore or tamper-detection drills.

This milestone demonstrates governance and operator usability only. It does not validate predictive accuracy, demand, sales, causal effects or real-world outcomes.

## 2. Required capabilities and exit evidence

| Requirement | Required behaviour | Exit evidence |
|---|---|---|
| One-command install/start | **DEMONSTRATED — clean-checkout install/start proof merged (#144/#145)** | #125 adds `agora pilot start --fixture ID --workdir D` and `agora pilot list`. #132 refuses a directly symlinked workdir root; #135 refuses symlink/reparse-point ancestors and filters linked fixture directories. #144 proves isolated-venv installation, packaged fixture and installed CLI list/start from outside the repository; #145 requires exactly one valid `run_record.json`, explicit false-valued engine/prediction flags and an installed console-script no-engine-import check (exact-head CI `45021238785`, 4/4). |
| Checked-in synthetic dataset | **AVAILABLE — fixture integrity hardening merged (#132/#135)** | #125 adds `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and per-file hash checks. #132 independently pins the checked-in manifest digest, rejects symlinked fixture directory/manifest/payload paths and empty fixture versions. #135 adds explicit schema/binding symlink coverage and filters linked directories from the catalogue. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4). |
| Guided end-to-end run | **AVAILABLE — partial M2 evidence** | #88 is on main and reports nine stages with first-denial stop. #125 adds fixture-selected `start`; #132 rejects direct workdir-root symlinks; #135 rejects symlink/reparse-point workdir ancestors. Clean-checkout installation and exact run-record/console-script assertions are proven by #144/#145; direct runbook binding and logged rehearsal remain separate gates. |
| CLI import boundary | Pilot/data dispatch must not import the simulation engine; engine imports belong only in simulation commands. | Fresh-process tests prove `import agora.cli` and pilot dispatch do not load `agora.sim.engine`; #94 provides the import/help-dispatch proof, with a full `--workdir` subprocess assertion still desirable. |
| Policy and anchor checks by default | **DONE for protected paths; identity remains synthetic-only** | #113 adds `BoundPolicy` and protected `PRINCIPAL_BOUND_REQUIRED=True`, rejecting raw callables; #111 restricts role-string PDP imports to the internal allowlist and makes the public role-string approval authorizer private. #96/#97/#99/#109 retain protected defaults and anchored-writer guards. Identity remains synthetic-only; anchor trust remains `local_sidecar`. |
| Legacy path retirement | **PARTIAL — public routes retired/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | **IMPLEMENTED COMPONENT — #107** adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>`; merged tests cover selected-decision filtering, ordering, redaction and read-only behaviour. Runbook-command execution test remains outstanding. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | **IMPLEMENTED COMPONENT — #107** adds `agora audit verify --audit <db> --anchor <file> --chain-id <id>` with plain-language verdicts and a `local_sidecar` trust note; tests cover intact, tampered, truncated, missing-anchor and wrong-chain cases. Coordinated rollback of both local files remains an explicit undetectable trust limitation; runbook-command execution test remains outstanding. |
| Backup/restore and tamper drill | **MERGED SYNTHETIC CLI (#120/#127/#134/#136/#138/#139); operator drill pending** | #138 exact sequence/head + manifest binding is merged (CI `45009045175`, 4/4), but no writer-side lock or single-read manifest validation. #139 closes B13 on backup/pilot (CI `45011493565`, 4/4). Deterministic writer proof, command test and logged tamper rehearsal remain incomplete. |
| Minimal reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verification/classification; #115 adds approver-authorised, anchored, exact-head repair for missing decision events only. The lock helper may create a sidecar `.lock` file and the concurrency test uses a fixed sleep, so strict read-only semantics/test determinism need clarification. Repair remains API-only and excludes outcome/review rows/unanchored-tail recovery. |
| Held-outcome listing | **PARTIAL — read-only list plus explicit-edge markers and marker-open outbox** | #102/#106 list held outcomes read-only. #116/#122 provide explicit-edge markers/lifecycle; #147 persists marker-open audit intent, but replay is not crash-idempotent against the real chain, transition events are not outboxed, and legacy rows are not backfilled. Retention/erasure, automatic report/run edges and CLI remain open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **PARTIAL — #142 merged** | Main now stores a versioned `input_provenance` envelope and checks manifest/scenario hashes, exact import ID and data role. Remaining gaps: legacy-vs-new record discrimination, strict RFC3339/timezone and integer version validation, manifest schema and `created_at` cross-check, complete report/export fields, and failure-atomic publication. |
| Operator runbook | **PARTIAL — #141 tests the command inventory, not this file** | #141 executes `docs/M2_RUNBOOK_COMMAND_INVENTORY.md`; it does not read `docs/OPERATOR_RUNBOOK.md`. Direct runbook/command drift coverage remains open. |
| Logged dress rehearsal | A separately owner-approved local synthetic rehearsal records command, SHA, fixture hashes, stage results, denial stops, audit verification, backup/restore/tamper outcomes and operator sign-off. | Verified Notion log entry with exact evidence and Claude's milestone confirmation. |

## 3. M2 authorisation gate

M1 is Claude-confirmed. Owner-approved scope is local synthetic M2 only. #144/#145 prove clean installation/start and strict run-record/flag/console-script assertions (CI `45021238785`, 4/4). #147 adds only marker-open outbox persistence; replay still fails after a chain-append/done-commit crash against the real chain, and transition-event recovery is absent. Remaining M2 gates include strict provenance/report/atomic publication, backup snapshot locking, pilot ancestor-`lstat` proof, direct runbook binding and separately approved logged rehearsal. No rehearsal is claimed.

## 4. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Required implementation order

1. M1 was explicitly confirmed by Claude in the 09:05 IST log entry; current main `5a579eb2c75257764ec8752273f3241544cf4bf8` includes #141, #142, #144 and #145 plus the earlier pilot/backup hardening. #141's inventory test passed exact-head CI `45012531745` 4/4 but does not test this operator-runbook file. #142's provenance envelope passed exact-head CI `45013670475` 4/4; strict legacy/new discrimination, RFC3339/version typing, manifest/time checks, complete report fields and atomic publication remain open. #138 still lacks writer-side locking and single-read manifest validation; #139 closes B13. Pilot intermediate-ancestor lstat-failure coverage remains. M2 is owner-approved for local synthetic implementation but remains incomplete.
2. #144 proves isolated-venv install/start from outside the checkout (head `38884bc8`, exact-head CI `45015043801`, 4/4). #145 strengthens that proof with exactly one valid `run_record.json`, explicit false-valued engine/prediction flags and installed console-script no-engine-import (head `6338c5a5`, exact-head CI `45021238785`, 4/4). Retain both regression layers. The independent manifest pin, direct fixture directory/manifest/payload symlink checks, explicit `schema.json`/`binding.json` symlink tests, empty-version refusal, direct workdir-root refusal and workdir-ancestor refusal are already merged in #132/#135; do not duplicate them.
3. The public policy/anchor bypasses are closed by #96/#97/#99/#109. Principal-bound policy gate is implemented by #113; #109 enforces anchored writers before decision-lifecycle mutation. Identity adapter remains synthetic-only. Do not introduce role-string or caller-controlled authority. Keep the trusted identity adapter synthetic-only and do not add credentials/connectors.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Harden the #142 envelope against the remaining RUN_PROVENANCE_SPEC gaps: distinguish pre-contract legacy records from newly written records with missing provenance; require `type(provenance_version) is int`; enforce timezone-aware RFC3339 and equality between envelope/manifest `created_at`; validate required manifest IDs/versions/hashes and field types; include all required provenance in reports/exports; and publish the immutable run record failure-atomically with partial-write/fsync/rename mutation proofs. Do not duplicate the merged #144/#145 clean-install slices. No engine call or `agora/sim/**` wiring.
6. #127 closes the primary #120 synthetic-gate, in-tree path, manifest, copied-chain/anchor and restore-hash hardening; #134 adds direct root refusal, #135 closes workdir-ancestor/fixture-catalogue gaps, #136 adds backup ancestor/pre-read/lstat-error checks, #138 adds copied-chain sequence/head comparison and manifest-head validation, and #139 closes B13. No writer-side lock and manifest re-read gap remain after #138; pilot intermediate-ancestor lstat-failure coverage is still missing. Execute documented backup/verify/restore cases through the runbook command test, then record the synthetic tamper drill in the separately approved rehearsal.
7. Obtain separate owner approval for the local synthetic dress rehearsal; record the rehearsal and exact evidence in Notion.

The sequence is a planning dependency, not permission to modify code. Claude owns implementation slices; this document is a proposed acceptance contract for review.

## 5. Confirmation rule

Only Claude's exact confirmation entry in the AI Collaboration Log may state that M2 is reached. The entry must cite main SHA, merged PRs, exact-head CI, the tested one-command workflow, fixture and run-record hashes, audit verification, reconciliation/held-outcome evidence, backup/restore/tamper results, runbook test and the logged dress rehearsal. ChatGPT must not declare M2 reached.

## 6. M2 planning specifications

The following companion documents define the remaining operator workflow. They are planning specifications; the current owner approval authorises only the local synthetic M2 scope described here, not simulation wiring, real data, credentials, connectors, write-back or a declaration of rehearsal completion:

- [One-command start plan](M2_ONE_COMMAND_START_PLAN.md)
- [Synthetic fixture selection plan](M2_FIXTURE_SELECTION_PLAN.md)
- [Plain-language audit and anchor verification plan](M2_AUDIT_ANCHOR_OPERATOR_PLAN.md)
- [Backup, restore and tamper-drill plan](M2_BACKUP_RESTORE_TAMPER_PLAN.md)
- [Runbook command inventory and test contract](M2_RUNBOOK_COMMAND_INVENTORY.md)
- [Dress rehearsal plan and evidence record](M2_DRESS_REHEARSAL_PLAN.md)

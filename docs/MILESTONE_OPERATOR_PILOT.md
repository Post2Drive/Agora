# M2 — Operator-Usable Synthetic Pilot

**Status:** Owner-approved scope is local synthetic M2 only. #122's primary marker audit-order/supersession and reconcile-lock changes, #123's initial run record, and #125's checked-in fixture/list/start are merged. #127/#130/#132/#134/#135/#136/#138/#139 are on main. #138 adds exact source/copy sequence/head comparison and manifest binding (CI `45009045175`, 4/4), but no writer-side lock; verify/restore re-read the manifest after validation. #139 closes B13 on backup/pilot path walkers (head `2d3a0e7f`, CI `45011493565`, 4/4), refusing any `..` component and using one `lstat()` result. M2 remains incomplete: manifest single-read validation, deterministic concurrent-writer proof, full input_provenance/failure-atomic run-record publication, runbook test, marker/audit outbox recovery and logged rehearsal remain open. Held-outcome and read-only reconcile CLI already exist with tests.
**Assessment base:** `main` at `1719d4c552d22e88109cee7623b3b7146ee5ef39` (22 November 2026).
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST log entry. The owner approved local synthetic M2 after the three primary hardening fixes merged in #122. #123/#125's run-record fields remain partial. Prohibited categories remain blocked.
**Operating boundary:** Local synthetic data and local stores only; no simulation-engine call.

## 1. Objective

Deliver a one-command, operator-usable, deterministic synthetic governance workflow. The operator must be able to install/start locally, select a checked-in synthetic fixture, follow a guided sequence with per-step outcomes, understand every denial/stop, verify the audit chain and local anchor in plain language, inspect held outcomes, and recover from backup/restore or tamper-detection drills.

This milestone demonstrates governance and operator usability only. It does not validate predictive accuracy, demand, sales, causal effects or real-world outcomes.

## 2. Required capabilities and exit evidence

| Requirement | Required behaviour | Exit evidence |
|---|---|---|
| One-command install/start | **PARTIAL — fixture-selected start exists; clean-install gate not proven** | #125 adds `agora pilot start --fixture ID --workdir D` and `agora pilot list`. #132 refuses a directly symlinked workdir root; #135 refuses symlink/reparse-point ancestors and filters linked fixture directories. The subprocess test does not prove package installation from a clean checkout. |
| Checked-in synthetic dataset | **AVAILABLE — fixture integrity hardening merged (#132/#135)** | #125 adds `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and per-file hash checks. #132 independently pins the checked-in manifest digest, rejects symlinked fixture directory/manifest/payload paths and empty fixture versions. #135 adds explicit schema/binding symlink coverage and filters linked directories from the catalogue. Clean-install proof is absent. |
| Guided end-to-end run | **AVAILABLE — partial M2 evidence** | #88 is on main and reports nine stages with first-denial stop. #125 adds fixture-selected `start`; #132 rejects direct workdir-root symlinks; #135 rejects symlink/reparse-point workdir ancestors. Clean-checkout installation proof remains open. |
| CLI import boundary | Pilot/data dispatch must not import the simulation engine; engine imports belong only in simulation commands. | Fresh-process tests prove `import agora.cli` and pilot dispatch do not load `agora.sim.engine`; #94 provides the import/help-dispatch proof, with a full `--workdir` subprocess assertion still desirable. |
| Policy and anchor checks by default | **DONE for protected paths; identity remains synthetic-only** | #113 adds `BoundPolicy` and protected `PRINCIPAL_BOUND_REQUIRED=True`, rejecting raw callables; #111 restricts role-string PDP imports to the internal allowlist and makes the public role-string approval authorizer private. #96/#97/#99/#109 retain protected defaults and anchored-writer guards. Identity remains synthetic-only; anchor trust remains `local_sidecar`. |
| Legacy path retirement | **PARTIAL — public routes retired/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | **IMPLEMENTED COMPONENT — #107** adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>`; merged tests cover selected-decision filtering, ordering, redaction and read-only behaviour. Runbook-command execution test remains outstanding. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | **IMPLEMENTED COMPONENT — #107** adds `agora audit verify --audit <db> --anchor <file> --chain-id <id>` with plain-language verdicts and a `local_sidecar` trust note; tests cover intact, tampered, truncated, missing-anchor and wrong-chain cases. Coordinated rollback of both local files remains an explicit undetectable trust limitation; runbook-command execution test remains outstanding. |
| Backup/restore and tamper drill | **MERGED SYNTHETIC CLI (#120/#127/#134/#136/#138/#139); operator drill pending** | #138 exact sequence/head + manifest binding is merged (CI `45009045175`, 4/4), but no writer-side lock or single-read manifest validation. #139 closes B13 on backup/pilot (CI `45011493565`, 4/4). Deterministic writer proof, command test and logged tamper rehearsal remain incomplete. |
| Minimal reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verification/classification; #115 adds approver-authorised, anchored, exact-head repair for missing decision events only. The lock helper may create a sidecar `.lock` file and the concurrency test uses a fixed sleep, so strict read-only semantics/test determinism need clarification. Repair remains API-only and excludes outcome/review rows/unanchored-tail recovery. |
| Held-outcome listing | **PARTIAL — read-only list plus marker slice/hardening** | #102/#106 list held outcomes read-only. #116 adds explicit-edge markers; #122 fixes audit-append failure rollback and same-target supersession with a bounded reason. A marker DB commit failure after successful audit append can still leave an orphan audit event; retention/erasure, automatic report/run edges, marker/audit reconciliation and CLI remain open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **PARTIAL — #123/#125/#130 merged** | #130 adds required-field/type, synthetic-only, false-engine/prediction and hash-format checks. It still permits absent/`null` fixture metadata, empty/`unknown` repository SHA strings, arbitrary status/mode values and malformed nested `fixture.file_hashes`; it does not validate canonical `input_provenance` or failure-atomic publication. |
| Operator runbook | Every command and expected output/stop condition in `docs/OPERATOR_RUNBOOK.md` is exercised by an automated test. | Test loads or validates the runbook command inventory and executes each safe local synthetic command. |
| Logged dress rehearsal | A separately owner-approved local synthetic rehearsal records command, SHA, fixture hashes, stage results, denial stops, audit verification, backup/restore/tamper outcomes and operator sign-off. | Verified Notion log entry with exact evidence and Claude's milestone confirmation. |

## 3. M2 authorisation gate

M1 is Claude-confirmed. The owner explicitly approved local synthetic M2 implementation after the three primary post-M1 hardening fixes; #122 is merged. #125 adds the checked-in fixture/list/start component, #127 hardens backup/restore, #130 adds partial strict run-record checks, #132 hardens fixture authenticity/direct paths, #135 closes workdir-ancestor/fixture-catalogue symlink gaps, #136 adds backup ancestor/pre-read/lstat-error checks, #138 adds copied-chain head detection/manifest binding and #139 closes B13. No writer-side lock and manifest re-read gaps remain after #138. Pilot intermediate-ancestor lstat-failure coverage, clean installation, full `input_provenance`/failure-atomic run records, executable runbook test, marker/audit outbox recovery and separately approved rehearsal remain open. No rehearsal has been run or recorded.

## 4. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Required implementation order

1. M1 was explicitly confirmed by Claude in the 09:05 IST log entry; current main `1719d4c552d22e88109cee7623b3b7146ee5ef39` includes #122, #123, #125, #127, #130, #132, #134, #135, #136, #138 and #139. #138 adds copied-chain sequence/head comparison and manifest-head verification; no writer-side lock and manifest re-read gap remain. #139 closes B13. Pilot intermediate-ancestor lstat-failure coverage remains. M2 is owner-approved for local synthetic implementation but remains incomplete.
2. Prove clean-checkout installation/start from a fresh environment. The independent manifest pin, direct fixture directory/manifest/payload symlink checks, explicit `schema.json`/`binding.json` symlink tests, empty-version refusal, direct workdir-root refusal and workdir-ancestor refusal are already merged in #132/#135; do not duplicate them.
3. The public policy/anchor bypasses are closed by #96/#97/#99/#109. Principal-bound policy gate is implemented by #113; #109 enforces anchored writers before decision-lifecycle mutation. Identity adapter remains synthetic-only. Do not introduce role-string or caller-controlled authority. Keep the trusted identity adapter synthetic-only and do not add credentials/connectors.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Complete and verify the immutable run-provenance envelope using `docs/RUN_PROVENANCE_SPEC.md`; #123/#125/#130 provide only partial run records. Add `input_provenance` with exact `scenario_hash`, `import_id`, canonical `input_manifest`/`manifest_hash`, binding/ontology/policy fingerprints, data role and timestamp; validate repository SHA, fixture metadata and cross-field hashes; publish failure-atomically with partial-write mutation proofs. No engine call or `agora/sim/**` wiring.
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

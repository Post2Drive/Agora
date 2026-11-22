# M2 — Operator-Usable Synthetic Pilot

**Status:** The owner has approved local synthetic M2 implementation. #122's primary marker audit-order/supersession and reconcile-lock changes are merged. #123's initial run record is merged but partial. #125's checked-in fixture and `agora pilot list/start` component is merged at head `914d570ce62c5d9c1157ec0470d9b948ff17dfc9`; exact-head CI run `44993280261` passed 4/4. M2 remains incomplete: manifest pinning, symlink/workdir hardening, clean-install proof, full run-record provenance, backup hardening, tested runbook and rehearsal remain open.
**Assessment base:** `main` at `969a040a497668740d20e1ace83841046639b2d6` (22 November 2026).
**Prerequisite:** Claude explicitly confirmed M1 in the 09:05 IST log entry. Main is `969a040a497668740d20e1ace83841046639b2d6` after #124 and #125; the owner approved local synthetic M2 after the three primary hardening fixes merged in #122. #123/#125's run-record fields remain partial. Prohibited categories remain blocked.
**Operating boundary:** Local synthetic data and local stores only; no simulation-engine call.

## 1. Objective

Deliver a one-command, operator-usable, deterministic synthetic governance workflow. The operator must be able to install/start locally, select a checked-in synthetic fixture, follow a guided sequence with per-step outcomes, understand every denial/stop, verify the audit chain and local anchor in plain language, inspect held outcomes, and recover from backup/restore or tamper-detection drills.

This milestone demonstrates governance and operator usability only. It does not validate predictive accuracy, demand, sales, causal effects or real-world outcomes.

## 2. Required capabilities and exit evidence

| Requirement | Required behaviour | Exit evidence |
|---|---|---|
| One-command install/start | **PARTIAL — fixture-selected start exists; clean-install gate not proven** | #125 adds `agora pilot start --fixture ID --workdir D` and `agora pilot list`; exact-head CI run `44993280261` passed 4/4. The subprocess test runs from the repository tree and does not prove package installation from a clean checkout or a single install/start path. |
| Checked-in synthetic dataset | **AVAILABLE — basic fixture merged (#125); integrity hardening pending** | #125 adds `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and per-file hash checks. The manifest digest itself is not independently pinned and symlinked fixture paths are followed; add tamper-together and symlink-escape tests. |
| Guided end-to-end run | **AVAILABLE — partial M2 evidence** | #88 is on main and reports nine stages with first-denial stop. #125 adds fixture-selected `start`; its workdir guard checks only for an existing `synthetic-pilot` child, not every pre-existing file in the workdir. |
| CLI import boundary | Pilot/data dispatch must not import the simulation engine; engine imports belong only in simulation commands. | Fresh-process tests prove `import agora.cli` and pilot dispatch do not load `agora.sim.engine`; #94 provides the import/help-dispatch proof, with a full `--workdir` subprocess assertion still desirable. |
| Policy and anchor checks by default | **DONE for protected paths; identity remains synthetic-only** | #113 adds `BoundPolicy` and protected `PRINCIPAL_BOUND_REQUIRED=True`, rejecting raw callables; #111 restricts role-string PDP imports to the internal allowlist and makes the public role-string approval authorizer private. #96/#97/#99/#109 retain protected defaults and anchored-writer guards. Identity remains synthetic-only; anchor trust remains `local_sidecar`. |
| Legacy path retirement | **PARTIAL — public routes retired/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | Operator can list the event sequence and see actor reference, operation, decision, stable resource IDs, timestamps and policy version without raw payloads. | **IMPLEMENTED COMPONENT — #107** adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>`; merged tests cover selected-decision filtering, ordering, redaction and read-only behaviour. Runbook-command execution test remains outstanding. |
| Plain-language chain/anchor verification | Operator sees chain valid/invalid, anchor match/mismatch, last verified sequence and an actionable fail-closed explanation. | **IMPLEMENTED COMPONENT — #107** adds `agora audit verify --audit <db> --anchor <file> --chain-id <id>` with plain-language verdicts and a `local_sidecar` trust note; tests cover intact, tampered, truncated, missing-anchor and wrong-chain cases. Coordinated rollback of both local files remains an explicit undetectable trust limitation; runbook-command execution test remains outstanding. |
| Backup/restore and tamper drill | **PARTIAL — CLI component merged (#120)** | `agora backup`, `agora backup verify` and `agora restore` verify source/backup chain-anchor integrity, manifest file hashes and empty destinations. Exact-head Actions run `44986367729` passed 4/4. Review found source verify-to-copy and restore verify-to-copy races; recursive copy also follows symlinks and hardcodes `synthetic_only=True` without a project/fixture proof, while malformed manifest `files` types can raise an uncaught exception. Require a verified synthetic project marker/fixture allowlist, reject symlinks/unapproved paths, lock the source chain/anchor pair across snapshot, re-hash every restored file after copy, and validate manifest schema. Add deterministic concurrency/scope/mutation tests, then record the operator tamper drill. |
| Minimal reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verification/classification; #115 adds approver-authorised, anchored, exact-head repair for missing decision events only. The lock helper may create a sidecar `.lock` file and the concurrency test uses a fixed sleep, so strict read-only semantics/test determinism need clarification. Repair remains API-only and excludes outcome/review rows/unanchored-tail recovery. |
| Held-outcome listing | **PARTIAL — read-only list plus marker slice/hardening** | #102/#106 list held outcomes read-only. #116 adds explicit-edge markers; #122 fixes audit-append failure rollback and same-target supersession with a bounded reason. A marker DB commit failure after successful audit append can still leave an orphan audit event; retention/erasure, automatic report/run edges, marker/audit reconciliation and CLI remain open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` (no engine call) | **PARTIAL — #123/#125 merged** | #123 stores a CSV hash and basic IDs/stage results; #125 adds fixture ID/version/manifest and per-file hashes. The full scenario/input-manifest/schema/binding/ontology/policy envelope, strict loader validation and failure-atomic persistence remain incomplete. |
| Operator runbook | Every command and expected output/stop condition in `docs/OPERATOR_RUNBOOK.md` is exercised by an automated test. | Test loads or validates the runbook command inventory and executes each safe local synthetic command. |
| Logged dress rehearsal | A separately owner-approved local synthetic rehearsal records command, SHA, fixture hashes, stage results, denial stops, audit verification, backup/restore/tamper outcomes and operator sign-off. | Verified Notion log entry with exact evidence and Claude's milestone confirmation. |

## 3. M2 authorisation gate

M1 is Claude-confirmed. The owner explicitly approved local synthetic M2 implementation after the three primary post-M1 hardening fixes; #122 is merged. #125 adds the checked-in fixture/list/start component, but its manifest/symlink/workdir/clean-install hardening remains open. #123/#125's run record remains partial. Continue only within this checklist and the safety boundaries below. #120 is a merged backup/verify/restore component, not a completed operator drill. No rehearsal has been run or recorded.

## 4. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Required implementation order

1. M1 was explicitly confirmed by Claude in the 09:05 IST log entry on main `83d0645b983365dddd9da07d4d1352e0b66e3d00`; current main `969a040a497668740d20e1ace83841046639b2d6` includes #121/#124 docs, #122 hardening, #123's initial run record and #125's fixture/start component. M2 is owner-approved for local synthetic implementation but remains incomplete.
2. Harden the merged #125 fixture/start slice: pin the manifest digest independently, reject symlinked fixture paths, enforce a truly empty workdir and prove clean-checkout installation/start. Do not reimplement the already-merged fixture catalogue.
3. The public policy/anchor bypasses are closed by #96/#97/#99/#109. Principal-bound policy gate is implemented by #113; #109 enforces anchored writers before decision-lifecycle mutation. Identity adapter remains synthetic-only. Do not introduce role-string or caller-controlled authority. Keep the trusted identity adapter synthetic-only and do not add credentials/connectors.
4. Implement the local orchestrator and one-command guided stages without calling the simulation engine.
5. Complete and verify the immutable run-provenance envelope using `docs/RUN_PROVENANCE_SPEC.md`; #123's first slice is merged but lacks schema/binding/manifest/ontology/policy hashes, complete schema/hash validation and failure-atomic record persistence. #116/#122 provide the first marker slice and primary lifecycle hardening, but cross-store commit-failure handling, retention/erasure, automatic report/run edge registration, CLI and marker/audit reconciliation remain open.
6. Harden #120's backup/restore concurrency, synthetic-source allowlisting/symlink rejection, manifest schema and post-copy file verification; add the synthetic tamper drill and make the operator runbook command inventory executable by tests.
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

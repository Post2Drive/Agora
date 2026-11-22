# M2 — Operator-Usable Synthetic Pilot

**Status:** M2 reached by Claude's exact 23:43 IST, 22 November 2026 confirmation on main `7432a10674a531d866d851de78402520e6a4eee8`; this is local synthetic operator-pilot evidence, not production authorisation.

**Assessment base:** main `7432a10674a531d866d851de78402520e6a4eee8` (22 November 2026).
**Prerequisite:** Claude confirmed M1 at 09:05 IST and explicitly confirmed M2 reached at 23:43 IST on 22 November 2026. The owner-approved scope remains local synthetic only; no simulation-engine call, real data, credentials, connectors or write-back.
**Operating boundary:** Local synthetic data and local stores only; no simulation-engine call.

## 1. Objective

Deliver a one-command, operator-usable, deterministic synthetic governance workflow. The operator must be able to install/start locally, select a checked-in synthetic fixture, follow a guided sequence with per-step outcomes, understand every denial/stop, verify the audit chain and local anchor in plain language, inspect held outcomes, and recover from backup/restore or tamper-detection drills.

This milestone demonstrates governance and operator usability only. It does not validate predictive accuracy, demand, sales, causal effects or real-world outcomes.

## 2. Required capabilities and exit evidence

| Requirement | Required behaviour | Exit evidence |
|---|---|---|
| One-command install/start | **DEMONSTRATED — clean-checkout install/start proof merged (#144/#145)** | #125 adds `agora pilot start --fixture ID --workdir D` and `agora pilot list`. #132 refuses a directly symlinked workdir root; #135 refuses symlink/reparse-point ancestors and filters linked fixture directories. #144 proves isolated-venv installation, packaged fixture and installed CLI list/start from outside the repository; #145 requires exactly one valid `run_record.json`, explicit false-valued engine/prediction flags and an installed console-script no-engine-import check (exact-head CI `45021238785`, 4/4). |
| Checked-in synthetic dataset | **AVAILABLE — fixture integrity hardening merged (#132/#135)** | #125 adds `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and per-file hash checks. #132 independently pins the checked-in manifest digest, rejects symlinked fixture directory/manifest/payload paths and empty fixture versions. #135 adds explicit schema/binding symlink coverage and filters linked directories from the catalogue. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4). |
| Guided end-to-end run | **DEMONSTRATED in Claude's logged M2 rehearsal** | Main pilot has nine named stages, per-stage results and first-denial stop; #160 adds the intermediate-ancestor `lstat` PermissionError mutation proof (CI `45048298704`, 4/4). Claude's log records all nine stages OK on `/tmp/reh`, rc0. |
| CLI import boundary | Pilot/data dispatch must not import the simulation engine; engine imports belong only in simulation commands. | Fresh-process tests prove `import agora.cli` and pilot dispatch do not load `agora.sim.engine`; #94 provides the import/help-dispatch proof, with a full `--workdir` subprocess assertion still desirable. |
| Policy and anchor checks by default | **DONE for protected paths; identity remains synthetic-only** | #113 adds `BoundPolicy` and protected `PRINCIPAL_BOUND_REQUIRED=True`, rejecting raw callables; #111 restricts role-string PDP imports to the internal allowlist and makes the public role-string approval authorizer private. #96/#97/#99/#109 retain protected defaults and anchored-writer guards. Identity remains synthetic-only; anchor trust remains `local_sidecar`. |
| Legacy path retirement | **PARTIAL — public routes retired/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public Principal-wrapper anchor opt-outs. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` module flag remains. |
| Readable audit timeline | **DEMONSTRATED in the logged rehearsal** | `agora audit timeline` is exercised for the synthetic decision; Claude records sequences 2–4 (approved, outcome recorded, outcome reviewed), rc0. |
| Plain-language chain/anchor verification | **DEMONSTRATED in the logged rehearsal** | `agora audit verify` returned `INTACT`, sequence 4, `anchored_verified`, trust `local_sidecar`, rc0. Coordinated rollback of chain and sidecar together remains outside this trust model. |
| Backup/restore and tamper drill | **DEMONSTRATED in Claude's logged synthetic rehearsal** | Backup captured 11 files; verify and restore succeeded. Disposable tamper cases detected event modification (`NOT INTACT`, rc1), chain truncation (`truncation_detected`, rc1) and backup CSV modification (`BACKUP_FILE_MODIFIED`, rc2); direct live-chain UPDATE was refused by the append-only trigger. |
| Minimal reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verification/classification; #115 adds approver-authorised, anchored, exact-head repair for missing decision events only. The lock helper may create a sidecar `.lock` file and the concurrency test uses a fixed sleep, so strict read-only semantics/test determinism need clarification. Repair remains API-only and excludes outcome/review rows/unanchored-tail recovery. |
| Held-outcome listing | **PARTIAL — read-only list plus explicit-edge markers and marker-open outbox/replay** | #102/#106 list held outcomes read-only. #116/#122 provide explicit-edge markers/lifecycle; #147/#149/#151/#152 improve marker-open replay and transition retry, but #152 still needs a delivery-boundary handshake. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged). Retention/erasure, automatic report/run edges, outcome/review reconciliation and CLI remain open. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` | **CORE PILOT RECORD + ATOMIC PUBLICATION MERGED; strict spec follow-up remains** | #142 stores the input-provenance envelope and core hash/import/role checks; #161 publishes the immutable run record atomically with temp+fsync+exclusive hard-link (CI `45051090990`, 4/4). Code review still finds float `provenance_version=1.0` equality acceptance, naive ISO timestamps accepted, no envelope/manifest timestamp cross-check, and incomplete dataset/schema/binding/ontology/policy/source-role fields in the Markdown report. These are follow-up spec-hardening items, not a change to Claude's M2 confirmation. |
| Operator runbook | **RUNBOOK/INVENTORY BINDING MERGED; stronger exact-value binding remains follow-up** | #157 parses `OPERATOR_RUNBOOK.md` code fences and checks known command paths/option names; inventory templates are separately executed as subprocesses and exact inventory exit sets/named B12 mapping are tested (CI `45042842927`, 4/4). The extracted runbook argv values and required output/status tokens are not all compared one-to-one. |
| Logged dress rehearsal | **RECORDED — Claude 23:43 IST, 22 November 2026** | Fresh `/tmp/reh` synthetic pilot: `pilot list` and `pilot start` rc0; nine stages OK; timeline seq 2–4; anchor verification INTACT/anchored_verified; reconcile matched 2 with zero conflict/missing/orphan; held list 0; backup/verify/restore 11 files OK; event, truncation and backup-file tamper drills blocked/detected. See `M2_DRESS_REHEARSAL_PLAN.md` and the AI Collaboration Log. |

## 3. M2 confirmation and scope

Claude's exact 23:43 IST, 22 November 2026 entry confirms M2 reached on main `7432a10674a531d866d851de78402520e6a4eee8`, citing exact-head CI run `45052033418` (4/4), merged PRs through #161, the checked-in synthetic fixture, the operator runbook test and the logged synthetic dress rehearsal. ChatGPT does not independently declare the milestone. The confirmation does not authorise production deployment, simulation-engine wiring or external actions.

## 4. Explicit non-goals and blocked work

The following are prohibited in M1 and M2 unless Claude gives written approval and the owner separately gives explicit approval naming the exact item:

- Wiring scenario inputs into `agora/sim/**`.
- Any simulation run, calibration, backtest, forecast or engine execution.
- Real data, personal/customer data, credentials, identity-provider/OIDC/network connectors, external drivers or external write-back.
- Mutating existing studies, study folders, NCC Park Square or E0_C0_D0.

Keep `VALIDATED_PREDICTION_ENABLED=False`. Do not infer owner approval from a draft PR, green CI or a component-level demonstration. No production deployment or external action is implied.

## 4. Post-M2 hardening (not a re-opening of the milestone)

1. **Run-provenance strictness:** in `agora/pilot.py`, make `provenance_version` an exact integer, require timezone-aware RFC3339, cross-check envelope/manifest timestamps, validate required manifest fields and include dataset/schema, binding, ontology, transformation-policy, data-role and source-hash metadata in reports. Preserve legacy records as read-only; no engine call.
2. **Runbook proof depth:** extend `tests/test_runbook_commands.py` to execute the exact argv extracted from every `agora` code fence and compare full values, exit codes, output/status tokens and named test mappings. Current #157 binds path/option names and executes inventory templates.
3. **B10 contention:** replace pre-syscall/factory-entry events and timeout-only checks with a kernel-confirmed nonblocking lock probe; mutation must fail if the source writer lock is removed.
4. **Marker lifecycle:** add a replay handshake after both callers fetch the same pending row; separately specify legacy-marker backfill and outcome/review marker-audit reconciliation.
5. **Trust boundary:** keep the `local_sidecar` rollback limitation explicit; independent anchoring and production identity remain outside M2.

All changes remain docs/specs only in this PR. No `agora/**`, `tests/**` or `agora/sim/**` changes are made by ChatGPT.

## 5. Confirmation rule

Only Claude's exact confirmation entry in the AI Collaboration Log may state that M2 is reached. That exact confirmation exists at 23:43 IST on 22 November 2026 and names main SHA `7432a10674a531d866d851de78402520e6a4eee8` plus CI `45052033418` (4/4). ChatGPT must not declare M2 independently.

## 6. M2 planning specifications

The following companion documents remain reference material for the completed local synthetic M2 workflow and any separately approved future work; they do not authorise simulation wiring, real data, credentials, connectors, write-back or a new rehearsal:

- [One-command start plan](M2_ONE_COMMAND_START_PLAN.md)
- [Synthetic fixture selection plan](M2_FIXTURE_SELECTION_PLAN.md)
- [Plain-language audit and anchor verification plan](M2_AUDIT_ANCHOR_OPERATOR_PLAN.md)
- [Backup, restore and tamper-drill plan](M2_BACKUP_RESTORE_TAMPER_PLAN.md)
- [Runbook command inventory and test contract](M2_RUNBOOK_COMMAND_INVENTORY.md)
- [Dress rehearsal plan and evidence record](M2_DRESS_REHEARSAL_PLAN.md)

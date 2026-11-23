# Operator Runbook — Governed Synthetic Pilot

**Status:** M2 synthetic pilot rehearsal is historical evidence, not production authorisation. M3 governed-input code slices #163/#164/#171/#172/#173 are merged on main `84e278bc246ee4fb00e252f361dd97bc334d052c` (23 November 2026); exact-head CI for #171/#172/#173 passed 4/4 each. The governed CLI is currently **blocked by design**: `agora/cli.py::_governed_policy()` returns `None` until an approved identity/policy adapter is wired, so policy-required construction denies before snapshot bytes are opened.

**Assessment base:** main `84e278bc246ee4fb00e252f361dd97bc334d052c` (23 November 2026).
**Milestone dependency:** `docs/MILESTONE_OPERATOR_PILOT.md` records Claude's exact M2 confirmation; `docs/M2_RUNBOOK_COMMAND_INVENTORY.md` is the command-test contract and `docs/M2_DRESS_REHEARSAL_PLAN.md` contains the logged evidence. This runbook is an operator reference, not production authorisation.

## 1. Scope and safety

Local synthetic data and local stores only. No real data, personal/customer records, credentials, network connectors, external write-back, simulation, calibration, backtest, forecast or study mutation is authorised here. Do not touch `agora/sim/**`. Keep `VALIDATED_PREDICTION_ENABLED=False`. NCC and Nutrivance are out of scope.

Claude's exact 23:43 IST entry confirms M2 reached; the logged synthetic rehearsal is evidence for that confirmation, not authorisation for production, simulation runs or external actions.

## 2. M2 operator capability checklist

| M2 requirement | Mainline status at `7432a10674a531d866d851de78402520e6a4eee8` | Evidence / missing item |
|---|---|---|
| One-command install/start | **DEMONSTRATED — #144/#145 clean-checkout install/start and exact run-record/flag/console-script proof passed** | Main includes `agora pilot start --fixture ID --workdir D` (#125). #130 refuses non-empty workdirs; #132 rejects direct workdir-root symlinks; #135 rejects symlink/reparse-point ancestors and filters linked fixture directories; #139 refuses lexical `..` in the pilot workdir path. #144 proves isolated-venv installation and installed CLI list/start from outside the repository; #145 requires exact run-record/false flags and installed console-script no-engine-import (CI 45021238785, 4/4). |
| Checked-in synthetic dataset | **AVAILABLE — fixture integrity and symlink coverage merged (#132/#135)** | #132 independently pins the manifest digest, rejects symlinked fixture directory/manifest/payload paths and empty fixture versions. #135 adds explicit symlink refusal tests for `schema.json` and `binding.json` in `tests/test_pilot_fixture.py`. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4). |
| Guided end-to-end run with per-step results and clear gate-denial stops | **DEMONSTRATED in Claude's logged rehearsal** | The pilot records nine named stages and stops at the first denial. Claude's 23:43 IST log records all nine stages OK on the fresh `/tmp/reh` synthetic workdir; #160 adds the intermediate-ancestor `lstat` PermissionError denial/mutation proof (CI `45048298704`, 4/4). |
| Anchor and policy checks enabled by default everywhere | **DONE for protected policy paths; local trust limitation remains** | #113 requires `BoundPolicy` under `PRINCIPAL_BOUND_REQUIRED=True`; #111 restricts role-string PDP imports and makes the role-string approval authorizer private. #96/#97/#99/#109 keep protected defaults and anchored-writer guards. #119/#122 verify the sidecar under the shared lock before reconcile classification. The original TOCTOU gap is closed; the lock helper may still create a `.lock` metadata file and the concurrency test uses a fixed sleep. Identity remains synthetic-only and anchor trust remains `local_sidecar`. |
| Legacy paths removed or test-only | **PARTIAL — public authorizer private/allowlisted; test-only legacy approval remains** | #92 retires public role-string outcome exports; #111 makes the role-string approval authorizer private and restricts PDP imports to the internal allowlist; #96 removes public wrapper opt-outs; #97 confines legacy approval enablement to the test-only module flag. |
| Readable audit timeline and plain-language chain/anchor verification | **CLI and rehearsal demonstrated** | Timeline seq 2–4 and anchor verify `INTACT`/`anchored_verified`/`local_sidecar` were exercised in Claude's logged synthetic rehearsal. Runbook code-fence paths/options are bound by #157; full argv/value/output/status binding remains follow-up. |
| Backup/restore and tamper drill | **DEMONSTRATED in logged rehearsal** | Backup/verify/restore succeeded for 11 files; event, truncation and backup-CSV tamper cases were detected/blocked. B10's deterministic kernel-contention proof remains a follow-up. |
| Minimal reconciliation and held-outcome listing | **PARTIAL — decision detector/repair API, held list and marker-open outbox** | #100/#104/#119/#122 provide anchored decision lifecycle detection/classification; #115 is API-only missing-decision repair; #102/#106 list held outcomes. #147/#149/#151/#152 improve marker-open replay and transition retry; #152's barrier precedes the pending-row delivery boundary. Legacy-marker backfill, outcome/review marker reconciliation, repair CLI and runbook integration remain open. Claude's exact M2 confirmation records #157 runbook/inventory binding; exact argv/value/output-status matching remains post-M2 hardening. |
| Run records per `docs/RUN_PROVENANCE_SPEC.md` | **CORE RECORD AND ATOMIC PUBLISH PRESENT; strict spec follow-up** | #161 atomic publication is merged (CI `45051090990`, 4/4). The remaining code-review caveats are float provenance-version acceptance, naive timestamp acceptance, no manifest/envelope timestamp equality check and incomplete report provenance fields. |
| Operator runbook commands executed by a test | **PARTIAL — #157 binds runbook fences; inventory templates execute** | `tests/test_runbook_commands.py` executes inventory templates as subprocesses and checks that the engine is not loaded; #157 also parses `OPERATOR_RUNBOOK.md` fences and binds command paths/option names to inventory rows. It does not execute the extracted fence argv or compare every value and required output/status token; exact-value binding remains post-M2 hardening. |
| Logged dress rehearsal | **RECORDED — Claude 23:43 IST** | Fresh `/tmp/reh` synthetic run, audit timeline/verify, reconcile, held-outcome list, backup/verify/restore and tamper drills are recorded in `M2_DRESS_REHEARSAL_PLAN.md`. |

## 3. Existing components (not a complete operator workflow)

- **PARTIAL — governed CSV import:** standalone `agora data import-csv` has no Principal and is refused with `POLICY_DENIED` in protected mode; `agora pilot start` performs the governed import. `agora data snapshots`, `agora data show` and `agora data rejected` remain read-only inspection commands for an exact import ID.
- **AVAILABLE — Python APIs:** ontology binding/materialization, scenario-input construction, decision records, principal-native `approve_as()`, outcome/review APIs and local anchored-audit primitives.
- **PROTECTED — policy enforcement:** #96 removes public `require_policy` opt-out kwargs; #97 removes the unanchored `audit=None` fallback; #99 removes the direct helper override and requires an anchored writer for protected denial events.
- **PARTIAL — principal approval:** #80/#84 provide `approve_as()` with server-derived policy inputs; #96 removes its public anchor opt-out kwarg. #97 removes the legacy approval env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains.
- **PARTIAL — anchored audit:** #71/#74/#75 wire append points; #96 removes public `require_anchored=False` kwargs, #92 retires public role-string outcome exports, #97 removes the unanchored denial fallback, #99 validates the policy-denial writer, and #109 guards the remaining decision lifecycle transitions before mutation. Trust remains `local_sidecar`; low-level lifecycle signatures retain optional annotations but protected calls refuse missing/plain writers, while private outcome helpers remain internal.
- **AVAILABLE — guided synthetic command:** `agora pilot --workdir <new-empty-directory>` (#88) runs nine stages and stops on first denial without invoking the engine. #125 adds `agora pilot list/start --fixture <id>` using the checked-in fixture. #132 pins the manifest, rejects direct fixture directory/manifest/payload symlinks and empty versions, and refuses a directly symlinked workdir root; workdir ancestors are refused since #135; #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4). #94 keeps pilot/data dispatch engine-import-free.
- **AVAILABLE — read-only audit commands (#107):** `agora audit timeline` lists one decision's transitions/related audit events after hash-chain verification; `agora audit verify` compares the chain with the local anchor and reports the local-sidecar trust limitation. They do not write, repair or bootstrap.
- **PARTIAL — reconciliation and held outcomes:** #100/#104/#119 provide the anchored decision lifecycle detector; #122 holds the lock across verification/classification, with a lock-file metadata side effect and fixed-sleep race-test caveat. #115 is API-only repair for missing decision events. #102/#106 list held outcomes; #116/#122 provide explicit-edge markers. #147/#149/#151/#152 provide marker-open outbox, real-chain idempotency, anchored-valid lookup and concurrent replay; #152 still needs a delivery-boundary handshake. Legacy-marker backfill, outcome/review marker-audit reconciliation, retention/erasure triggers, automatic report/run edges and a repair CLI remain open. Claude's exact M2 confirmation records #157 runbook/inventory binding; exact argv/value/output-status matching remains post-M2 hardening.

Do not execute a component command as though it were the full M2 workflow.

## 4. Demonstrated operator sequence and current test boundary

Claude's logged 22 November 2026 rehearsal used a fresh `/tmp/reh` workdir and only the checked-in `synthetic-units-v1` fixture. The following is historical evidence, not permission to repeat the rehearsal. `D`, `A`, `N`, `P`, `B` and `R` below are placeholders for paths created inside that fresh synthetic project; never reuse paths from another run.

1. **Fixture catalogue:** `agora pilot list` returned the fixture with rc0.
2. **Guided pilot:** `agora pilot start --fixture synthetic-units-v1 --workdir /tmp/reh` completed all nine stages with rc0. The run record and report were synthetic-labelled; `engine_invoked=false` and `VALIDATED_PREDICTION_ENABLED=False`.
3. **Audit evidence:** `agora audit timeline --decisions D --audit A --decision-id decision-synthetic-001` returned sequences 2–4 (approval, outcome recorded, outcome reviewed), rc0. `agora audit verify --audit A --anchor N --chain-id synthetic-pilot-chain` returned `INTACT`, `anchored_verified`, trust `local_sidecar`, rc0.
4. **Reconciliation and held outcomes:** Claude recorded reconciliation as matched 2, with conflict/missing/orphan all 0, rc0; `agora outcomes held --decisions D` returned held 0 and outcomes 1, rc0.
5. **Backup and restore:** the logged `agora backup`, `agora backup verify` and `agora restore` operations completed for 11 files with rc0. Use the command forms shown in the inventory and fresh destinations only.
6. **Tamper drills:** disposable event modification returned `NOT INTACT` (rc1) and reconciliation `CHAIN_INVALID` (rc2); chain truncation returned `truncation_detected` (rc1); a modified backup CSV returned `BACKUP_FILE_MODIFIED` on verify and restore (rc2). A direct UPDATE against the live append-only chain was refused.

**Automated-test boundary:** `tests/test_runbook_commands.py` executes the inventory templates as subprocesses and asserts the simulation engine is not loaded. #157 additionally parses the runbook's `agora` code fences and checks command paths and option names against inventory rows. It does not execute each extracted runbook argv or compare every value and required output/status token. That is a post-M2 traceability-strengthening item; it does not reverse Claude's exact M2 confirmation.

Stop on any gate denial, unsafe path, provenance/hash mismatch, chain/anchor failure, unexpected engine import, real data, credential, connector or external write. Do not bypass a gate, repair source evidence in place or rerun a failed step by deleting its evidence.

Command forms (placeholders only; each path must be a fresh path inside a synthetic project; bound to the inventory by `tests/test_runbook_commands.py`):

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>
agora audit timeline --decisions <decisions-db> --audit <audit-db> --decision-id <decision-id>
agora audit verify --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain
agora reconcile --decisions <decisions-db> --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain
agora outcomes held --decisions <decisions-db>
agora backup --project <synthetic-project> --dest <new-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-target-dir>
```

## 5. Mandatory stop conditions

Stop immediately on a missing/invalid Principal, wrong tenant/project, missing required policy, missing/invalid anchor, chain mismatch, non-exact import ID, provenance mismatch, unexpected source read before policy denial, real/personal/sensitive data, credentials, network access, write-back, a simulation/engine call, an unlabelled exploratory output or any attempt to modify a protected study.

Never repair a reconciliation gap by rewriting a decision version or audit event. Preserve ambiguous cases for independent human review. Never treat a simulated preference, agent action, conversion or report metric as an observed outcome.

## 6. Evidence retained and future-run controls

The completed rehearsal evidence is recorded in `M2_DRESS_REHEARSAL_PLAN.md` and Claude's 23:43 IST collaboration-log entry. The log does not specify OS/Python/CLI versions, the operator sign-off or full source/backup hash comparison; do not invent those fields. For any future separately approved rehearsal, record the repository SHA, exact command and CLI version, operator identity reference, synthetic fixture IDs and hashes, schema/binding/ontology fingerprints, import ID, scenario-input hash, decision ID/version/fingerprint, policy version and denial codes, audit chain ID/head, anchor verification result, run-record hash, report ID/mode and backup/restore/tamper outcomes. Do not log raw rows, sensitive values, credentials or unrestricted free text. This runbook does not authorise another rehearsal.

Claude's exact 23:43 IST entry confirms M2 reached on main `7432a10674a531d866d851de78402520e6a4eee8` with exact-head CI `45052033418` (4/4). This runbook records the commands and the completed synthetic rehearsal; it does not authorise a new rehearsal, simulation or production use.


## 7. M3 governed-input CLI — implemented, not yet operator-usable

The following interface is present in the merged CLI parser:

```bash
agora run <project> --governed-input <IMPORT_ID> --binding <binding-file> --pack <ontology-pack-file> --mapping <mapping-file>
```

The import identifier must be exact; `latest` is rejected. `--force` is refused with governed input. Supplying `--binding`, `--pack` or `--mapping` without `--governed-input` is refused. Engine-level governed-input refusals are returned as exit code 3.

**Current gate:** `agora/cli.py::_governed_policy()` returns `None` because no production identity adapter is wired. The policy-required scenario-input builder therefore denies the request before opening the snapshot. Do not run this command expecting success, do not pass an ad hoc permissive policy, and do not weaken the default-deny path. The next operator step is blocked until the owner decides whether a narrowly scoped synthetic Principal is acceptable for local public-data validation and Claude implements/reviews the approved adapter.

**Do not substitute the legacy command.** `agora run <project>` without `--governed-input` remains the legacy scenario-file simulation path. It does not prove governed tabular-input provenance and must not be used for the benchmark packages in `VALIDATION_PROTOCOL.md`.

No M3 simulation or validation run has been authorized or performed. Keep `VALIDATED_PREDICTION_ENABLED=False`; reports remain exploratory and simulated. The exact operator invocation, environment and evaluator steps must be frozen in a new approved protocol revision before any run.

## 8. M3 operator readiness checklist

- [ ] Owner decision recorded on synthetic Principal versus production identity requirements.
- [ ] Approved adapter is Principal-bound, scoped, expiring and fail-closed.
- [ ] Policy denial occurs before source snapshot bytes are opened.
- [ ] Direct `Simulation(..., governed_input=...)` cannot bypass the authorization boundary.
- [ ] Original `base_scenario_hash` and effective `projected_scenario_hash` are distinct and tested.
- [ ] Exact input, mapping, row and projection hashes are persisted append-once and checked on resume.
- [ ] Reports/exports retain full provenance and explicit exploratory label.
- [ ] Dataset files, licences, exact headers, privacy review and SHA-256 register are owner-supplied.
- [ ] Validation protocol is explicitly approved and frozen.
- [ ] Separate owner approval exists for any simulation/validation run.

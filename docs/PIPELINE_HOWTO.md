# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** M1 and M2 are Claude-confirmed reached on main `7432a10674a531d866d851de78402520e6a4eee8` (M2 confirmation 23:43 IST, 22 November 2026; CI `45052033418`, 4/4). Local synthetic pilot only; no simulation engine or production capability is implied. Post-M2 hardening remains visible: `_check_provenance()` still accepts a float provenance version equal to 1 and `datetime.fromisoformat()` accepts a naive timestamp; manifest/envelope timestamp equality and full report provenance fields are not yet enforced. The runbook test executes inventory command templates and binds runbook code-fence command paths/option names, but does not execute the extracted runbook argv or compare every value/output/status token. B10 still has a pre-syscall scheduling gap; #152's replay barrier is before pending-row delivery; legacy-marker backfill and outcome/review marker reconciliation remain open. Anchor trust remains `local_sidecar`, not an independent external anchor.

**Assessment base:** main `7432a10674a531d866d851de78402520e6a4eee8` (22 November 2026).
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

Main `7432a10674a531d866d851de78402520e6a4eee8` includes marker-open outbox/replay (#147/#149), anchored-valid lookup and stable transition retry (#151), the two-caller replay test (#152), source snapshot locking and a single manifest snapshot (#148), strict backup manifest typing (#154), runbook command path/option binding (#157), the B10 real-writer lock test mapping (#159), the pilot ancestor-`lstat` denial proof (#160), and atomic run-record publication (#161). Exact-head CI for #157/#159/#160/#161 and M2 confirmation run `45052033418` passed 4/4. #152's barrier is before the pending-row query and does not prove both callers fetched the same row before delivery. Claude confirmed M2 reached at 23:43 IST on 22 November 2026.

This guide documents the available components and their boundaries. It does not authorise a simulation, calibration, backtest, forecast, study mutation, live pilot, production decision, real data, credentials, network access or external write-back. Do not use Nutrivance, NCC Park Square, customer records or any real personal/sensitive data. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Capability status at this assessment base

| Pipeline stage | Status on merged main | What is actually available |
|---|---|---|
| Synthetic CSV import | **PARTIAL — governed import inside pilot start** | Standalone `agora data import-csv` is denied with `POLICY_DENIED` in protected mode because it has no Principal; `agora pilot start` performs the import under the synthetic Principal. Snapshot/show/rejected commands remain read-only inspection. |
| Ontology binding | **AVAILABLE — Python API, protected boundary** | `load_binding`, `validate_binding`, `materialize_instances`; #96 removes the public opt-out kwarg and #99 hardens direct policy enforcement with anchored denial writes. |
| Shared policy enforcement | **DONE — Principal-bound callback enforced** | #113 introduces `BoundPolicy` and rejects raw callables in protected mode (`PRINCIPAL_BOUND_REQUIRED=True`). The adapter remains synthetic-fixture-only. |
| Scenario-input package | **AVAILABLE — guided pilot integration; engine disconnected** | #142 calls `build_scenario_input()` during pilot bind and persists its manifest/hash in the run record. It is not consumed by `agora/sim/engine.py`; no engine or simulation wiring is authorised. |
| Decision record and proposal | **AVAILABLE — Python API** | Decision schema/store and lifecycle APIs. |
| Principal-based approval | **AVAILABLE — partial synthetic migration** | #80/#84/#89/#96 make `approve_as()` Principal-native with stored-decision-derived policy input and no public anchor opt-out kwarg. #97 removes the legacy env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains. |
| Anchored audit chain | **AVAILABLE — local-sidecar API; protected entry points guarded** | #63/#71/#74/#75/#89/#96/#97 provide writer, factory, append wiring and protected Principal wrappers; #99 hardens policy-denial writes and #109 guards `propose()`/`reject()`/`expire()`/`supersede()` before mutation when `ANCHOR_REQUIRED=True`. Optional annotations do not permit `None` or plain writers on protected paths. Trust is `local_sidecar`. |
| Audit timeline and chain/anchor verification | **AVAILABLE — read-only CLI (#107)** | `agora audit timeline` verifies the hash chain and lists one decision's stored transitions/related audit events; `agora audit verify` compares the chain with its local sidecar and states the trust limitation. Neither writes or repairs. |
| Backup/restore | **MERGED SYNTHETIC CLI; verify/restore/tamper drill recorded in Claude's M2 rehearsal** | #148 adds the source writer lock and one manifest snapshot for verify/restore (CI `45026655360`, 4/4); #154 adds strict manifest version/sequence/hash validation (CI `45037406804`, 4/4); #159 maps B10 to the real-writer OS-lock observer (CI `45045492204`, 4/4), with deterministic kernel-confirmed contention still a follow-up. Claude's 23:43 rehearsal records an 11-file backup/verify/restore and disposable tamper denials. A new rehearsal requires separate approval; this document does not authorise a rerun. |
| Observed outcome recording/review | **AVAILABLE — Principal public routes; protected public wrappers** | #92 retires public role-string exports and #96 removes public `require_anchored=False` kwargs. Private helper audit can still be omitted internally; this is not a public caller bypass. |
| Outcome dependency review markers | **PARTIAL — marker-open replay and stable transition retry; legacy backfill/reconciliation follow-up** | #147/#149/#151/#152 are merged. #152's barrier is before the pending-row query, so a delivery-boundary handshake remains a post-M2 test-strengthening item. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open. M2 is Claude-confirmed reached; the latest logged Claude command is `docs/M3_DESIGN.md`, with no M3 owner go recorded. |
| Decision/audit reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verify/classify; #115 repairs missing decision events through an approver-authorised API only. The lock helper may create a sidecar `.lock` file, and the concurrency test uses a timing sleep; no outcome/review reconciliation or unanchored-tail recovery is included. |
| M2 run record | **CORE RECORD + ATOMIC PUBLICATION MERGED; strict spec follow-up** | #142 stores `input_provenance` and checks core manifest/scenario hashes, exact import ID and role; #161 publishes the immutable record via a private temp file, flush/fsync and exclusive hard-link (CI `45051090990`, 4/4). Main `_check_provenance()` compares the version with `1` but excludes only `bool`, so float `1.0` passes; `datetime.fromisoformat()` accepts naive timestamps; envelope and manifest `created_at` are not compared; `_write_report()` omits dataset/schema, binding, ontology, transformation-policy, data-role and source-hash provenance fields. Missing `input_provenance` is still accepted as `legacy_missing` for any record. These are post-M2 hardening gaps, not a reversal of Claude's milestone confirmation. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **M2 local synthetic operator workflow — Claude-confirmed reached** | Main provides the nine-stage pilot and fixture-selected `pilot list/start`; #144/#145 prove clean-checkout install/start, #157 binds runbook code-fence paths/options to the inventory, #160 adds the intermediate-ancestor `lstat` PermissionError denial/mutation proof, and #161 adds atomic run-record publication. Claude's 23:43 rehearsal records the guided run, audit verification, reconciliation, held-outcome listing, backup/restore and tamper drill. Post-M2 follow-ups remain strict provenance/report completeness, exact runbook argv/value/output/status binding, deterministic B10 contention, marker backfill and outcome/review reconciliation. |

## 2.1 Guided synthetic pilot command on main (#88/#125; CLI import isolation #94)

The merged CLI dispatches `agora pilot` from `agora.cli.main()` to `agora.pilot.main()`. The supported invocation is:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

Use a new empty local work directory. Main includes `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and `agora pilot list` / `agora pilot start --fixture <id> --workdir <dir>`. #132 independently pins the checked-in manifest digest, rejects direct fixture directory/manifest/payload symlinks, rejects empty fixture versions and refuses a directly symlinked workdir root with `WORKDIR_UNSAFE_PATH`. #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4).

The fixture/start command is part of the M2 local synthetic workflow Claude confirmed reached. #144/#145 prove isolated-venv install/start, exact `run_record.json`, explicit false flags and installed console-script no-engine-import. #160 adds the intermediate-ancestor `PermissionError` denial/mutation proof before workdir/run-record creation. #161 adds atomic temp+fsync+exclusive-hard-link publication; it does not complete strict provenance validation. Main `_check_provenance()` still accepts float `1.0`, permits naive ISO timestamps and does not compare envelope/manifest `created_at`; `_write_report()` omits required provenance fields. #157 binds runbook command paths/option names, while full extracted argv/value/exit/output-status binding remains follow-up. #148/#154 harden backup snapshots/manifests; #159 maps B10 to the real-writer OS-lock observer, but deterministic kernel-confirmed contention remains follow-up.


## 2.2 Backup/restore component on main (#120/#127)

The current CLI dispatch supports:

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The backup command checks the source chain against its sidecar, requires a synthetic run record, rejects unsafe paths, validates listed files, re-verifies the copied chain/anchor and re-hashes restored files. #148 source snapshot locking and one manifest snapshot for verify/restore are merged (CI `45026655360`, 4/4); #154 strict manifest validation is merged (CI `45037406804`, 4/4); #159 maps B10 to the real-writer OS-lock observer (CI `45045492204`, 4/4), with deterministic kernel-confirmed contention still a follow-up. #160 adds the pilot ancestor-`lstat` PermissionError proof; #161 adds atomic run-record publication. Claude's M2 rehearsal records backup/verify/restore and tamper denials. #157 binds runbook paths/options, but exact argv/value/output-status matching remains follow-up.

## 3. Preconditions and fixture rules

Use a disposable local project and temporary evidence directory. Prepare only:

- a small UTF-8 CSV containing invented synthetic rows and stable synthetic record IDs;
- a strict schema with declared types and `public` or `internal` sensitivity for every column;
- a versioned ontology pack and binding file with exact IDs and property mappings;
- an exact project scope and synthetic decision evidence references;
- separate temporary paths for tabular, decision and audit stores.

Do not include names, emails, phone numbers, addresses, government identifiers, real customer details, secrets, tokens or free-text personal notes. Review the fixture before import. Do not use `latest` where an exact immutable import/version ID is required.

## 4. Step A — governed import inside pilot start

**Status: AVAILABLE — governed synthetic import inside `agora pilot start`; standalone import is denied.**

Do not invoke `agora data import-csv` as a standalone operator step: protected mode returns `POLICY_DENIED` because the command does not carry a Principal. The `pilot start --fixture synthetic-units-v1 --workdir <new-empty-directory>` flow performs the governed import as its `import` stage under the synthetic Principal. After a successful pilot start, use the exact recorded `import_id` with the read-only inspection commands:

```bash
agora data snapshots --project <project>
agora data show --project <project> --import-id <EXACT_IMPORT_ID>
agora data rejected --project <project> --import-id <EXACT_IMPORT_ID>
```

Stop on any policy, schema or validation denial. Do not weaken validation or infer a moving `latest` import.

## 5. Step B — validate and materialize the ontology binding

**Status: AVAILABLE — Python API; protected Principal-bound policy gate implemented (#113); synthetic identity only**

The available API surface is:

```python
from agora.ontology.binding import (
    load_binding,
    validate_binding,
    materialize_instances,
)

binding = load_binding("./fixtures/pilot-binding.yaml")
# Load the reviewed ontology pack using the repository's ontology loader.
validate_binding(ontology_pack, snapshot_manifest, binding)

instances = materialize_instances(
    binding,
    ontology_pack,
    project_path,
    exact_import_id,
    policy=policy_callable,
    purpose="synthetic_pipeline_demo",
    retention="short_lived_test",
)
```

Use the exact committed snapshot ID and a reviewed, versioned ontology pack/binding. Supply a `BoundPolicy` returned by `principal_policy()`; protected `enforce_policy()` requires this typed capability under `PRINCIPAL_BOUND_REQUIRED=True`, rejects raw callables and re-evaluates the bound Principal on each call. #111 restricts role-string PDP imports to the internal allowlist and makes the role-string approval authorizer private; #113 closes the M1 protected policy-provenance gate. Explicitly pass purpose and retention. The only adapter remains `SyntheticFixtureAdapter`, which is synthetic-fixture-only and is not production authentication.

The result is an in-memory list of provenance-rich instances. This step does not persist a pipeline run or connect to the simulation engine.

## 6. Step C — build the scenario-input package

**Status: AVAILABLE — Python API; NOT wired to engine**

```python
from agora.scenario_inputs import build_scenario_input

package = build_scenario_input(
    binding,
    ontology_pack,
    project_path,
    exact_import_id,
    scenario_parameters=synthetic_parameters,
    transformation_policy=None,
    policy=policy_callable,
)
```

Use exact immutable IDs and a policy callable. The package contains a manifest, scenario hash, instances and run-record metadata. The API rejects the moving selector `latest`.

**Hard boundary:** the package is not imported or consumed by `agora/sim/engine.py`. Do not claim that a subsequent engine run used these bound instances. Simulation wiring is a separate blocked task requiring Claude's written approval and a separate owner-approved execution step. Do not edit `agora/sim/**`.

## 7. Step D — create a decision and use the principal approval slice

**Status: AVAILABLE — Python APIs; synthetic Principal path; no production identity provider**

The decision schema/store and lifecycle are Python APIs; there is no single decision-record CLI workflow. The principal slice on main provides:

- `agora.principal.Principal` — immutable principal value;
- `SyntheticFixtureAdapter` — test-only adapter that refuses production mode and issues principals from predeclared fixture keys;
- `decide_principal()` — principal-based PDP decision;
- `BoundPolicy` / `principal_policy()` — typed policy capability re-evaluated against the bound Principal on every call;
- `agora.decisions.approval.approve_as()` — approval entry point with no caller-supplied role parameter.

#111 restricts role-string PDP/permission imports to the internal allowlist and makes the legacy role-string approval authorizer private. #113 makes protected `enforce_policy()` reject raw callables. This closes the M1 protected Principal-bound policy gate; the adapter remains synthetic-only.

For a synthetic-only rehearsal, define fixture identities in code/configuration controlled by the test harness (not request fields), issue a predeclared approver fixture, and call `approve_as(store, decision_id, expected_version, principal=approver_principal, expected_fingerprint=..., expected_scope=..., expected_evidence_refs=..., audit=...)` after a separate proposer and reviewer have prepared/reviewed the exact proposal.

The API checks the exact current version, fingerprint, scope, evidence references, review date and separation of duties. #80/#84 make `approve_as()` Principal-native and derive policy input from the stored decision. #96 removes its public `require_anchored=False` opt-out kwarg. #97 removes the `AGORA_TEST_ONLY_LEGACY_APPROVE` env switch; legacy `approve()` is enabled only by the test-only `LEGACY_APPROVE_ENABLED` module flag. `SyntheticFixtureAdapter` is not production authentication.

## 8. Step E — audit evidence

**Status: AVAILABLE — local-sidecar API; protected denial writer required; trust limitation remains**

Main contains the local append-only hash chain from #38/#47 and the merged local-sidecar implementation from #63. #74 wires lifecycle/outcome appends and #75 introduces the structural `AuditAppender` protocol. The API includes `AnchorStore`, `AnchoredAuditChain`, `bootstrap_anchor()`, and `verify_anchored()`. `AnchoredAuditChain.append()` serializes the verify → chain append → anchor advance sequence with a cross-process sidecar lock and fails closed when the existing chain/anchor state is not cleanly verified. If the chain append succeeds but anchor persistence fails, `AnchorWriteError` reports a partial failure; do not retry the protected business operation or describe it as fully audited.

The anchor is a separate local JSONL sidecar with owner-only creation permissions and fsync on append. Its reported trust level is `local_sidecar`: it detects chain truncation/rollback only while the anchor survives independently. It does not protect against an attacker who can rewrite both local files, and it is not an external or independently hosted anchor. PR #63's exact-head Actions run 44917009154 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The Linux 3-process mutation test did not detect removal of the lock, so that particular lock-coverage proof remains a stated limitation.

**Integration status on main after #119:**

- #96 removes the `require_anchored` opt-out kwargs from `approve_as()`, `record_outcome_as()` and `review_outcome_as()`; public callers cannot pass `False`. #92 retires the public role-string outcome exports.
- #92 removes public `record_outcome()` / `review_outcome()` exports. `record_outcome_as()` / `review_outcome_as()` are the public routes; #96 removes their public `require_anchored=False` opt-out kwargs.
- `approve()` remains default-deny; #97 removes the environment switch and permits enablement only through the test-only `agora.protection.LEGACY_APPROVE_ENABLED` flag.
- #99 removes the direct `require_policy` override. When `ANCHOR_REQUIRED=True`, `enforce_policy()` requires `require_anchored(audit)` for denial writes and rejects `None`, plain `AuditChainStore` and duck-typed non-anchored writers; #99 exact-head CI run `44960946006` passed 4/4.
- #109 adds the same pre-mutation guard to `propose()`, `reject()`, `expire()` and `supersede()`; exact-head CI run `44975437439` passed all four matrix jobs.
- #111 makes the role-string approval authorizer private and restricts direct PDP imports to the internal allowlist; #113 requires `BoundPolicy` for protected `enforce_policy()` and re-checks the bound Principal (exact-head CI `44979668275`, 4/4).
- #107 adds `agora audit timeline --decisions <db> --audit <db> --decision-id <id>` and `agora audit verify --audit <db> --anchor <file> --chain-id <id>`. Timeline verifies the hash chain before listing the selected decision; verify compares the chain with the local anchor. Timeline does not check the anchor itself; neither command repairs data.

## 9. Step F — record and review an observed outcome

**Status: AVAILABLE — Principal public routes; synthetic identity only**

The #53 implementation provides `DecisionOutcomeStore` and append-only outcome/review storage. After #92, the public write routes are `record_outcome_as()` / `review_outcome_as()`; the role-string `_record_outcome()` / `_review_outcome()` helpers are private implementation details. The path requires an approved decision version, exact declared measure, measurement window, exact source reference with a content hash and `provenance_class="observed"`. The reviewer must differ from the recorder; corrections append a new record.

There is no separate outcome CLI. PR #70 adds Principal-gated wrappers; #86 ignores caller-supplied resource data; #89 defaults their anchor check on; #92 retires public role-string outcome exports; #96 removes public `require_anchored=False` kwargs. The public wrapper gate is not bypassable through that keyword, although private helper audit remains optional internally.

#147 persists marker-open audit intent; #149 adds real-chain same-payload replay; #151 requires anchored-valid lookup and stable transition IDs; #152 adds two independent replay callers (exact-head CI `45034452114`, 4/4). Its barrier is before the pending-row query, so a delivery-boundary handshake remains a post-M2 test-strengthening item. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open. M2 is Claude-confirmed reached; the latest logged Claude command is `docs/M3_DESIGN.md`, with no M3 owner go recorded.
### Read-only decision/audit reconciliation detector (#100)

The available command is:

```bash
agora reconcile --decisions ./data/decisions.sqlite3 --audit ./data/audit_chain.sqlite3 --anchor ./data/audit_anchor.jsonl --chain-id <CHAIN_ID>
```

It opens the decision and audit stores read-only. #119 verifies the audit chain against the configured sidecar before classification, and #122 holds the same anchor lock across verification and classification, closing the TOCTOU gap. The lock helper may create a `.lock` metadata file and the concurrency test still uses a fixed sleep rather than a deterministic handshake. The CLI requires `--anchor` and `--chain-id`; it lists lifecycle/approval transitions as `matched`, `missing`, `conflict` or `source_invalid`, plus orphan lifecycle events. Exit codes: `0` = no detected gaps; `1` = gaps listed; `2` = blocked with no classifications. #104 validates immutable transition metadata, expected audit operation and exact resource IDs, and closes connections on partial open. #115 is a separate API-only repair for missing decision events; it does not cover outcomes/reviews or unanchored-tail recovery. See `docs/RECONCILIATION_SPEC.md`.

## 10. Step G — generate a separate simulated-labelled report

**Status: AVAILABLE — separate exploratory/mock path**

The existing engine/report path is separate from Steps A–F. The scenario-input package is not consumed by the engine. Do not run the following smoke commands as part of this documentation task; they describe the separate exploratory/mock path only. A standalone mock smoke test can use:

```bash
agora new ./engine-smoke --from demo
agora check ./engine-smoke --mock
agora run ./engine-smoke --mock
agora status ./engine-smoke
agora report ./engine-smoke --mock
```

Inspect the demo template first and replace it only with a small approved synthetic scenario appropriate to the rehearsal. Preserve run ID, scenario hash, backend/mode and report provenance. The report is exploratory/simulated output only. It does not consume the Step C package and does not validate demand, sales, causal effects or predictions.

## 11. Post-M2 hardening and explicit blockers

M2 was confirmed reached by Claude at 23:43 IST on 22 November 2026 on main `7432a10674a531d866d851de78402520e6a4eee8`; exact-head CI `45052033418` passed 4/4. The synthetic dress rehearsal is recorded in `docs/M2_DRESS_REHEARSAL_PLAN.md`. The items below are follow-up hardening and known limitations, not a reversal of Claude's milestone confirmation.

1. **Run provenance:** #161 makes run-record publication atomic (temp file, flush/fsync, exclusive hard-link publish and cleanup; CI `45051090990`, 4/4). Follow-up strictness remains: reject float `provenance_version=1.0`, require timezone-aware RFC3339, compare envelope/manifest timestamps and include dataset/schema, binding, ontology, policy, data-role and source-hash fields in reports.
2. **Runbook binding:** #157 binds runbook code-fence command paths and option names to the inventory, and the inventory templates run as subprocesses. Future strengthening should execute extracted runbook argv and compare every argument value, expected exit, required output/status token and named proof.
3. **Backup B10:** #159 maps B10 to the real-writer test, but its observer is immediately before the OS lock call; the companion test still uses factory-entry signaling and a timeout. Replace this with kernel-confirmed contention.
4. **Marker lifecycle:** #152's barrier is before pending-row delivery; add a handshake after both independent callers fetch the same row. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open.
5. **Anchor trust:** `local_sidecar` detects tampering only while the anchor remains safe; coordinated rollback of both local files is not detected. No independent external anchor is included.
6. **Hard boundary:** scenario-input wiring into `agora/sim/**`, any simulation, real data, connectors, credentials and write-back remain blocked without Claude's written approval and separate owner approval naming the item. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 12. Current mainline pilot commands and future operator work

The current merged local synthetic commands on main `7432a10674a531d866d851de78402520e6a4eee8` are:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

The fixture-selected `start` path, clean-install proof (#144/#145), pilot path-failure proof (#160), runbook/inventory binding (#157) and atomic run-record publication (#161) are all on main. Claude's 23:43 IST entry confirms M2 reached and records a nine-stage synthetic pilot, audit verification, reconciliation, held-outcome listing, backup/restore and tamper drills. Follow-up provenance strictness, full runbook argv/value/status matching, B10 kernel-confirmed contention, replay delivery-boundary proof and marker reconciliation remain visible; no simulation engine was run.
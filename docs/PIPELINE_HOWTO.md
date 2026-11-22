# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** M1 was explicitly confirmed by Claude. Main is `400666bd90da5834c68bfdcb4dbc135640f99aa0` after #144 merged (clean-install CI `45015043801`, 4/4; #142 provenance CI `45013670475`, 4/4); #141's command-inventory test passed 4/4 but does not read `docs/OPERATOR_RUNBOOK.md`. The run-record `input_provenance` envelope is now on main, but strict legacy/new validation, full manifest/report checks and failure-atomic publication remain open. M2 remains incomplete: #144 proves clean-checkout install/start (head 38884bc8; exact-head CI 45015043801 passed 4/4); backup manifest single-read and real-writer proof, marker/audit outbox recovery, direct runbook binding and logged rehearsal remain open.
**Assessment base:** `main` at `400666bd90da5834c68bfdcb4dbc135640f99aa0` (22 November 2026).
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

Main `400666bd90da5834c68bfdcb4dbc135640f99aa0` includes #144's isolated-venv clean-install/start proof and has the guided M1 command `agora pilot --workdir <new-empty-directory>` (#88), checked-in fixture/start (#125), baseline loader/workdir guard (#130), fixture/manifest and path hardening (#132/#135/#139), backup guards (#136), and copied-chain/manifest binding (#138). #142 now calls `build_scenario_input()` during pilot bind and persists `input_provenance`; strict legacy/new, timestamp/version, manifest/report checks and failure-atomic publication remain open. #138 still lacks writer-side lock and single-read manifest validation. Pilot intermediate-ancestor lstat-failure coverage remains open. #144 proves clean-checkout install/start (head 38884bc8; exact-head CI 45015043801 passed 4/4); direct runbook binding, marker/audit outbox and rehearsal remain open.

M2 is not complete: #141 adds a tested command inventory, but the operator-runbook file is not the test source-of-truth. #142 adds the run-record envelope on main, but strict legacy/new validation, timestamp/schema/report checks and failure-atomic publication remain open.

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
| Backup/restore | **MERGED SYNTHETIC CLI (#120/#127/#134/#136/#138/#139); operator drill pending** | #138 compares exact sequence/head and binds them in the manifest (CI `45009045175`, 4/4); no writer-side lock and manifest re-read gap remain. #139 closes B13 path normalization on backup and pilot (CI `45011493565`, 4/4). Single-read manifest validation and deterministic concurrent-writer proof remain open. |
| Observed outcome recording/review | **AVAILABLE — Principal public routes; protected public wrappers** | #92 retires public role-string exports and #96 removes public `require_anchored=False` kwargs. Private helper audit can still be omitted internally; this is not a public caller bypass. |
| Outcome dependency review markers | **PARTIAL — first slice plus #122 lifecycle hardening** | #116 adds explicit-edge marker propagation; #122 makes audit-append failure roll back the marker transition and binds supersession to the same decision/version/object with a bounded reason. A marker DB commit failure after successful audit append can still leave an orphan audit event; marker/audit reconciliation, retention/erasure triggers, automatic report/run edges and CLI remain open. |
| Decision/audit reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verify/classify; #115 repairs missing decision events through an approver-authorised API only. The lock helper may create a sidecar `.lock` file, and the concurrency test uses a timing sleep; no outcome/review reconciliation or unanchored-tail recovery is included. |
| M2 run record | **PARTIAL — #142 merged** | #142 stores `input_provenance` and verifies canonical manifest/scenario hashes, exact import ID and role. It still accepts missing provenance as legacy for any record, permits non-strict timestamps/version typing, does not validate all manifest fields or report metadata, and publishes with a non-atomic direct write. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **AVAILABLE — M1 flow plus M2 fixture/start component** | Main provides the nine-stage `agora pilot --workdir` flow and #125 fixture-selected `agora pilot list/start`. #132 pins the manifest/direct fixture paths; #135 refuses workdir ancestors and filters linked fixture directories; #139 refuses lexical `..` before path normalization. Pilot intermediate-ancestor lstat-failure coverage remains open. #144 proves clean-checkout install/start (head 38884bc8; exact-head CI 45015043801 passed 4/4).  Full run-record provenance/atomic publication remains open. |

## 2.1 Guided synthetic pilot command on main (#88/#125; CLI import isolation #94)

The merged CLI dispatches `agora pilot` from `agora.cli.main()` to `agora.pilot.main()`. The supported invocation is:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

Use a new empty local work directory. Main includes `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and `agora pilot list` / `agora pilot start --fixture <id> --workdir <dir>`. #132 independently pins the checked-in manifest digest, rejects direct fixture directory/manifest/payload symlinks, rejects empty fixture versions and refuses a directly symlinked workdir root with `WORKDIR_UNSAFE_PATH`. #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories. #144 proves clean-checkout install/start (head 38884bc8; exact-head CI 45015043801 passed 4/4).

The fixture/start command is a merged M2 component, not an M2-complete operator workflow. #125 adds fixture ID/version/manifest/file hashes; #130 adds baseline strict required-field/type/hash checks; #132/#135/#139 harden fixture and workdir paths. #142 integrates `build_scenario_input()` into pilot bind and persists the provenance envelope; strict legacy/new, timestamp/version, manifest/report validation and failure-atomic publication remain open. Pilot intermediate-ancestor lstat-failure coverage remains open. #144 proves clean-checkout install/start (head 38884bc8; exact-head CI 45015043801 passed 4/4).  #138 adds copied-chain sequence/head comparison and manifest-head validation; writer-side lock and single-read manifest validation remain open.


## 2.2 Backup/restore component on main (#120/#127)

The current CLI dispatch supports:

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The backup command checks the source chain against its sidecar, requires a synthetic run record, rejects in-tree symlinks/unsafe paths, validates the manifest, re-verifies the copied chain/anchor and re-hashes restored files. #134 rejects direct roots; #136 adds ancestor/pre-read/lstat-error guards; #138 compares copied-chain sequence/head with the source verdict and records/verifies the manifest head (CI `45009045175`, 4/4). No writer-side lock is present, and verify/restore re-read the manifest after validation. #139 closes B13 lexical `..` refusal (CI `45011493565`, 4/4). Pilot intermediate-ancestor lstat-failure coverage, runbook test and tamper drill remain outstanding.

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

#116's first append-only marker slice is merged; #122 fixes the original audit-failure-before-commit and supersession-scope gaps. A marker-store commit failure after the audit append succeeds can still leave an orphan audit event, and marker/audit reconciliation is absent. #119 plus #122 hold the anchor lock across reconcile verification/classification, but the lock helper may create a `.lock` file and its concurrency test relies on a fixed sleep. Retention/erasure triggers, automatic report/run edge registration, a CLI and outcome/review marker-audit reconciliation remain open.
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

## 11. Remaining work for M2 operator readiness

The following M2 gaps remain on main `400666bd90da5834c68bfdcb4dbc135640f99aa0` after Claude's M1 confirmation and merged #88/#100/#104/#119/#122 detector, #102/#106 held-outcome list, #116/#122 marker lifecycle, #120 backup CLI, #123 initial run record, #125 fixture/start, #127 backup hardening, #130 partial strict loader, #132 fixture hardening, #134 direct backup-root guards and #135 workdir-ancestor guards. The owner approved local synthetic M2; M2 remains incomplete:

1. Complete marker/audit cross-store failure handling: #122 rolls back marker state when audit append fails, but if the audit append succeeds and the later marker DB commit fails, an orphan audit event can remain. Add a commit-failure regression and durable pending/outbox or reconciliation semantics. Retention/erasure triggers, automatic report/run edges and marker/audit reconciliation also remain open.
2. Reconciliation's #119 verify/classify TOCTOU is serialized by #122's shared anchor lock. Clarify the lock-file creation side effect under the read-only contract and replace the fixed-sleep race test with a deterministic handshake; add stable correlation IDs and a reviewed queue/repair contract, and separately cover outcome/review audit rows.
3. Harden the #142 immutable operator run record against the remaining `RUN_PROVENANCE_SPEC.md` gaps: distinguish legacy records from newly written records missing the envelope; enforce strict timezone-aware RFC3339 and integer version types; validate manifest fields and timestamp equality; include required provenance in reports/exports; and publish failure-atomically with partial-write mutations.
4. Close the remaining fixture/start gaps after #132: reject symlinked workdir ancestors (not only the final workdir component), add explicit symlink tests for each schema/binding payload file, and prove package installation/start from a clean checkout. Direct fixture directory/manifest/payload symlinks, independent manifest pinning, empty versions and direct workdir-root symlinks are already on main.
5. #138 now detects copied-chain sequence/head mismatch and validates the manifest head, but no writer-side lock exists and verify/restore re-read the manifest after validation. #139 closes B13 path refusal. Add single-read manifest validation, manifest-replacement mutation proof and a barrier-controlled real-writer interleaving; then complete the synthetic tamper drill, tested operator runbook commands and logged dress rehearsal.
6. Scenario-input-to-engine integration remains separately blocked; do not edit `agora/sim/**` or run a simulation.

## 12. Current mainline pilot commands and future operator work

The current merged local synthetic commands on main `400666bd90da5834c68bfdcb4dbc135640f99aa0` are:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

The fixture-selected `start` path from #125 is a merged M2 component, not an M2-complete installer/runbook. #132 pins the manifest digest, rejects direct fixture directory/manifest/payload symlinks, empty fixture versions and a directly symlinked workdir root; #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories. #144 adds an isolated-venv install/start proof: the installed CLI runs outside the repository, resolves from the venv, finds the packaged fixture, keeps both safety flags false and does not import agora.sim (CI 45015043801, 4/4). The legacy M1 path uses the embedded fixture by default. Neither path invokes the simulation engine. No command in this guide authorises execution during a documentation-only review.
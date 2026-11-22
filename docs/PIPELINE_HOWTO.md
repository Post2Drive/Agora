# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** M1 was explicitly confirmed by Claude. Main `932dfbc4dcb200c53da86bc8580b219eee877076` includes #154/#155; M2 remains incomplete. #154 strict manifest version/sequence/hash validation is merged (exact-head CI `45037406804`, 4/4). #155 (test-only B10 lock-handshake) is merged at exact head `943d707ac1a67772ca82383c4f00c82c31806fee`; exact-head CI run `45039917180` passed 4/4. Main is now `932dfbc4dcb200c53da86bc8580b219eee877076`. Claude's 21:21 IST entry claims runbook-binding in `tests/test_runbook_commands.py` next. #152's barrier still precedes the pending-row delivery boundary; it does not prove both replay callers fetched the same pending row before delivery. Legacy-marker backfill and outcome/review marker-audit reconciliation remain open. #141 still tests the inventory, not `OPERATOR_RUNBOOK.md`; exact numeric exits, required status tokens and named proof mapping remain open. #142 provenance still needs strict legacy/new discrimination, exact version types, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication. The pilot intermediate-ancestor `lstat` failure mutation proof is missing. M2 remains incomplete.

**Assessment base:** main `932dfbc4dcb200c53da86bc8580b219eee877076` (22 November 2026).
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

Main `932dfbc4dcb200c53da86bc8580b219eee877076` includes marker-open outbox/replay (#147/#149), anchored-valid lookup and stable transition retry (#151), two-caller replay test (#152), source snapshot lock/single manifest snapshot (#148), strict manifest typing (#154) and B10 event-based lock-handshake test (#155). Exact-head CI for #154/#155 passed 4/4. #152's start barrier does not prove both callers fetched the same pending row before delivery. Claude's current claim is runbook-binding in `tests/test_runbook_commands.py`; M2 remains incomplete.

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
| Backup/restore | **MERGED SYNTHETIC CLI (#120/#127/#134/#136/#138/#139/#148/#154/#155); operator drill pending** | #148 adds source writer-lock and single manifest snapshot for verify/restore (CI `45026655360`, 4/4); #154 adds strict manifest version/sequence/hash validation (CI `45037406804`, 4/4); #155 adds B10 event-based real-writer lock test (CI `45039917180`, 4/4). Logged tamper drill remains outstanding. |
| Observed outcome recording/review | **AVAILABLE — Principal public routes; protected public wrappers** | #92 retires public role-string exports and #96 removes public `require_anchored=False` kwargs. Private helper audit can still be omitted internally; this is not a public caller bypass. |
| Outcome dependency review markers | **PARTIAL — marker-open replay and stable transition retry (#147/#149/#151); two-caller test merged (#152), backfill pending** | #147/#149/#151/#152 are merged; #152's barrier precedes pending-row delivery, so add a delivery-boundary handshake. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged). Outcome/review marker-audit reconciliation remains separate. |
| Decision/audit reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the sidecar and #122 holds the same anchor lock across verify/classify; #115 repairs missing decision events through an approver-authorised API only. The lock helper may create a sidecar `.lock` file, and the concurrency test uses a timing sleep; no outcome/review reconciliation or unanchored-tail recovery is included. |
| M2 run record | **PARTIAL — #142 merged** | #142 stores `input_provenance` and verifies canonical manifest/scenario hashes, exact import ID and role. It still accepts missing provenance as legacy for any record, permits non-strict timestamps/version typing, does not validate all manifest fields or report metadata, and publishes with a non-atomic direct write. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **AVAILABLE — M1 flow plus M2 fixture/start component** | Main provides the nine-stage `agora pilot --workdir` flow and #125 fixture-selected `agora pilot list/start`. #132 pins the manifest/direct fixture paths; #135 refuses workdir ancestors and filters linked fixture directories; #139 refuses lexical `..` before path normalization. Pilot intermediate-ancestor lstat-failure coverage remains open. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4).  Full run-record provenance/atomic publication remains open. |

## 2.1 Guided synthetic pilot command on main (#88/#125; CLI import isolation #94)

The merged CLI dispatches `agora pilot` from `agora.cli.main()` to `agora.pilot.main()`. The supported invocation is:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

Use a new empty local work directory. Main includes `agora/pilot_fixtures/synthetic-units-v1` with CSV/schema/binding/manifest and `agora pilot list` / `agora pilot start --fixture <id> --workdir <dir>`. #132 independently pins the checked-in manifest digest, rejects direct fixture directory/manifest/payload symlinks, rejects empty fixture versions and refuses a directly symlinked workdir root with `WORKDIR_UNSAFE_PATH`. #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories. #144/#145 prove clean-checkout install/start and exact run-record/flag/console-script assertions (head 6338c5a5; exact-head CI 45021238785 passed 4/4).

The fixture/start command is a merged M2 component, not an M2-complete operator workflow. #144/#145 prove isolated-venv install/start, exact `run_record.json`, explicit false flags and installed console-script no-engine-import. `pilot._linked_component()` fails closed on lstat errors in code, but `tests/test_pilot.py` still lacks an intermediate-ancestor `PermissionError` mutation proof asserting denial before workdir/run-record creation. #142 stores the pilot `input_provenance` envelope and checks core hashes/import/role; strict legacy/new discrimination, exact version types, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication remain open. #148 source snapshot locking and one manifest snapshot for verify/restore are merged (CI `45026655360`, 4/4); #154 strict manifest typing is merged (CI `45037406804`, 4/4). #155's B10 event handshake is open/draft with exact-head CI `45039917180` 4/4 but not merged; main still uses bounded `join(timeout=1.5)`. #141 tests the inventory only, not `docs/OPERATOR_RUNBOOK.md`; exact exit/status assertions and named proof mapping remain open. B10 inventory mapping must point to the #148 real-writer test, not the older copied-chain test; B12 needs an explicit named mapping.


## 2.2 Backup/restore component on main (#120/#127)

The current CLI dispatch supports:

```bash
agora backup --project <project-dir> --dest <new-empty-backup-dir>
agora backup verify --backup <backup-dir>
agora restore --backup <backup-dir> --target <new-empty-target-dir>
```

The backup command checks the source chain against its sidecar, requires a synthetic run record, rejects unsafe paths, validates listed files, re-verifies the copied chain/anchor and re-hashes restored files. #148 source snapshot locking and one manifest snapshot for verify/restore are merged (CI `45026655360`, 4/4); #154 strict manifest validation is merged (CI `45037406804`, 4/4); #155 B10 event-based real-writer lock test is merged (CI `45039917180`, 4/4). #139 closes B13; the logged tamper drill and direct runbook binding remain outstanding.

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

#147 persists marker-open audit intent; #149 adds real-chain same-payload replay; #151 requires anchored-valid lookup and stable transition IDs; #152 adds two independent replay callers (CI `45034452114`, 4/4). Its barrier precedes pending-row delivery, so add a delivery-boundary handshake. Legacy-marker backfill remains open; Claude's current claim is runbook-binding (#155 merged). Outcome/review marker-audit reconciliation remains separate.
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

The following M2 gaps remain on main `932dfbc4dcb200c53da86bc8580b219eee877076`. M2 remains incomplete. Claude's current claim is runbook-binding in `tests/test_runbook_commands.py`. After the claimed runbook-binding slice, remaining M2 gaps are pilot intermediate-ancestor `lstat` failure mutation coverage; strict legacy/new run-provenance validation, timezone-aware RFC3339, manifest/envelope timestamp equality, complete report/export fields and failure-atomic publication; outcome/review marker-audit reconciliation; held-outcome/reconcile runbook integration; and a separately approved, logged synthetic dress rehearsal. No rehearsal is claimed.

1. **Legacy-marker backfill:** remains open but is not Claude's current claim. Claude's current claim is runbook-binding in `tests/test_runbook_commands.py`. After that, close the pilot-path, provenance, outcome/review reconciliation and separately approved rehearsal gates.
2. Reconciliation's #119 verify/classify TOCTOU is serialized by #122's shared anchor lock. Clarify the lock-file creation side effect under the read-only contract and replace the fixed-sleep race test with a deterministic handshake; add stable correlation IDs and a reviewed queue/repair contract, and separately cover outcome/review audit rows.
3. Harden the #142 immutable operator run record against the remaining `RUN_PROVENANCE_SPEC.md` gaps: distinguish legacy records from newly written records missing the envelope; enforce strict timezone-aware RFC3339 and integer version types; validate manifest fields and timestamp equality; include required provenance in reports/exports; and publish failure-atomically with partial-write mutations.
4. Remaining pilot path-test gap: add intermediate-ancestor lstat-failure coverage to the pilot workdir walker. #135 already covers symlinked schema/binding payloads and workdir ancestors; #144 proves isolated-venv package installation and installed CLI start from outside the checkout. Direct fixture directory/manifest/payload symlinks, independent manifest pinning, empty versions and direct workdir-root symlinks are already on main.
5. #148 now holds the source anchor-writer lock across the complete backup snapshot, excludes the sidecar lock file, and reuses one manifest snapshot for verify/restore (CI `45026655360`, 4/4). #139 closes B13 path refusal. Add exact manifest version/sequence/hash type validation and replace bounded-join B10 proof with deterministic barrier/event synchronization; then complete the synthetic tamper drill, tested operator runbook commands and logged rehearsal.
6. Scenario-input-to-engine integration remains separately blocked; do not edit `agora/sim/**` or run a simulation.

## 12. Current mainline pilot commands and future operator work

The current merged local synthetic commands on main `932dfbc4dcb200c53da86bc8580b219eee877076` are:

```bash
agora pilot list
agora pilot start --fixture synthetic-units-v1 --workdir ./tmp-agora-pilot
# Legacy M1 path remains available:
agora pilot --workdir ./tmp-agora-pilot
```

The fixture-selected `start` path from #125 is a merged M2 component, not an M2-complete installer/runbook. #132 pins the manifest digest, rejects direct fixture directory/manifest/payload symlinks, empty fixture versions and a directly symlinked workdir root; #135 rejects workdir symlink/reparse-point ancestors and filters linked fixture directories; #139 refuses lexical `..`. #144/#145 prove isolated-venv install/start, exact `run_record.json` and explicit false flags, and installed console-script no-engine-import (CI `45021238785`, 4/4). Pilot workdir ancestor walking fails closed on `lstat` errors in code, but `tests/test_pilot.py` still lacks an intermediate-ancestor `PermissionError` mutation proof; backup has its own lstat-error test. Add the matching pilot test and assert denial before workdir/run-record creation. #142 provenance remains partial; strict schema/report validation and failure-atomic publication remain open. #148 source snapshot locking and one manifest snapshot for verify/restore are merged (CI `45026655360`, 4/4); #154 strict manifest version/sequence/hash typing is merged (CI `45037406804`, 4/4). Remaining backup gap: deterministic B10 event/lock-acquisition synchronization instead of bounded `join(timeout=1.5)`.
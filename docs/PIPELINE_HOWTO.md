# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** M1 was explicitly confirmed by Claude; M2 operator workflow remains incomplete and implementation awaits owner GO.  
**Assessment base:** `main` at `30385885f16b3750a879ef7df25140fabe29c4ba` (22 November 2026).
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

Main has the guided local command `agora pilot --workdir <new-empty-directory>` (#88), with per-stage results, first-denial stop, anchored audit verification and a synthetic-labelled report. Claude's exact 09:05 IST log entry confirms M1 reached on main `83d0645b983365dddd9da07d4d1352e0b66e3d00`; current main is `30385885f16b3750a879ef7df25140fabe29c4ba` after #119 merged. #111 restricts role-string PDP imports to the internal allowlist and makes the role-string approval authorizer private; #113 enforces Principal-bound `BoundPolicy` callbacks in protected mode. #115 adds an API-only missing-decision-event repair requiring an approver Principal, clean anchor and exact audit head. #116 adds the first append-only outcome dependency-marker slice. #119 verifies the audit chain against its local sidecar read-only before reconciliation classification and requires `--anchor` plus `--chain-id`. Review found a possible TOCTOU window because #119 closes the verification connection before the classification connection is opened; concurrent-writer atomicity is not yet established.

M2 is not complete: the pilot still uses in-module synthetic CSV/schema/binding, does not persist the `RUN_PROVENANCE_SPEC.md` envelope, and has no backup/restore/tamper drill or tested operator runbook. The marker slice still lacks retention/erasure triggers, automatic report/run edge registration, CLI and marker/audit reconciliation. Scenario-input remains disconnected from the engine; no simulation wiring or run is authorised.

This guide documents the available components and their boundaries. It does not authorise a simulation, calibration, backtest, forecast, study mutation, live pilot, production decision, real data, credentials, network access or external write-back. Do not use Nutrivance, NCC Park Square, customer records or any real personal/sensitive data. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Capability status at this assessment base

| Pipeline stage | Status on merged main | What is actually available |
|---|---|---|
| Synthetic CSV import | **AVAILABLE — CLI** | `agora data import-csv`, snapshot listing/show/rejected-row commands; immutable local snapshot and manifest. |
| Ontology binding | **AVAILABLE — Python API, protected boundary** | `load_binding`, `validate_binding`, `materialize_instances`; #96 removes the public opt-out kwarg and #99 hardens direct policy enforcement with anchored denial writes. |
| Shared policy enforcement | **DONE — Principal-bound callback enforced** | #113 introduces `BoundPolicy` and rejects raw callables in protected mode (`PRINCIPAL_BOUND_REQUIRED=True`). The adapter remains synthetic-fixture-only. |
| Scenario-input package | **AVAILABLE — Python API, disconnected** | `build_scenario_input` builds a provenance-rich package from an exact import ID. It is not consumed by `agora/sim/engine.py`. |
| Decision record and proposal | **AVAILABLE — Python API** | Decision schema/store and lifecycle APIs. |
| Principal-based approval | **AVAILABLE — partial synthetic migration** | #80/#84/#89/#96 make `approve_as()` Principal-native with stored-decision-derived policy input and no public anchor opt-out kwarg. #97 removes the legacy env switch; only the test-only `LEGACY_APPROVE_ENABLED` flag remains. |
| Anchored audit chain | **AVAILABLE — local-sidecar API; protected entry points guarded** | #63/#71/#74/#75/#89/#96/#97 provide writer, factory, append wiring and protected Principal wrappers; #99 hardens policy-denial writes and #109 guards `propose()`/`reject()`/`expire()`/`supersede()` before mutation when `ANCHOR_REQUIRED=True`. Optional annotations do not permit `None` or plain writers on protected paths. Trust is `local_sidecar`. |
| Audit timeline and chain/anchor verification | **AVAILABLE — read-only CLI (#107)** | `agora audit timeline` verifies the hash chain and lists one decision's stored transitions/related audit events; `agora audit verify` compares the chain with its local sidecar and states the trust limitation. Neither writes or repairs. |
| Observed outcome recording/review | **AVAILABLE — Principal public routes; protected public wrappers** | #92 retires public role-string exports and #96 removes public `require_anchored=False` kwargs. Private helper audit can still be omitted internally; this is not a public caller bypass. |
| Outcome dependency review markers | **PARTIAL — first slice merged (#116)** | Append-only marker/edge/event records, explicit-edge propagation, idempotent marker creation and Principal-gated lifecycle are merged. Retention/erasure triggers, automatic report/run edge registration, CLI and marker/audit reconciliation remain open. #102/#106 remain the separate read-only held-outcome list. |
| Decision/audit reconciliation | **DONE — anchored read-only detector plus API repair** | #100/#104 detect decision lifecycle gaps; #119 verifies the chain against its sidecar before classification and requires `--anchor` / `--chain-id`; #115 adds approver-authorised, anchored, exact-head, idempotent repair for missing events only. Repair has no CLI, excludes outcome/review rows and blocks unanchored-tail recovery. A concurrent-writer TOCTOU review finding remains open. |
| M2 run record | **NOT AVAILABLE in the pilot** | `agora/pilot.py` returns an in-memory `PilotResult`; it does not persist/verify the immutable `RUN_PROVENANCE_SPEC.md` envelope. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **AVAILABLE — M1-confirmed guided synthetic CLI (#88)** | `agora pilot --workdir <new-empty-directory>` runs provision/import/bind/decision/approval/outcome record/review/audit verify/report with per-stage results and first-denial stop; no engine call. Claude confirmed M1 on 22 November. It does not persist the M2 run record, use a checked-in fixture catalogue or call `build_scenario_input()`. |

## 2.1 Guided synthetic pilot command on main (#88; CLI import isolation #94)

The merged CLI dispatches `agora pilot` from `agora.cli.main()` to `agora.pilot.main()`. The supported invocation is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

Use a new empty local work directory. The pilot creates its own `synthetic-pilot` project and uses the in-module `SYNTHETIC_CSV`, schema and binding definitions; it does not use the proposed checked-in `fixtures/pilot.*` files. It reports `provision_audit`, `import`, `bind`, `decision`, `approval`, `outcome_record`, `outcome_review`, `audit_verify` and `report` results. The first denial/failure stops later stages and reports them as skipped. Its report states synthetic/simulated and `engine_invoked=false`. The `agora.pilot` module and `agora.data_cli` contain no simulation-engine import/call. PR #94 removes the module-level `.sim.engine` import from `agora.cli`; a fresh-process test proves `import agora.cli` and `agora pilot --help` do not load the engine. No simulation is invoked. The test does not yet exercise a complete `agora pilot --workdir` invocation in that fresh process.

This command is a merged M1 component, not an M2-complete operator workflow. It does not call `build_scenario_input()`, persist the immutable operator run record, use a checked-in fixture set, back up/restore stores, run a tamper drill or execute the operator runbook. Separate read-only audit timeline and chain-vs-anchor verification commands are now available through #107; the timeline checks the chain only, and the verify command checks the local sidecar. Decision/audit reconciliation (#100/#104) remains a read-only detector; merged #115 adds a separate API-only repair for missing decision audit events. It does not cover outcome/review rows or unanchored-tail recovery. Do not treat the in-code fixture as the checked-in dataset required by M2. Exact-head CI run `44945307064` passed all four jobs; no local execution is claimed by this documentation refresh.

## 3. Preconditions and fixture rules

Use a disposable local project and temporary evidence directory. Prepare only:

- a small UTF-8 CSV containing invented synthetic rows and stable synthetic record IDs;
- a strict schema with declared types and `public` or `internal` sensitivity for every column;
- a versioned ontology pack and binding file with exact IDs and property mappings;
- an exact project scope and synthetic decision evidence references;
- separate temporary paths for tabular, decision and audit stores.

Do not include names, emails, phone numbers, addresses, government identifiers, real customer details, secrets, tokens or free-text personal notes. Review the fixture before import. Do not use `latest` where an exact immutable import/version ID is required.

## 4. Step A — import the synthetic CSV snapshot

**Status: AVAILABLE — CLI**

The merged CLI exposes:

```bash
agora data import-csv --project ./pilot-project --csv ./fixtures/pilot.csv --schema ./fixtures/pilot-schema.yaml --role scenario_input
agora data snapshots --project ./pilot-project
agora data show --project ./pilot-project --import-id <EXACT_IMPORT_ID>
agora data rejected --project ./pilot-project --import-id <EXACT_IMPORT_ID>
```

Use the exact `import_id` returned by the import. Confirm accepted plus rejected rows reconcile with parsed rows, inspect the manifest and hashes, and ensure diagnostics contain only row number, column and stable error code—not raw values. Stop on schema or validation failure; do not weaken validation.

Expected local artefacts include `data/tabular.sqlite3` and an immutable import manifest. The import path is local; it does not provide external connectors or write-back.

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

#116's first append-only marker slice is merged: disputed/corrected/source-hash triggers, explicit-edge propagation, Principal-gated lifecycle and blocking-marker lookup. It does not include retention/erasure triggers, automatic report/run edge registration, a CLI or marker/audit reconciliation. Code review found that `advance_marker_as()` commits the lifecycle event before `_audit()`; an audit failure can therefore persist `resolved(valid)` or `superseded` without its required audit event, and `blocking_markers()` no longer blocks those states. Supersession also checks only that a different marker exists, not that it matches the same decision/version/affected object, and no reason is persisted. Treat both as hardening blockers before operator reliance. #102/#106 still provide the separate read-only held-outcome list. #100/#104 plus #119 provide decision lifecycle detection with sidecar verification; #115 is the separate API-only missing-event repair.
### Read-only decision/audit reconciliation detector (#100)

The available command is:

```bash
agora reconcile --decisions ./data/decisions.sqlite3 --audit ./data/audit_chain.sqlite3 --anchor ./data/audit_anchor.jsonl --chain-id <CHAIN_ID>
```

It opens the decision and audit stores read-only. #119 first verifies the audit chain against the configured sidecar and classifies only when the result is `anchored_verified`; the CLI requires `--anchor` and `--chain-id`. It then lists decision lifecycle/approval transitions as `matched`, `missing`, `conflict` or `source_invalid`, plus orphan lifecycle events. Exit codes: `0` = no detected gaps; `1` = gaps listed; `2` = blocked with no classifications. #104 validates immutable transition metadata, expected audit operation and exact resource IDs, and closes connections on partial open. #115 is a separate API-only repair for missing decision events; it does not cover outcomes/reviews or unanchored-tail recovery. Review found a possible TOCTOU gap between #119's verification and classification connections under concurrent writes. See `docs/RECONCILIATION_SPEC.md`.

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

The following M2 gaps remain after Claude's M1 confirmation and the merged #88 pilot, #100/#104/#119 reconciliation detector, #102/#106 held-outcome list and #116 first marker slice:

1. Harden #116 lifecycle transitions first: audit failure must leave the prior marker state blocking, and supersession must bind to the same decision/version/affected object with a bounded persisted reason. Then add retention/erasure triggers, automatic report/run edge registration and marker/audit reconciliation; keep explicit-edge and synthetic-only limits visible.
2. Harden #119's possible verification/classification TOCTOU window, add stable correlation IDs and a reviewed queue/repair contract, and separately cover outcome/review audit rows. Keep unanchored-tail recovery fail-closed. 
3. Persist and verify the immutable operator run record in `docs/RUN_PROVENANCE_SPEC.md`; #88 currently returns an in-memory `PilotResult` only.
4. Add the checked-in synthetic fixture set; #88 currently embeds its CSV/schema/binding in Python, and the proposed fixture paths remain absent on main.
5. Add backup/restore and tamper drills, tested operator runbook commands, and a separately approved/logged dress rehearsal; #107 has already added the read-only timeline and chain-vs-anchor verification CLI components.
6. Scenario-input-to-engine integration remains separately blocked; do not edit `agora/sim/**` or run a simulation.

## 12. Current M1 command and future operator work

The current merged local synthetic command is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

This is the guided governance workflow from #88, not a simulation command and not an M2-complete installer/runbook. It uses a new empty work directory, embedded invented data, per-stage results and fail-closed stop behaviour. It must not be described as using a checked-in fixture set or persisting a run-provenance record. No command in this guide authorises execution during a documentation-only review.
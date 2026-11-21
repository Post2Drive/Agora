# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** Capability map and operator guide; a guided synthetic CLI now exists, but M1/M2 exit gates remain open.  
**Assessment base:** `main` at `87c7cc95b3e7c231f52dca4924d6fc433c698462` (22 November 2026)  
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

Main has the guided local command `agora pilot --workdir <new-empty-directory>` (#88), with per-stage results, first-denial stop, anchored audit verification and a synthetic-labelled report. It does not call the simulation engine. It is not the full M2 operator pilot: no checked-in fixture set, durable run-record envelope, audit timeline command, reconciliation/held-outcome listing, backup/restore/tamper drill or tested runbook exists.

The repository also provides separate CLI commands and Python APIs. #89 is merged: the three data-boundary APIs default `require_policy=True`, and `approve_as()` / the Principal outcome wrappers default `require_anchored=True`. Explicit `False` overrides remain accepted, direct `enforce_policy()` still defaults off, and `audit=None` policy-denial logging remains unanchored. #86 outcome wrappers still delegate to public role-string functions, and the `AGORA_TEST_ONLY_LEGACY_APPROVE=1` escape remains. The scenario-input package remains disconnected from the simulation engine.

This guide documents the available components and their boundaries. It does not authorise a simulation, calibration, backtest, forecast, study mutation, live pilot, production decision, real data, credentials, network access or external write-back. Do not use Nutrivance, NCC Park Square, customer records or any real personal/sensitive data. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Capability status at this assessment base

| Pipeline stage | Status on merged main | What is actually available |
|---|---|---|
| Synthetic CSV import | **AVAILABLE — CLI** | `agora data import-csv`, snapshot listing/show/rejected-row commands; immutable local snapshot and manifest. |
| Ontology binding | **AVAILABLE — Python API, partial governance** | `load_binding`, `validate_binding`, `materialize_instances`; #89 makes `require_policy=True` the default. Explicit `False` and unanchored `audit=None` denial logging remain. |
| Shared policy enforcement | **AVAILABLE — partial** | #78/#79/#89 provide Principal-bound callback plumbing and default-on policy checks at three data boundaries. Direct `enforce_policy()` defaults off; `audit=None` still creates an unanchored local chain. |
| Scenario-input package | **AVAILABLE — Python API, disconnected** | `build_scenario_input` builds a provenance-rich package from an exact import ID. It is not consumed by `agora/sim/engine.py`. |
| Decision record and proposal | **AVAILABLE — Python API** | Decision schema/store and lifecycle APIs. |
| Principal-based approval | **AVAILABLE — partial synthetic migration** | #80/#84/#89 make `approve_as()` principal-native with stored-decision-derived policy input and default-on anchor check. Explicit `False` remains accepted; legacy `approve()` retains its runtime environment switch. |
| Anchored audit chain | **AVAILABLE — local-sidecar API; partial protected mode** | #63/#71/#74/#75/#89 provide writer, factory, append wiring and default-on anchor checks on three Principal wrappers. Explicit opt-out, legacy outcome paths and unanchored policy-denial fallback remain. Trust is `local_sidecar`. |
| Observed outcome recording/review | **AVAILABLE — Python API, partial principal migration** | #86 ignores caller resource data and #89 defaults Principal wrappers to anchored audit, but wrappers still delegate to public role-string functions. |
| Outcome dependency review markers | **NOT AVAILABLE** | #60 is a specification only; no marker store or propagation worker. |
| Decision/audit reconciliation | **NOT AVAILABLE** | #57 is a specification only; no queue, detector, worker or repair command. |
| M2 run record | **NOT AVAILABLE in the pilot** | `agora/pilot.py` returns an in-memory `PilotResult`; it does not persist/verify the immutable `RUN_PROVENANCE_SPEC.md` envelope. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **AVAILABLE — guided synthetic CLI (#88), partial M1 evidence** | `agora pilot --workdir <new-empty-directory>` runs provision/import/bind/decision/approval/outcome record/review/audit verify/report with per-stage results and first-denial stop; no engine call. It does not persist the M2 run record or use `build_scenario_input()`. |

## 2.1 Guided synthetic pilot command on main (#88)

The merged CLI dispatches `agora pilot` from `agora.cli.main()` to `agora.pilot.main()`. The supported invocation is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

Use a new empty local work directory. The pilot creates its own `synthetic-pilot` project and uses the in-module `SYNTHETIC_CSV`, schema and binding definitions; it does not use the proposed checked-in `fixtures/pilot.*` files. It reports `provision_audit`, `import`, `bind`, `decision`, `approval`, `outcome_record`, `outcome_review`, `audit_verify` and `report` results. The first denial/failure stops later stages and reports them as skipped. Its report states synthetic/simulated and `engine_invoked=false`; the module does not import or call the simulation engine.

This command is a merged M1 component, not an M2-complete operator workflow. It does not call `build_scenario_input()`, persist the immutable operator run record, provide a standalone audit timeline, reconcile cross-store records, list held outcomes, back up/restore stores, run a tamper drill or execute the operator runbook. Do not treat the in-code fixture as the checked-in dataset required by M2. Exact-head CI run `44945307064` passed all four jobs; no local execution is claimed by this document refresh.

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

**Status: AVAILABLE — Python API; governance is partial**

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

Use the exact committed snapshot ID and a reviewed, versioned ontology pack/binding. Supply the policy callable; do not omit it for this governed path. The policy callback contract is still legacy role-string based, so this is not yet principal-first end-to-end governance. Explicitly pass purpose and retention. Keep the fixture public/internal synthetic only.

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

**Status: AVAILABLE — Python APIs; partial migration**

The decision schema/store and lifecycle are Python APIs; there is no single decision-record CLI workflow. The principal slice on main provides:

- `agora.principal.Principal` — immutable principal value;
- `SyntheticFixtureAdapter` — test-only adapter that refuses production mode and issues principals from predeclared fixture keys;
- `decide_principal()` — principal-based PDP decision;
- `agora.decisions.approval.approve_as()` — approval entry point with no caller-supplied role parameter.

For a synthetic-only rehearsal, define fixture identities in code/configuration controlled by the test harness (not request fields), issue a predeclared approver fixture, and call `approve_as(store, decision_id, expected_version, principal=approver_principal, expected_fingerprint=..., expected_scope=..., expected_evidence_refs=..., audit=...)` after a separate proposer and reviewer have prepared/reviewed the exact proposal.

The API checks the exact current version, fingerprint, scope, evidence references, review date and separation of duties. #80/#84 make `approve_as()` principal-native and derive policy input from the stored decision. #82's legacy role-string approval gate remains runtime-enableable. #89 is merged and defaults `approve_as()` anchoring on; explicit False remains accepted. `SyntheticFixtureAdapter` is not production authentication.

## 8. Step E — audit evidence

**Status: AVAILABLE — local-sidecar API; partially wired, with opt-in gates**

Main contains the local append-only hash chain from #38/#47 and the merged local-sidecar implementation from #63. #74 wires lifecycle/outcome appends and #75 introduces the structural `AuditAppender` protocol. The API includes `AnchorStore`, `AnchoredAuditChain`, `bootstrap_anchor()`, and `verify_anchored()`. `AnchoredAuditChain.append()` serializes the verify → chain append → anchor advance sequence with a cross-process sidecar lock and fails closed when the existing chain/anchor state is not cleanly verified. If the chain append succeeds but anchor persistence fails, `AnchorWriteError` reports a partial failure; do not retry the protected business operation or describe it as fully audited.

The anchor is a separate local JSONL sidecar with owner-only creation permissions and fsync on append. Its reported trust level is `local_sidecar`: it detects chain truncation/rollback only while the anchor survives independently. It does not protect against an attacker who can rewrite both local files, and it is not an external or independently hosted anchor. PR #63's exact-head Actions run 44917009154 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The Linux 3-process mutation test did not detect removal of the lock, so that particular lock-coverage proof remains a stated limitation.

**Integration status on main after #88:**

## 9. Step F — record and review an observed outcome

**Status: AVAILABLE — Python API; principal migration partial**

The #53 implementation provides `DecisionOutcomeStore`, `record_outcome()` and `review_outcome()` in `agora.decisions.outcomes`. It requires an approved decision version, an exact declared measure, a measurement window, an exact source reference with a content hash, and `provenance_class="observed"`. The reviewer must differ from the recorder; corrections append a new record.

There is no separate outcome CLI. PR #70 adds

Outcome dependency review markers are not implemented. Reconciliation between decision and audit stores is not implemented.

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

## 11. Remaining work before M1/M2 readiness

The following gaps remain after the #88 guided pilot command:

1. #89's default-on policy/anchor parameters are now merged (run `44948055801`, 4/4 green). Remove production-capable explicit False opt-outs and make the configured anchored writer mandatory for policy-denial/data-boundary paths; `audit=None` still uses an unanchored chain.
2. Retire the public role-string `record_outcome()` / `review_outcome()` APIs and remove the runtime-enableable legacy `approve()` environment switch; keep no production-capable role-string authority path.
3. Require the same configured `AnchoredAuditChain` for policy-denial/data-boundary paths; remove unanchored `audit=None` fallback and prove denial precedes protected reads.
4. Implement decision/audit reconciliation (#57) and outcome dependency markers/held-outcome listing (#60); both remain specifications only.
5. Persist and verify the immutable operator run record in `docs/PILOT_RUN_RECORD_FIELDS.md` / `docs/RUN_PROVENANCE_SPEC.md`; #88 currently returns an in-memory `PilotResult` only.
6. Add the checked-in synthetic fixture set; #88 currently embeds its CSV/schema/binding in Python, and the proposed fixture paths remain absent on main.
7. Add readable audit timeline and plain-language verification commands, backup/restore and tamper drills, tested operator runbook commands, and a separately approved/logged dress rehearsal.
8. Scenario-input-to-engine integration remains separately blocked; do not edit `agora/sim/**` or run a simulation.

## 12. Current M1 command and future operator work

The current merged local synthetic command is:

```bash
agora pilot --workdir ./tmp-agora-pilot
```

This is the guided governance workflow from #88, not a simulation command and not an M2-complete installer/runbook. It uses a new empty work directory, embedded invented data, per-stage results and fail-closed stop behaviour. It must not be described as using a checked-in fixture set or persisting a run-provenance record. No command in this guide authorises execution during a documentation-only review.
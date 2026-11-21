# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** Capability map and operator guide; this is not an integrated end-to-end pipeline  
**Assessment base:** `main` at `d0cb5c7260f3d18643cd6a93fd6fdd4e9cbd43c9` (21 November 2026)  
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

There is **no single CLI/API entry point** on this mainline that executes import → bind → decision → principal approval → anchored audit → observed outcome → simulated-labelled report as one governed workflow.

The repository provides several separate CLI commands and Python APIs. Some stages are only partially governed, some use legacy caller-supplied role strings, and the local audit-anchor implementation is still an open draft PR (#63), not part of main. The scenario-input package is not connected to the simulation engine.

This guide documents the available components and their boundaries. It does not authorise a simulation, calibration, backtest, forecast, study mutation, live pilot, production decision, real data, credentials, network access or external write-back. Do not use Nutrivance, NCC Park Square, customer records or any real personal/sensitive data. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Capability status at this assessment base

| Pipeline stage | Status on merged main | What is actually available |
|---|---|---|
| Synthetic CSV import | **AVAILABLE — CLI** | `agora data import-csv`, snapshot listing/show/rejected-row commands; immutable local snapshot and manifest. |
| Ontology binding | **AVAILABLE — Python API, partial governance** | `load_binding`, `validate_binding`, `materialize_instances`; policy callback still uses the legacy role-string enforcement contract. |
| Scenario-input package | **AVAILABLE — Python API, disconnected** | `build_scenario_input` builds a provenance-rich package from an exact import ID. It is not consumed by `agora/sim/engine.py`. |
| Decision record and proposal | **AVAILABLE — Python API** | Decision schema/store and lifecycle APIs. |
| Principal-based approval | **AVAILABLE — limited synthetic slice** | `Principal`, test-only `SyntheticFixtureAdapter`, `decide_principal` and `approve_as()` (#58). This is not production identity; legacy role-string approval remains underneath the bridge and other call sites are not migrated. |
| Anchored audit chain | **NOT AVAILABLE ON MAIN** | #52 is a specification. Implementation PR #63 remains open/draft; it is not merged and not wired into decision, outcome or policy call sites. |
| Observed outcome recording/review | **AVAILABLE — Python API, partial governance** | `DecisionOutcomeStore`, `record_outcome()`, `review_outcome()` (#53). Current APIs still accept caller-supplied role/subject values; no CLI. Simulated data is rejected as observed evidence. |
| Outcome dependency review markers | **NOT AVAILABLE** | #60 is a specification only; no marker store or propagation worker. |
| Decision/audit reconciliation | **NOT AVAILABLE** | #57 is a specification only; no queue, detector, worker or repair command. |
| Simulated-labelled report | **AVAILABLE — separate exploratory/mock path** | Existing standalone engine/report CLI path can produce exploratory/mock reports. It is not connected to the scenario-input package or the decision/outcome workflow. |
| One callable end-to-end entry point | **NOT AVAILABLE** | No command or API orchestrates all stages with the required principal and anchored-audit guarantees. |

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

The API checks the exact current version, fingerprint, scope, evidence references, review date and separation of duties. However, `approve_as()` currently derives the role and delegates to the legacy role-string `approve()` path. The remaining PDP, policy-enforcement and outcome call sites are not migrated. `SyntheticFixtureAdapter` is not production authentication; do not use real credentials or OIDC.

## 8. Step E — audit evidence

**Status: NOT AVAILABLE — anchored audit**

Main contains `AuditChainStore` from #38/#47: a local append-only, redacted hash chain with `append()`, `verify()` and `close()`. It is **not independently anchored** and cannot detect a removed tail if the remaining chain is internally consistent.

The local sidecar anchor implementation is proposed in #63, but live GitHub state at this assessment shows #63 open/draft/unmerged. Even if that implementation later merges, the wiring plan (#64) is documentation only and the wrapper still needs the lock, permission/atomic-write and close-lifecycle gaps resolved before wiring is treated as complete.

Do not describe the current pipeline as anchored, externally anchored, or fully tamper-resistant. Do not substitute a plain hash-chain verification for anchor verification.

## 9. Step F — record and review an observed outcome

**Status: AVAILABLE — Python API; principal migration pending**

The #53 implementation provides `DecisionOutcomeStore`, `record_outcome()` and `review_outcome()` in `agora.decisions.outcomes`. It requires an approved decision version, an exact declared measure, a measurement window, an exact source reference with a content hash, and `provenance_class="observed"`. The reviewer must differ from the recorder; corrections append a new record.

There is no CLI. The current API still accepts caller-supplied role and subject inputs; principal-based outcome recording/review is not implemented. A synthetic fixture may demonstrate schema and denial behaviour only, but **simulated preferences, agent actions, conversions and reports must never be entered as observed outcomes**. Use a genuinely observed source only in a separately authorised real-world workflow, which is outside this guide.

Outcome dependency review markers are not implemented. Reconciliation between decision and audit stores is not implemented.

## 10. Step G — generate a separate simulated-labelled report

**Status: AVAILABLE — separate exploratory/mock path**

The existing engine/report path is separate from Steps A–F. A standalone mock smoke test can use:

```bash
agora new ./engine-smoke --from demo
agora check ./engine-smoke --mock
agora run ./engine-smoke --mock
agora status ./engine-smoke
agora report ./engine-smoke --mock
```

Inspect the demo template first and replace it only with a small approved synthetic scenario appropriate to the rehearsal. Preserve run ID, scenario hash, backend/mode and report provenance. The report is exploratory/simulated output only. It does not consume the Step C package and does not validate demand, sales, causal effects or predictions.

## 11. What is required before this becomes one callable pipeline

The following are **not** delivered by this guide:

1. A single CLI/API orchestrator with exact immutable IDs passed between stages.
2. Principal-first policy enforcement at import, binding, decision, outcomes and review call sites; removal of caller-controlled role authority.
3. A reviewed and merged audit-anchor implementation, followed by wiring at decision, outcome and policy-denial append boundaries with serialized writes, safe lifecycle/close, permissions, atomicity and fail-closed recovery.
4. Reconciliation implementation or an owner-approved and tested manual recovery procedure for decision/audit cross-store gaps.
5. Outcome dependency markers or an owner-approved and tested manual hold/review procedure.
6. Scenario-input-to-engine integration, including new-run and resume paths; this remains separately blocked by the simulation-wiring approval gate.
7. End-to-end synthetic integration tests and exact-head CI for the orchestrator, followed by an independently reviewed and separately approved synthetic rehearsal.

Until those items are evidenced, run only the individual components within their documented limits; do not call them an end-to-end governed pipeline.

## 12. Evidence and stop conditions

Record the Git SHA, operator, fixture IDs, schema/import hashes, binding fingerprint, scenario-input hash, decision ID/version/fingerprint, synthetic actor labels, audit verification result, report run ID/mode and all stable denial/stop codes. Keep raw rows and sensitive values out of logs.

Stop immediately if real/personal/sensitive data, credentials, network access, external write-back, an unapproved simulation, a policy bypass, a non-exact identifier, an unaudited approval, or an output without simulated/exploratory labelling is encountered.

Passing a component-level demonstration means only that the documented local synthetic component ran. It does not establish that the complete pipeline exists or is ready for a pilot.

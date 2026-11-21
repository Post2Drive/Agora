# Callable Synthetic Governed Pipeline — Current-State How-To

**Status:** Capability map and operator guide; this is not an integrated end-to-end pipeline  
**Assessment base:** `main` at `7afa1414acd9c2e68361faab81a5d246597a5919` (22 November 2026)  
**Scope:** Local synthetic data and local stores only; merged mainline capabilities only

## 1. Read this before running anything

There is **no single CLI/API entry point** on this mainline that executes import → bind → decision → principal approval → anchored audit → observed outcome → simulated-labelled report as one governed workflow.

The repository provides separate CLI commands and Python APIs. #71/#74 wire the anchored writer through data-boundary, lifecycle and outcome append paths, but writer requirements remain opt-in. #78 adds a Principal-bound policy callback and #79 threads opt-in `require_policy` through import, binding and scenario-input APIs; defaults remain `False`. #80 makes `approve_as()` principal-native and #84 derives its policy resource only from the stored decision, ignoring caller-supplied resource data. #82 makes legacy role-string `approve()` fail closed by default behind an environment-variable switch; #70 outcome wrappers still bridge to legacy role-string functions. The scenario-input package remains disconnected from the simulation engine.

This guide documents the available components and their boundaries. It does not authorise a simulation, calibration, backtest, forecast, study mutation, live pilot, production decision, real data, credentials, network access or external write-back. Do not use Nutrivance, NCC Park Square, customer records or any real personal/sensitive data. Keep `VALIDATED_PREDICTION_ENABLED=False`.

## 2. Capability status at this assessment base

| Pipeline stage | Status on merged main | What is actually available |
|---|---|---|
| Synthetic CSV import | **AVAILABLE — CLI** | `agora data import-csv`, snapshot listing/show/rejected-row commands; immutable local snapshot and manifest. |
| Ontology binding | **AVAILABLE — Python API, partial governance** | `load_binding`, `validate_binding`, `materialize_instances`; #78 can bind a Principal with `principal_policy()`, and #79 adds opt-in `require_policy=True`. The default remains `False`; `policy=None` remains a no-op unless the caller opts in. |
| Shared policy enforcement | **AVAILABLE — partial** | #78 adds `principal_policy()` and `require_policy=True`; #79 threads the flag through import, binding and scenario-input. `require_policy=False` remains default; the callback is still `(operation, resource)`, and `audit=None` falls back to an unanchored local chain. |
| Scenario-input package | **AVAILABLE — Python API, disconnected** | `build_scenario_input` builds a provenance-rich package from an exact import ID. It is not consumed by `agora/sim/engine.py`. |
| Decision record and proposal | **AVAILABLE — Python API** | Decision schema/store and lifecycle APIs. |
| Principal-based approval | **AVAILABLE — partial synthetic migration** | #80 makes `approve_as()` call `authorize_decision_approval_principal()` and derive actor from Principal. #82 gates legacy `approve(... actor, role, subject, ...)` behind `AGORA_TEST_ONLY_LEGACY_APPROVE=1`; keep that switch test-only and migrate remaining callers. `SyntheticFixtureAdapter` is test-only, not production identity. |
| Anchored audit chain | **AVAILABLE — local-sidecar API; partially wired** | #63/#71/#74 provide the writer, factory and append wiring. `approve_as()`, `record_outcome_as()` and `review_outcome_as()` can opt into `require_anchored=True`, but the default is `False`; legacy lifecycle paths still accept optional audit. Trust is `local_sidecar`, not external anchoring. |
| Observed outcome recording/review | **AVAILABLE — Python API, partial principal migration** | #53 supplies append-only outcomes/reviews; #70 wrappers require operator/reviewer from Principal but still delegate to legacy role-string functions. #74 adds opt-in anchor gates. Audit remains optional; no CLI. Simulated data is rejected as observed evidence. |
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

The API checks the exact current version, fingerprint, scope, evidence references, review date and separation of duties. #80 makes `approve_as()` call `authorize_decision_approval_principal()` directly and derive the actor from `principal.subject_id`; #84 ignores caller-supplied policy resource data and fixes the server-side baseline sensitivity to `internal`. #82 makes the legacy role-string `approve()` API fail closed by default, but the environment switch is not structurally restricted to tests. Shared policy enforcement and outcome writes are not fully migrated. `SyntheticFixtureAdapter` is not production authentication; do not use real credentials or OIDC.

## 8. Step E — audit evidence

**Status: AVAILABLE — local-sidecar API; partially wired, with opt-in gates**

Main contains the local append-only hash chain from #38/#47 and the merged local-sidecar implementation from #63. #74 wires lifecycle/outcome appends and #75 introduces the structural `AuditAppender` protocol. The API includes `AnchorStore`, `AnchoredAuditChain`, `bootstrap_anchor()`, and `verify_anchored()`. `AnchoredAuditChain.append()` serializes the verify → chain append → anchor advance sequence with a cross-process sidecar lock and fails closed when the existing chain/anchor state is not cleanly verified. If the chain append succeeds but anchor persistence fails, `AnchorWriteError` reports a partial failure; do not retry the protected business operation or describe it as fully audited.

The anchor is a separate local JSONL sidecar with owner-only creation permissions and fsync on append. Its reported trust level is `local_sidecar`: it detects chain truncation/rollback only while the anchor survives independently. It does not protect against an attacker who can rewrite both local files, and it is not an external or independently hosted anchor. PR #63's exact-head Actions run 44917009154 passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. The Linux 3-process mutation test did not detect removal of the lock, so that particular lock-coverage proof remains a stated limitation.

**Integration status after #84:** policy-denial/import/binding/scenario-input paths accept an optional anchored writer; #79 adds opt-in `require_policy`, default `False`. Decision lifecycle and outcome/review append boundaries are wired by #74. `approve_as()`, `record_outcome_as()` and `review_outcome_as()` can set `require_anchored=True`, but the default remains `False`; legacy outcome paths and `audit=None` remain possible. #84 adds precise anchor-error coverage for `approve_as()` but does not change its opt-in default. #82's legacy approval gate is default-deny but still environment-enableable. Do not claim all approvals/outcomes are anchored. Trust remains local-sidecar; this is not external anchoring or protection against coordinated rollback.

## 9. Step F — record and review an observed outcome

**Status: AVAILABLE — Python API; principal migration partial**

The #53 implementation provides `DecisionOutcomeStore`, `record_outcome()` and `review_outcome()` in `agora.decisions.outcomes`. It requires an approved decision version, an exact declared measure, a measurement window, an exact source reference with a content hash, and `provenance_class="observed"`. The reviewer must differ from the recorder; corrections append a new record.

There is no CLI. PR #70 adds `record_outcome_as()` and `review_outcome_as()` wrappers that derive recorder/reviewer and role from Principal and require `operator` / `reviewer`. They reject caller-supplied recorder/reviewer, role and subject fields, then delegate to legacy role-string functions. #74 wires the append boundaries and adds opt-in `require_anchored=True` gates, but the audit parameter remains optional by default. A synthetic fixture may demonstrate schema and denial behaviour only, but **simulated preferences, agent actions, conversions and reports must never be entered as observed outcomes**. Use a genuinely observed source only in a separately authorised real-world workflow, which is outside this guide.

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

## 11. What is required before this becomes one callable pipeline

The following are **not** delivered by this guide:

1. A single local CLI/API orchestrator with exact immutable IDs passed between stages and clear per-step results/deny stops.
2. Keep the #82 legacy `approve()` switch test-only and retire the compatibility API after test migration; migrate the outcome store boundary to Principal rather than wrappers around legacy role-string functions.
3. Make protected policy checks default-on: `require_policy=False` is still the default on import, binding and scenario-input; the shared callback does not accept a Principal directly.
4. Require one configured anchored writer on every protected path by default: `require_anchored=False` and optional `audit=None` paths remain; `local_sidecar` is not an independent external anchor.
5. Reconciliation implementation or an owner-approved and tested manual recovery procedure for decision/audit cross-store gaps. PR #57 remains a specification only.
6. Outcome dependency markers or an owner-approved and tested manual hold/review procedure. PR #60 remains a specification only.
7. A checked-in synthetic dataset, one-command install/start, operator runbook commands executed by tests, backup/restore and tamper drills, held-outcome listing, readable audit timeline/verification, and a logged dress rehearsal.
8. Scenario-input-to-engine integration remains separately blocked; this guide does not authorise changes to `agora/sim/**` or any simulation run.
9. End-to-end synthetic integration tests and exact-head CI for the orchestrator, followed by the owner-approved synthetic rehearsal required by the milestone process.

Until those items are evidenced, run only the individual components within their documented limits; do not call them an end-to-end governed pipeline. The previous `approve_as()` caller-resource downgrade finding is closed by #84. #86 is merged (main `a0777c1`): it removes caller-supplied policy resource data from the outcome `_as` wrappers, but the wrappers still delegate to public role-string outcome functions and `require_anchored` remains opt-in. Claude's next slice is the local synthetic `agora/pilot.py` entry point.

## 12. Future synthetic end-to-end command — NOT IMPLEMENTED

**This is a proposed interface sketch only. No such command exists on main; do not execute it or treat it as an operator instruction.**

```bash
# PROPOSED ONLY — not implemented
agora governed-pipeline run --project ./tmp-governed-pilot --fixture-set ./fixtures/governed-synthetic
```

A future implementation must orchestrate exact immutable import IDs, ontology binding, scenario-input construction, decision creation, principal approval, anchored audit, observed-only outcome/review and a separately simulated-labelled report. It must stop on missing policy, Principal, scope, anchor, provenance, exact ID or reviewer separation. It must not start a simulation or call `agora/sim/**` until Claude's written approval and separate owner approval are recorded. This guide does not authorise such implementation or rehearsal.

## 13. Evidence and stop conditions

Record the Git SHA, operator, fixture IDs, schema/import hashes, binding fingerprint, scenario-input hash, decision ID/version/fingerprint, synthetic actor labels, audit verification result, report run ID/mode and all stable denial/stop codes. Keep raw rows and sensitive values out of logs.

Stop immediately if real/personal/sensitive data, credentials, network access, external write-back, an unapproved simulation, a policy bypass, a non-exact identifier, an unaudited approval, or an output without simulated/exploratory labelling is encountered.

Passing a component-level demonstration means only that the documented local synthetic component ran. It does not establish that the complete pipeline exists or is ready for a pilot.

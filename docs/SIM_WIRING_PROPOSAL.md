# Scenario-Input Wiring into the Simulation Engine — Proposal (Block 22)

**Status: proposal only.** This document does not change `agora/sim/**`, run a simulation, mutate a study, or authorise implementation. Any edit to `agora/sim/**` requires Claude's written approval and a separate explicit owner-approved execution step.

## 1. Goal and non-goals

Connect the existing read-only scenario-input adapter and append-only run-provenance store to the simulation lifecycle so that a run is bound to one exact input snapshot.

The intended guarantees are:

- a new opted-in run prepares scenario input from an explicit immutable `import_id`;
- the exact input manifest is persisted before population state is written or round 1 can begin;
- resume recomputes the input and checks the exact input `scenario_hash` before loading the prior world;
- a missing or changed input fails closed rather than resolving `latest` or silently substituting another snapshot;
- legacy projects and existing studies are not silently migrated or rewritten; and
- outputs remain exploratory and visibly simulated.

This proposal does not change agent behaviour, treatment assignments, event schedules, model prompts, run-round logic, calibration, backtests, forecasts, or report claims. It does not enable validated prediction or external write-back.

## 2. Current code boundary (main at 6a8208f8)

- `Simulation.__init__` in `agora/sim/engine.py` loads the scenario and opens the run `Store`; it does not currently build scenario inputs.
- `Simulation.prepare()` is the lifecycle boundary. For a new project it builds a population and calls `self.store.write_population(...)`; it then records the engine's existing scenario hash and seed. For an existing project it checks the engine scenario hash and then calls `World.load(self.store)`.
- `agora/scenario_inputs.py::build_scenario_input(binding, pack, project, import_id, *, scenario_parameters=None, transformation_policy=None, policy=None)` builds a deterministic package from one explicit snapshot and returns a manifest, input `scenario_hash`, and `validated_prediction_enabled=False`.
- `agora/store/db.py::Store.set_input_provenance(manifest, *, scenario_hash=None)` stores an append-once envelope; `Store.assert_resume_input(scenario_hash)` rejects legacy-missing provenance and mismatched input hashes.
- `agora/report/writer.py` reads and verifies provenance for report exports. Its validated-prediction gate remains before provenance access and `VALIDATED_PREDICTION_ENABLED` remains `False`.

The engine's existing `scenario_hash` is a hash of `scenario.yaml`. The scenario-input adapter's `scenario_hash` is a separate hash of the selected snapshot, binding, ontology, transformation policy and declared parameters. Do not overwrite or conflate these two values.

## 3. Proposed opt-in configuration contract

Add a versioned, optional top-level `scenario_input` section to a scenario configuration. This is a proposed schema, not an implemented field:

```yaml
scenario_input:
  contract_version: 1
  import_id: "<exact-committed-import-id>"
  binding_path: "inputs/customer.binding.yaml"
  ontology_pack_path: "inputs/customer.pack.yaml"
  scenario_parameters:
    cohort: "synthetic-pilot-a"
  transformation_policy:
    policy_id: "synthetic-transform-v1"
    purpose: "declared scenario construction"
    retention: "one day"
    reviewer: "named-reviewer"
    approved_at: "RFC3339 timestamp"
    audit_reference: "opaque-audit-reference"
    authorized_property_ids: []
```

Rules:

1. `import_id` is mandatory, exact and immutable. Reject empty values and `latest`.
2. Paths are project-relative, resolved beneath the project root, and must not escape it.
3. The binding and ontology pack must pass their existing schema, version, fingerprint, type and sensitivity checks.
4. `scenario_parameters` must be canonicalisable JSON and become part of the scenario-input hash.
5. Personal/sensitive data remains redacted unless the explicit transformation policy authorises the exact properties. The policy's purpose, retention, reviewer, approval timestamp and audit reference remain in the manifest.
6. The policy callable must use the central PDP and fail closed. A caller-supplied role is not trusted identity. The known purpose/retention propagation gap at the binding hook must be resolved or explicitly wrapped and tested before this feature can be considered secure.
7. If the optional section is absent, preserve the current legacy simulation path exactly; do not infer an input from a nearby file or a most-recent import.

## 4. Required lifecycle ordering

### New opted-in run

The proposed order inside `Simulation.prepare()` is:

1. Confirm the run store is not initialised.
2. Parse and validate the optional `scenario_input` contract.
3. Resolve the exact binding and ontology pack paths under the project root.
4. Call `build_scenario_input(..., import_id=<exact id>, ...)` using the project's explicit policy adapter.
5. Validate that the returned package identifies the requested `import_id`, has a non-empty scenario-input hash, and has `validated_prediction_enabled is False`.
6. Call `self.store.set_input_provenance(package["manifest"], scenario_hash=package["scenario_hash"])`.
7. Only after provenance persistence succeeds, build the population and call `self.store.write_population(...)`.
8. Preserve the existing engine `scenario_hash` and seed metadata as separate run metadata.
9. Continue into the existing round loop unchanged.

If any step through 6 fails, no population rows or round records may be written. A partially created project directory may remain, but it must not appear to be an initialised simulation.

### Resume of an opted-in run

1. Recompute the current scenario-input package from the exact configured import, binding, ontology pack, parameters and transformation policy.
2. Call `self.store.assert_resume_input(package["scenario_hash"])`.
3. Separately perform the existing engine scenario-hash check.
4. Only after both checks succeed call `World.load(self.store)`.
5. If the provenance is missing (`legacy_missing`) or the input hash differs, stop with a safe diagnostic. Do not repair, backfill, overwrite or infer provenance.

The call to `assert_resume_input` must be before `World.load` and before any round work.

### Legacy and non-opted-in projects

- Existing runs without `scenario_input` retain their current behaviour and remain labelled `legacy_missing` when inspected by the provenance reader.
- A project explicitly configured for scenario-input mode must not resume as though it had a valid scenario-input envelope if the envelope is absent.
- No migration writes provenance into an old run. Start a new project to opt into this path.
- Do not edit or rerun NCC Park Square, E0_C0_D0, any factorial run, or any existing study folder as part of this work.

## 5. Proposed implementation surface

No files are changed by this proposal. A later implementation should be narrowly scoped:

- `agora/sim/engine.py`: add one private preparation helper or a small adapter call in `Simulation.prepare()`; persist the manifest before `write_population`; verify resume input before `World.load`.
- `agora/scenario.py` (or the existing scenario configuration validation module): validate the optional versioned `scenario_input` section and reject unknown/malformed fields.
- `agora/store/db.py`: reuse `set_input_provenance` and `assert_resume_input`; do not weaken append-only semantics or replace the existing engine scenario hash.
- Tests: add a focused simulation-prepare integration test module using temporary project directories, synthetic CSV fixtures, mock LLM backend and no real run rounds.

Avoid changing `agora/sim/world.py`, population generation, round execution, event handlers, or existing study artifacts unless a separately reviewed requirement proves it necessary.

## 6. Failure modes and required diagnostics

| Condition | Required behaviour |
|---|---|
| Missing or `latest` import ID | Fail before snapshot read; safe explicit-ID diagnostic |
| Binding/ontology pack missing, invalid or version-drifted | Fail before population write; identify contract field, not raw data |
| Policy denies or cannot decide | Fail closed and record the allow-listed denial through the existing policy boundary |
| Personal/sensitive value lacks purpose/retention or explicit transformation permission | Fail closed; do not expose raw values in errors or logs |
| Scenario-input hash changes on resume | `assert_resume_input` fails before `World.load` |
| Existing opted-in run has no provenance | Fail closed as legacy; no automatic migration |
| Provenance write fails | Do not write population or begin round 1 |
| No `scenario_input` section | Preserve current non-opted-in behaviour; do not infer a snapshot |

## 7. Acceptance tests

1. Opted-in new run writes the exact manifest and scenario-input hash before `write_population`.
2. A spy around `write_population` proves the provenance row already exists when population persistence begins.
3. The run store's engine scenario hash remains distinct from the input scenario hash.
4. Resume with the same import, binding, ontology and policy reaches `World.load` only after `assert_resume_input` succeeds.
5. Changed import ID, snapshot manifest, binding fingerprint, ontology fingerprint, policy or scenario parameters fails before `World.load`.
6. Legacy opted-in run with no provenance fails closed and remains unmodified.
7. A non-opted-in project follows the pre-existing path with no new database writes or changed outputs.
8. Policy denial is audited with allow-listed metadata and no raw values.
9. The manifest and diagnostics contain no raw personal/sensitive values.
10. `VALIDATED_PREDICTION_ENABLED` remains `False`; no simulation rounds are run by the tests.

## 8. Scratch mutation proofs (never committed)

- Move `set_input_provenance` after `write_population`: the ordering test must fail.
- Remove `assert_resume_input` or move it after `World.load`: the resume-order test must fail.
- Replace the explicit import ID with `latest`: the explicit-ID rejection test must fail.
- Omit the input scenario hash from the provenance call: the exact-hash/resume test must fail.
- Backfill a legacy run: the legacy immutability test must fail.
- Bypass the policy hook: the deny-before-read/audit test must fail.

## 9. Rollout gates

1. Claude provides written approval of this proposal before any edit to `agora/sim/**`.
2. The owner explicitly approves the implementation scope after seeing that approval.
3. Implementation is a separate draft PR with no study-folder or scenario changes.
4. Synthetic tests and mutation proofs run in a clean checkout; all four CI matrix jobs pass on the exact head.
5. Existing studies remain untouched; no simulation, calibration, backtest, forecast or real-data run is used as a test.
6. Owner explicitly says `review` before any review/merge decision.

**No implementation is authorised by this proposal.**

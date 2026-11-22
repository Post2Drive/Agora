# M3 Proposal — Governed Scenario Inputs to the Simulation Engine

**Status:** Proposal only. No M3 implementation, simulation, calibration, backtest, forecast or engine run is authorised by this document. M2 is still in progress in Claude's 12:58 IST brief. This proposal does not declare M2 or M3 reached.

**Draft baseline:** main `85c0ecad8106fe1b24f1d4a5daf6fe33aa236ea8` (22 November 2026), including #135's workdir-ancestor symlink refusal and linked-fixture catalogue filtering. PR #136 is merged at head `b5d7b045d89a354fdef758feaa49adc23e8fa703`; exact-head CI `45006493190` passed 4/4; its exact-head CI `45006493190` passed 4/4 and a `..`-through-symlink normalization regression remains. Source-pair snapshot locking/head equality and other M2 gates remain open. M2 remains in progress; clean-install proof remains open.

## 1. Purpose and boundary

M3 should connect an explicitly selected, policy-governed, immutable tabular snapshot to a simulation run without weakening policy, principal, audit, anchor, provenance, resume or output-label boundaries.

The intended proof is narrow:

1. A run identifies one exact approved tabular import and its canonical input manifest.
2. Policy and anchor checks occur before the protected snapshot is read.
3. A deterministic, schema-bound projection transforms the approved snapshot into a documented simulation input.
4. The engine consumes that projection; it does not silently read a `latest` snapshot or unrelated files.
5. The run and every report retain exact input, scenario, schema, binding, ontology and policy provenance.
6. Resume refuses a changed or missing input envelope and does not rewrite original provenance.
7. Outputs remain visibly exploratory simulations, not observed outcomes or validated predictions.

M3 is not a production identity, connector, external action, prediction-approval or deployment milestone. P2D remains pre-launch with no real operational data. Its separate rate-card exercise is an owner-entered governed decision, not an outcome-validation exercise.

## 2. Live-main facts used by this proposal

The following are code/document observations at main `85c0ecad8106fe1b24f1d4a5daf6fe33aa236ea8`, including merged #135 workdir-ancestor/fixture-catalogue hardening and open, unmerged PR #136 backup path hardening; they are not claims that M3 behavior exists:

- `agora/cli.py` keeps the simulation import lazy through `_simulation()`. The `run` command constructs `Simulation`, calls `prepare()`, then `run()`. The `pilot` and data-command dispatch paths are separate and must remain engine-import-free.
- `agora/sim/engine.py` currently loads `scenario.yaml`, opens the run `Store`, and calculates `scenario_hash` from scenario configuration. On a first run, `prepare()` calls `population.build(self.sc)`; on resume it compares the stored scenario hash before loading `World`. It does not currently require a governed tabular input envelope.
- `agora/tabular.py` provides local CSV ingestion as an immutable typed snapshot. `ingest_csv()` requires an explicit data role and policy enforcement; `read_snapshot(project, import_id)` reads one exact import ID.
- `agora/ontology/binding.py` provides validated bindings and `materialize_instances(..., import_id)`; its protected path requires policy and runs policy enforcement before opening the snapshot database.
- `docs/RUN_PROVENANCE_SPEC.md` defines an append-once `input_provenance` envelope containing exact `scenario_hash`, `import_id`, canonical input manifest/hash, binding fingerprint, ontology fingerprint, transformation-policy fingerprint, data role and creation time. It requires resume and report checks against that envelope.
- `agora/pilot.py` is explicitly a local synthetic governance pilot; its structural `engine_invoked` and `validated_prediction_enabled` values are false. It is not the M3 engine adapter.

These existing boundaries must be preserved. A design document alone is not implementation evidence.

## 3. Proposed integration sequence

### Stage 0 — preflight and explicit input selection

Require an explicit project, dataset/schema/binding versions, exact `import_id`, data role, transformation policy and scenario configuration. Require `data_role=scenario_input` for fields that affect the simulated world. Resolve the import manifest and file hash from the local immutable snapshot registry. Never select `latest`. Reject unknown imports, changed bytes, unsupported schemas, unbound columns, unknown fields, invalid ontology properties and prohibited sensitivity classes. No personal or sensitive fields are in the proposed validation datasets. Complete policy/principal/anchor evaluation and anchored denial handling before reading snapshot bytes.

**What this proves:** the engine receives an explicit, authorized, reproducible source reference rather than an ambient file or mutable database view.

### Stage 1 — canonical scenario-input envelope

Construct a versioned immutable envelope using `RUN_PROVENANCE_SPEC.md`:

- exact import ID, dataset ID/version and source file SHA-256;
- schema ID/version/fingerprint;
- binding ID/version/fingerprint;
- ontology pack ID/version/fingerprint;
- transformation-policy fingerprint and redaction summary;
- data role, approved field allow-list and record count;
- canonical input manifest and its SHA-256;
- scenario hash and UTC creation time;
- repository SHA and run ID.

The manifest contains identifiers, hashes and safe metadata only. It must not duplicate raw row values, personal fields, credentials, free text or source payloads.

**What this proves:** the same source and transformation contract can be identified independently of a later report or engine result.

### Stage 2 — deterministic projection to engine input

Define a small, versioned adapter from bound ontology instances to the exact fields consumed by the simulation scenario/population. It must map only allow-listed properties; reject unknown or unmapped columns; use stable ordering and deterministic transformations; use stable opaque IDs or deterministic pseudonyms; enforce row limits, value bounds, null rules and categorical vocabularies; record aggregation, sampling, filtering and transformations; separate observed source values from generated agent attributes and assumptions; avoid injecting raw source text into prompts/personas; and produce the same projection hash from the same input/configuration.

No adapter may infer population weights, segment shares, agent beliefs, behavior rates or causal effects without an explicit documented mapping and owner-reviewed assumption register.

**What this proves:** the transformation from governed data to simulation parameters is explicit, testable and reproducible.

### Stage 3 — engine preflight and first-run persistence

Before population creation or the first simulation round:

1. Verify the envelope against the exact immutable snapshot and canonical manifest.
2. Verify scenario hash, adapter version and every transformation fingerprint.
3. Persist the append-once provenance envelope with run metadata before any round is committed.
4. Construct the initial world from the deterministic projection, not directly from source CSV or arbitrary database rows.
5. Fail closed if provenance persistence fails; do not create a partially initialized run that appears valid.

**What this proves:** the run cannot start without a durable record of the exact inputs that shaped it.

### Stage 4 — resume, report and export integrity

Resume only if the stored envelope is present, valid and identical to the exact import, manifest, schema, binding, ontology, policy and scenario values requested. A changed import, source bytes, mapping, policy or scenario requires a new run ID. `--force` must not overwrite or bypass the input envelope. Legacy runs without `input_provenance` remain inspectable as legacy but cannot resume through the governed-input path. Reports/exports carry run ID, input manifest hash, scenario hash, exact import ID, schema/binding/ontology/policy fingerprints, data role, repository SHA and an explicit exploratory/simulated label. Missing or inconsistent provenance blocks report/export for the governed-input run.

**What this proves:** the source-to-output trace survives restart and cannot be silently changed after the run.

### Stage 5 — labelled output and independent comparison

Every M3 report is labelled **EXPLORATORY SIMULATION — simulated outputs, not validated real-world predictions**. Simulated preferences, actions, conversions and metrics must not be described as observed sales, demand, adoption, election outcomes or causal effects. A validation comparison may be calculated only under the separately committed `VALIDATION_PROTOCOL.md`, using the exact approved public datasets and run scope. Keep `VALIDATED_PREDICTION_ENABLED=False`. A validation metric does not enable validated-prediction reporting.

**What this proves:** output semantics and validation claims remain bounded by the evidence actually collected.

## 4. Exact proposed `agora/sim/**` edit scope — not approved

The following is the complete proposed simulation-tree scope for owner review. It is not permission to edit these files. No other `agora/sim/**` path is included.

| Proposed file | Proposed responsibility | Why it may need an edit |
|---|---|---|
| `agora/sim/engine.py` | Accept and verify governed input envelope before `prepare()` creates a population or `World.load()` resumes one; bind envelope to run; verify before every resume. | Observed engine lifecycle boundary: first-run population creation and resume checks currently occur here. |
| `agora/sim/population.py` | Add deterministic typed projection from validated ontology instances to scenario population/segment inputs, retaining current scenario-only path for legacy runs. | Current engine calls `population.build(self.sc)`; adapter belongs where governed projection becomes population. |
| `agora/sim/world.py` | Only if approved projection requires a minimal explicit world-construction field not supported by current `Agent`/world model; preserve stable identity and deterministic load behavior. | Conditional scope, not a presumed requirement. Claude should remove this path if existing world contract is sufficient. |

**No other simulation-tree edits are proposed.** If implementation discovery shows a fourth `agora/sim/**` file is necessary, Claude must revise the design and obtain new owner approval naming that path before editing.

## 5. Proposed non-simulation integration scope

These paths are outside `agora/sim/**`, but code changes remain Claude-owned and require their own implementation PR:

- `agora/cli.py`: expose explicit governed-input selection for the run command; preserve lazy engine import and keep pilot/data dispatch engine-free.
- `agora/tabular.py` and `agora/ontology/binding.py`: reuse existing immutable snapshot, exact import-ID, binding and policy boundaries; add behavior only if reviewed contract requires it.
- A new narrowly scoped provenance/adapter module may be preferable to embedding manifest logic in CLI or engine. Claude must fix its path/API before coding.
- `agora/report/render.py` and report provenance construction: carry and validate the envelope, retaining exploratory labels and hard-disabled validated-prediction gate.
- Tests are Claude-owned; this proposal makes no test edits.

This is a planning inventory, not a code change request to ChatGPT.

## 6. Required acceptance gates

M3 is not acceptable unless exact merged-head evidence demonstrates:

1. Policy denial occurs before source bytes/snapshot rows are read.
2. Only an exact immutable `import_id` is accepted; `latest`, implicit discovery and path substitution are rejected.
3. Dataset, schema, binding, ontology, policy and transformation fingerprints are validated and persisted.
4. Projection is deterministic, schema-bound, bounded and free of prohibited personal/sensitive fields.
5. Run provenance is written before the first simulation round and is failure-atomic.
6. Resume with identical inputs succeeds; changed import, bytes, manifest, schema, binding, ontology, policy or scenario fails without mutating original run.
7. Legacy runs are not silently upgraded to governed-input status.
8. Reports/exports include provenance trace and exploratory label.
9. Fresh process can verify trace without mutable `latest`.
10. Tests prove no real data, connectors, credentials, network access or external write-back.
11. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.
12. No unapproved simulation-tree path is changed.

## 7. Explicitly blocked items — each needs its own named owner approval

The owner approved in principle an M3 design and validation simulation runs only for the three named public benchmark packages, after M2, M3 and protocol commitment. That does not approve every adjacent action.

| Blocked item | Not authorised | Required future approval |
|---|---|---|
| Any `agora/sim/**` implementation | This document does not authorise code edits. | Written owner approval naming each exact file path and accepted design revision, after Claude supplies final design. |
| M3 simulation run on P2D inputs | No P2D database/export run, test-account or operational-data inference. | Separate named approval for exact P2D input and run scope. P2D remains pre-launch with no real data. |
| Real P2D export import | No live DB, read-only replica, Railway API, connector or credentials. | Owner approval naming export file, fields, purpose and handling. Approved future form is read-only export file only; personal fields excluded. |
| Any personal-data import | No customer/driver names, contact details, addresses, identifiers or other personal fields. | Separate consent/data-protection review and new owner approval naming exact fields and lawful basis. |
| Connector or live service access | No credentials, network access from AGORA or external service connection. | New owner approval naming connector, permissions, data scope and network boundary. |
| Write-back or external action | No updates to live systems, customer, driver, carrier or third-party records. | Separate named owner approval and independent action-safety design. |
| Change to `VALIDATED_PREDICTION_ENABLED` | It remains `False`. | Separate explicit owner approval naming requested flip and claims scope after validation review. |
| Other datasets or extra simulation runs | No extra dataset, substitute, expanded period or exploratory run beyond committed protocol. | New owner approval naming dataset and run scope. |

## 8. Sequence and governance

1. Claude completes M2 and records exact M2 confirmation in the collaboration log.
2. Claude finalizes M3 architecture and exact simulation-tree file list.
3. Owner gives written approval naming exact `agora/sim/**` edit scope.
4. Claude implements approved code slice in a draft PR; exact-head CI must pass all four matrix jobs and independent review must close.
5. Validation protocol is committed before any validation run/data-backed simulation.
6. Claude confirms M3 only in the collaboration log. Validation runs then proceed only within committed protocol and named approvals.

**No implementation, simulation, validation run, calibration, backtest, forecast, network access, credential use or write-back was performed to prepare this proposal.**

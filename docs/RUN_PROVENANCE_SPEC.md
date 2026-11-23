# Run Provenance for Scenario Inputs — Rung 4

> **Governance update — 23 November 2026, 22:40 IST:** Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1`; manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. The freeze authorizes no run, no data import and no flag change. Claude reports the 15 pinned source files match the manifest and 74 benchmark-metrics/engine governed-input tests pass on main. The target-output check remains partial because the exact base scenarios, mappings, run invocation and evaluator command are not yet written. A versioned v0.2 run specification is required; owner pre-approval is conditional and does not itself authorize a run. M3 remains unreached. Evaluator custody and staged label release are governed by `docs/EVALUATOR_CUSTODY.md`.

**Status:** Normative contract assessed against Agora main `3872f2401a8c6c6de097ad82a701414e8b1a26c9` (23 November 2026). Merged implementation, CI and residual security limitations remain as recorded below. Protocol v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1` with manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; owner confirmation was posted at 22:14 IST and Claude recorded the freeze at 22:16 IST. The freeze authorizes no run, no import and no flag change. Claude's 22:40 report records 15 pinned source files matching manifest bytes/hashes and 74 benchmark-metrics/engine governed-input tests passing. Exact base scenarios, input/output mappings, run invocation and evaluator command remain unspecified; v0.2 is required before a run. Evaluator custody is drafted in `docs/EVALUATOR_CUSTODY.md` and remains subject to owner review/merge. M3 remains unreached and `VALIDATED_PREDICTION_ENABLED=False`.

## 1. Purpose and boundary

Every new run that consumes a scenario input must retain the exact immutable
input manifest and `scenario_hash` used to construct it. A run is exploratory
unless a separately approved governance process says otherwise. Simulated
preferences, actions, and metrics must never be represented as observed sales,
validated demand, or validated prediction.

## 2. Storage location and shape

The run record is the authoritative provenance envelope. It is stored beside
the run's existing immutable metadata, in the run store's metadata namespace,
under a versioned `input_provenance` record:

```json
{
  "provenance_version": 1,
  "scenario_hash": "sha256:...",
  "import_id": "...",
  "input_manifest": {"...": "the canonical scenario-input manifest"},
  "manifest_hash": "sha256:...",
  "binding_fingerprint": "sha256:...",
  "ontology_pack_fingerprint": "sha256:...",
  "transformation_policy_fingerprint": "sha256:... or null",
  "data_role": "context or scenario_input",
  "created_at": "RFC3339 timestamp"
}
```

The engine calls its provenance guard from `Simulation.prepare()` before population creation. The stored envelope is append-once in the run store's `meta.input_provenance` key. Its outer shape is `provenance_version`, `scenario_hash`, `input_manifest`, and `manifest_hash`; `Store.get_input_provenance()` recomputes the manifest hash and checks that the outer and inner scenario hashes agree. The input manifest carries the projection record (`mapping_hash`, `instances_hash`, `projection_hash`, and declared assumptions) plus two distinct scenario hashes. `base_scenario_hash` is the 16-hex SHA-256 prefix of the original `scenario.yaml` content as loaded, before projection. `projected_scenario_hash` is the 16-hex SHA-256 prefix of canonical JSON binding that base hash to the projection's `projection_hash`, which covers the row, mapping and segment projection.

`manifest_hash` is the canonical hash of `input_manifest`; it is not a substitute for the source `scenario_hash`. The hash distinction is implemented in #178: `base_scenario_hash` is captured immediately after loading `scenario.yaml`, before projection; `projected_scenario_hash` binds that base hash to the projection record's `projection_hash`. The merged tests cover both values, prove that row and mapping changes leave the base hash stable while changing the projected hash, and prove that changed-input resume is refused without altering the original append-once envelope. Exact-head CI run `45113858688` passed all four Ubuntu/Windows × Python 3.11/3.12 jobs. Claude reports the local mutation proofs; ChatGPT did not run or independently reproduce them.

## 3. Immutability and consistency

- A committed run record's `input_provenance` is append-once. Updates create a
  new run record or an explicit superseding record; they never rewrite the
  original envelope.
- On read, the stored `manifest_hash` must match the canonical manifest and the
  manifest's `scenario_hash` must match the envelope. Any mismatch fails closed
  before report generation or resume.
- The run record must retain the exact `import_id`, never `latest`, plus dataset,
  schema, source registry, binding, ontology, policy, and file-hash fields from
  the scenario-input manifest.
- Provenance is metadata only. It must not copy raw personal or sensitive
  values beyond the already-authorized/redacted scenario-input payload.

## 4. Resume safety

For a governed run, `Simulation.prepare()` invokes `_guard_provenance()` before any population write. On an initial run it appends the envelope; on an initialized run it first requires a verified existing envelope and then attempts the same append-once write, which succeeds only for an identical envelope. The engine re-verifies the package and projection before this check. A changed import, manifest, mapping, instance rows, projected scenario or other manifest field therefore refuses resume without replacing the original envelope. `--force` is refused by the CLI for governed input and cannot bypass the engine guard. Legacy runs without a verified envelope cannot be upgraded through this path.

The existing engine rule that a changed scenario requires a new run remains in
force. `--force` must not overwrite or mutate the old provenance envelope; if a
future implementation supports a forced branch, it must create a new run ID
with a new provenance record and an explicit audit relation to the old run.
Runs without an input manifest are not silently upgraded: they are legacy runs
that may be inspected or reported as legacy, but they cannot be resumed as
scenario-input runs.

## 5. Report and export requirements

Every report or export derived from a scenario-input run must display or carry:

- run ID and exact `scenario_hash`;
- exact `import_id`, dataset/schema IDs and versions;
- binding ID/version/fingerprint and ontology pack/version fingerprint;
- transformation-policy fingerprint and redaction summary, when applicable;
- source data role and snapshot/file hash;
- `mode: exploratory` and a visible statement that results are simulated;
- whether the run is legacy (missing `input_provenance`) and therefore not
  eligible for scenario-input resume.

Reports must not use labels such as “forecast,” “validated demand,” or “sales
prediction” for exploratory output. A missing or inconsistent provenance
envelope is a report error, not a reason to infer the most recent snapshot.

## 6. Compatibility and migration

Existing runs created before this contract may retain their current metadata.
They are marked `provenance_status: legacy_missing` when read. Migration is
read-only unless the owner explicitly approves a new run record, and it cannot
invent a scenario hash or reconstruct an input manifest from `latest`.

## 7. Verification plan

Merged implementation evidence and remaining verification:

- #171 tests the governed engine path with synthetic packages and a mock backend, including append-once provenance, changed-input refusal, legacy-run refusal and `--force` resistance; the default ungoverned path remains separate.
- #172 tests exact import selection, missing input files, refusal of `latest`, refusal of `--force`, and the current no-identity-adapter policy denial; the denial leaves the run without provenance and without a population.
- #173 tests that changing even an unmapped row property changes `instances_hash` and `projection_hash`, while row reordering leaves the order-independent row hash unchanged.
- Exact-head Ubuntu/Windows × Python 3.11/3.12 CI passed 4/4 for #171, #172, #173 and #178 (hash split run `45113858688`).
- #198/#199 now implement a Principal-bound receipt and reject hand-built Principals that lack adapter-origin provenance. This is not a production trust boundary: the in-process `_ISSUED`/`_MINT` sentinels are reachable, `object.__setattr__` bypasses the receipt setter, and the synthetic adapter accepts caller-supplied fixture definitions. Keep the fixture adapter test-only; production identity remains absent and the CLI remains default-deny.
- #197 implements held-descriptor read-side snapshots for audit-chain, anchor and run-record/seal verification. `AuditChainStore` writer opens remain path-based; Python before 3.11 fails closed. Any writer-side race work must remain within the owner's explicit path approvals.
- Claude's reports state that the 12-file FiveThirtyEight sub-manifest on P2D PR #5 has matching source/committed-destination and Windows-checkout byte counts/SHA-256 values, and that the owner-approved MEDSL and Ember mirror files have been fetched/hash-verified in Claude's workspace. MEDSL: `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7`, `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0. Ember: `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0, 16-Nov snapshot. ChatGPT inspected GitHub metadata only, not raw CSV bytes. Neither mirror file is committed to P2D/Agora. Agora #203 contains the current 15-row hash-only manifest (SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) with E/A rows `PLANNED - NOT EXECUTED`. Package R/M5 is dropped. The selected poll window is 2000–2016; 2020/2024 are out of scope, and the uncorrected 2024 file is excluded. No raw data is staged in the owner-controlled private repository.
- The five owner-approved 23 November design values (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on) are now merged in `VALIDATION_PROTOCOL.md` by #202. Claude's 21:58 IST entry provides the replacement freeze sentence naming protocol commit `6d06088cf7954bd41f003544f5ec61675389bcc1` and manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; the owner posted it at 22:14 IST and Claude recorded protocol v0.1 frozen at 22:16 IST; the separate run go remains conditional on v0.2 freeze and all gates.
- Keep the owner's run approval dormant until the protocol is validly frozen, all data and implementation gates are satisfied, and Claude has recorded M3 reached. No run or flag change is authorized now.

The original verification objectives remain applicable:

1. the exact manifest and scenario hash are persisted before a run starts;
2. tampering with the manifest or hash is rejected;
3. resume with an unchanged input succeeds;
4. resume after snapshot, schema, binding, ontology, policy, or parameter change
   is rejected without mutating the original run;
5. old runs without a manifest are labelled legacy and cannot resume through
   this path;
6. reports contain the required provenance fields and exploratory labels;
7. no personal or sensitive raw value is copied into provenance metadata; and
8. validated-prediction mode remains disabled until separately approved.

No dataset validation, calibration, backtest, forecast, network call, credential use, or write-back is authorized by this specification. Keep all outputs labelled exploratory and simulated; keep `VALIDATED_PREDICTION_ENABLED=False`.

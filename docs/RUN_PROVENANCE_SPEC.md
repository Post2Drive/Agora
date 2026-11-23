# Run Provenance for Scenario Inputs — Rung 4

**Status:** Normative contract; M3 governed-input implementation slices 4.1–4.4 and 4.6 are merged on main `3e55e5505cda38a2ccfdc93a3e9996120ebb659e` (23 November 2026). #171 adds the opt-in `Simulation(..., governed_input=...)` engine path; #172 adds `agora run --governed-input` with exact import ID and fail-closed policy handling; #173 binds instance rows into `projection_hash` with an order-independent `instances_hash`; #178 separates the original `base_scenario_hash` from the projection-bound `projected_scenario_hash`. Exact-head CI passed 4/4 for #171 (`45089066900`), #172 (`45093439437`), #173 (`45096233966`) and #178 (`45113858688`). Supporting metric PRs #175, #176, #179 and #180 are merged. Track A static symlink/reparse-point hardening #183 is merged (exact head `0f870e22aad3d2496a5da872c21c5871106e262d`, run `45126668732`, 4/4). Backup seal work began in #186; #189 closes the RT05c verification/restore record gaps at exact head `21b540ee91cbfb47335156c8f2c2510b1b4d7d45` (merge `757da519f7af2c75a515ca42c6d23015d9e47123`, run `45141079904`, 4/4). #192 closes the RT05d source-side consistency gap at exact head `bdf13a0663e5498c9d2e857817769985a8419e94` (merge/current main `3e55e5505cda38a2ccfdc93a3e9996120ebb659e`, run `45150068645`, 4/4): `backup()` strictly validates the source run record/seal before destination validation, creation or copying, then re-checks the copied record before manifest publication. #192 changes `agora/backup.py` and `tests/test_redteam_backup_records.py`. ChatGPT docs PR #191 is the latest docs-only merge at exact head `02a88463529559009adec76c052be94621aa557e` (merge `705fe5cfa157b36fd75c93a141afe39255c08b65`, run `45148838308`, 4/4; six paths all under `docs/**`). Static path checks do not eliminate path-based SQLite reopen TOCTOU; that threat-model decision remains owner-gated. M2 pilot provenance (#142) and atomic run-record publication (#161) remain part of the compatibility baseline.



The governed path is implemented but is not yet usable through the production CLI: `_governed_policy()` currently returns `None` because no production identity adapter exists, and the policy-required scenario-input builder denies the request before opening the snapshot. No validation dataset has been run. `VALIDATED_PREDICTION_ENABLED` remains `False`; this specification does not authorize a simulation or validation run.

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
- Still required: close the direct-constructor policy trust boundary so a caller cannot supply a self-consistent but policy-unapproved package; decide whether a bounded synthetic Principal is acceptable for local public-dataset validation or whether a production identity adapter is required; complete the owner-supplied dataset register; and obtain explicit owner approval to freeze the validation protocol before any validation run.

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

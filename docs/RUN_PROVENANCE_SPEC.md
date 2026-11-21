# Run Provenance for Scenario Inputs — Rung 4

**Status:** design only. This document does not edit `agora/sim/**`, change the
existing run engine, launch simulations, or enable validated prediction.

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

The envelope is written before the first round is committed and is included in
run exports and report provenance. `manifest_hash` is the canonical hash of
`input_manifest`; it is not a substitute for the exact `scenario_hash`.

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

Resume is permitted only when the newly computed scenario hash equals the
stored run record's `scenario_hash`, and the stored input manifest passes the
same canonical-hash and binding checks. A changed snapshot, schema, binding,
ontology pack, transformation policy, scenario parameter, or application input
therefore blocks resume with a safe mismatch diagnostic.

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

Future implementation tests must prove:

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

No implementation, simulation, calibration, backtest, forecast, network call,
credential use, or write-back is included in this specification.

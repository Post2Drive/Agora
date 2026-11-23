# Run Provenance for Scenario Inputs — Rung 4

**Status:** Normative contract; governed-input slices 4.1–4.4 and 4.6 (#163/#164/#171/#172/#173/#178), supporting metrics #175/#176/#179/#180, static path hardening #183, backup fixes #186/#189/#192 and RT06 read-side held-descriptor SQLite snapshots #197 are merged. #197 exact PR head `5d67cb4ceed8200a9a952b05ae1db9a58c3b0ba6`, merge/main `5cbe4cfbb82039543d408ab5c67e045e17e10a99`, exact-head CI run `45167913607` passed 4/4; it reads the audit chain, anchor and run-record seal through a held-descriptor snapshot with file-identity checks. Principal-bound authorization receipt #198 merged at exact head `d3a8435bbabc28a1e488d87b752b1350b99c687d`, merge `4a55f2efd44da7aea54adda6ca7787471dd97cba`, exact-head CI `45170449040` passed 4/4. Adapter-origin check #199 merged at exact head `851bbf1a217f018695133ee9c42f1c538fa088f0`, merge/current main `4a0607f8946e32ef828b47183099ead4f8ae2bd7`, exact-head CI `45173316190` passed 4/4. Latest docs PR #196 merged at exact head `f9d34afa5914ee1cd2ccfd39a722fbb791ac4591`, merge `34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c`, exact-head CI `45170530846` passed 4/4 (seven `docs/**` paths). #199 rejects hand-built Principals without adapter-origin provenance, but the synthetic fixture remains test-only: Python callers in the same process can reach `_ISSUED` and `_MINT`, construct a receipt with the module sentinel, and bypass the receipt's `__setattr__` via `object.__setattr__`; the fixture adapter also accepts a caller-supplied fixture table. There is no production identity adapter. `agora/cli.py::_governed_policy()` still returns `None`, so the production CLI denies before snapshot bytes are opened. #197 hardens read-side SQLite snapshots only; `AuditChainStore` writers still open by pathname, and Python versions before 3.11 fail closed because `Connection.deserialize` is unavailable. P2D PR #5 contains eight FiveThirtyEight old-model CSVs (644,042 bytes total) only on its unmerged branch, with no SHA-256 recorded; four large poll files are missing, and P2D main and Agora main contain no raw benchmark files. No complete per-file SHA-256 manifest exists. The owner approved five protocol design values on 23 November (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on); they become effective only after merge into the protocol and a complete freeze sentence. The per-file manifest is absent and the freeze sentence contains literal `<sha>`, so the protocol remains draft/unfrozen. The one-run approval remains dormant. No dataset has been run. Keep `VALIDATED_PREDICTION_ENABLED=False`; no validation run is authorized.

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
- Complete and verify the owner-controlled per-file dataset manifest (exact path, bytes, SHA-256, immutable source version and licence) and the election, retail and adoption source files. The owner named ChatGPT as a separate-process evaluator, but the evaluator's restricted scope, output custody and label-release boundary are not yet established.
- Merge the five owner-approved 23 November design values into `VALIDATION_PROTOCOL.md` (B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, temperature 0 with cache on); then obtain a complete per-file manifest SHA and a new owner freeze sentence naming the merged protocol commit and actual manifest SHA. The received sentence contains literal `<sha>` and is not a freeze.
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

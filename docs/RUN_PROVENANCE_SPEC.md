# Run Provenance for Scenario Inputs — Rung 4

**Current verified state — 25 Nov 2026:** This update is based on Agora main a0de2655da7c28d616ffa85183ebddebd39b5833; the provenance contract remains assessed against frozen v0.2 commit 3fc4bc4f9b06e90b4602169de4cc13534a403ca0. PRs #219, #224, #225, #223, #226, #212, and #227 are merged. #224's phase-1 verifier remains unwired and test-key-only, with no production key or durable production nonce store; the production CLI remains default-deny. The owner selected Railway for future company-pilot hosting, gated on security/access-control review and a spend limit. The official FiveThirtyEight 2020 state-average CSV is selected as a v1.0 draft candidate only; no file was acquired. Full run-level configuration, seven state-cycle exclusions, and first-calibration-failure disposition remain outstanding or unrecoverable. No v1.0 freeze, run, or label release is authorized. VALIDATED_PREDICTION_ENABLED=False.

**Historical status snapshot:** Normative provenance contract assessed against frozen v0.2 commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` and current main `c98d21084608ad4a300aa71bfbd3c623e92a6ccd` after merged #221 and #222 (both exact-head CI 4/4). #222 is test-only in tests/test_outcome_markers.py and does not alter the audit-chain writer-open implementation. Claude's exact 24 Nov 2026 ~18:15 IST collaboration-log entry declares **M3 REACHED (scope-limited)**, now effective after main documentation synchronization by PR #220 (merge `c98d21084608ad4a300aa71bfbd3c623e92a6ccd`); this is not predictive validity or production readiness. ChatGPT PR #210 merged at `58695236b79b55233d46c096c27cf7e479097beb` from exact head `2058e9b798d0b2633fff49db41a7e850fac6ae3f`; its nine paths were all `docs/**`, exact-head workflow `45387958484` passed 4/4. PR #216 merged at `ace85f6483ef0d20a1a3c916311232a81d7d05f9` from exact head `7ab7adab0753207b51580ceced0ba155202128be`; exact-head workflow `45391932296` passed 4/4. It adds `input_origin` to the provenance manifest, but `builder`/`synthetic_demo` are caller-imitable labels, not authenticated origin, a valid issuer proof or a policy allow. PR #219 is an open/draft design-only proposal for owner-held signed receipts and signed releases; exact-head CI `45407991180 (in progress)` passed 4/4, but no issuer, key custody, signed key list, nonce-replay store or release verifier is implemented. Do not rely on the label or design as an authorization control. The direct constructor remains untrusted, production CLI remains default-deny, and `VALIDATED_PREDICTION_ENABLED=False`. v0.2 run-spec SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`; v0.1 protocol SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66`; 15-row manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`. Claude reports Package E complete and the 2016 result loses to published average (MAE 7.362 vs 6.163; RMSE 8.747 vs 7.546; paired MAE difference +1.20 pp, 95% CI [+0.73,+1.84]). ChatGPT independently fetched the exact main-branch bytes of all nine non-sensitive PR #213 output/log artifacts and recomputed byte counts/SHA-256 against SHA256SUMS; all matched. ChatGPT did not access held-out labels or raw source CSVs and did not recalculate metrics. Full run-level configuration, the separate seven state-cycle exclusions and first-calibration-failure disposition remain outstanding. Package A is NOT EVALUABLE; Package R/M5 is dropped.

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
- #198/#199 implement a Principal-bound receipt and reject hand-built Principals that lack adapter-origin provenance. This is not a production trust boundary: the in-process `_ISSUED`/`_MINT` sentinels are reachable, the public `AuthorizationReceipt` constructor accepts `_MINT`, `object.__setattr__` bypasses the receipt setter, and the synthetic adapter accepts caller-supplied fixture definitions. Static review of `Simulation(..., governed_input=...)` shows that the engine validates the caller-supplied manifest and receipt scope but does not call `build_scenario_input()`/`enforce_policy()` again. PR #216 is now merged and adds an `input_origin` provenance label plus a caller-supplied `synthetic_demo` marker; its own test demonstrates that a same-process caller can imitate builder-shaped fields and be labelled `builder`, so the field is not an authenticated origin or policy decision. Direct same-process construction remains forgeable and can bypass the builder's `POLICY_REQUIRED` gate with a matching `_MINT` receipt; the CLI remains default-deny because `_governed_policy()` returns `None`. PR #219 proposes owner-held asymmetric signing keys for receipts and signed releases, but is design-only; key custody, rotation/revocation, nonce replay, clock, trust-list distribution and independent release verification are undecided and unimplemented. Keep the fixture adapter test-only; do not treat receipt presence or `input_origin` as a fresh PDP allow. Any remediation must be tested against direct-constructor forgery; changes outside the already-approved `agora/sim/engine.py` require separate exact-path owner approval.
- #197 implements held-descriptor read-side snapshots for audit-chain, anchor and run-record/seal verification. `AuditChainStore` writer opens remain path-based; Python before 3.11 fails closed. Any writer-side race work must remain within the owner's explicit path approvals.
- Claude's reports state that the 12-file FiveThirtyEight sub-manifest on P2D PR #5 has matching source/committed-destination and Windows-checkout byte counts/SHA-256 values, and that the owner-approved MEDSL and Ember mirror files have been fetched/hash-verified in Claude's workspace. MEDSL: `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7`, `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0. Ember: `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0, 16-Nov snapshot. ChatGPT inspected GitHub metadata only, not raw CSV bytes. Neither mirror file is committed to P2D/Agora. Claude's 24 Nov entry states no private MEDSL/Ember import is required for frozen v0.2 because the public source commits and hashes are pinned in the frozen manifest; no further download/import is authorized. For frozen v0.2, the selected poll window is 2000–2016; 2020/2024 remain out of scope and Package R/M5 is dropped by owner decision. A separate v1.0 draft proposes a future 2020 holdout and requires a new owner-supplied polling file and separately versioned manifest; it does not amend v0.2, alter this provenance contract, or authorize acquisition or a run.
- The five owner-approved design values are effective under the frozen v0.1 protocol / v0.2 run-spec package. `VALIDATION_PROTOCOL.md` v0.1 is frozen at `6d06088cf7954bd41f003544f5ec61675389bcc1` under the owner's complete 23-Nov freeze attestation (manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`, evaluator ChatGPT in a separate process); its historical in-file “Draft preregistration only” header is preserved byte-for-byte; `VALIDATION_RUN_SPEC.md` v0.2 is frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` with SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`; the 15-row manifest SHA-256 is `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf` (manifest finalized by #203 merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`). Each artifact matches current main at its respective freeze reference; do not edit them in this docs sync. Any amendment requires a separately approved versioned freeze.
Claude reports its 2016 test-evaluate has already opened the held-out labels once after the recorded output seal matched. ChatGPT did not receive or access those labels. The nine non-sensitive PR #213 output/log artifacts were independently fetched from main and their byte counts/SHA-256 values matched SHA256SUMS. No raw source CSVs were accessed and no metrics were recalculated. A separately named owner-designated evaluator is required for any future label-based metric recalculation after explicit authorization. PR #214 adds missing-seal and valid-seal tests; exact-head CI `45313425335` passed 4/4. Review finding: the missing-seal test does not instrument MEDSL `sha256_file`, and the positive control does not explicitly assert output-read-before-MEDSL-hash order; static source order is correct.

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

This specification does not authorize any additional package, data, seed, configuration or rerun beyond the reported Package E stages. Claude reports its one test-evaluate opened 2016 labels only after the output seal matched; ChatGPT independently fetched and verified the exact bytes, byte counts and SHA-256 values of all nine non-sensitive PR #213 output/log artifacts against SHA256SUMS; all matched. No raw source CSVs or held-out labels were accessed and no metrics were recalculated. Any future label-based metric evaluation requires a separately named owner-designated evaluator and explicit authorization. Keep all outputs labelled exploratory and simulated; keep `VALIDATED_PREDICTION_ENABLED=False`.


## Current evidence limitations — owner clarification, 24 November 2026

Package E was run once: the 2012 result was a tie and the 2016 held-out result was a loss. This is final; no rerun is authorized. Package A is NOT EVALUABLE; Package R/M5 and retail are dropped. The seven state-cycle exclusions were not listed in the saved evidence and are unrecoverable. The first failed calibration attempt has no retained log or exit code and is unrecoverable from saved files. Full run configuration is only partly recorded: retain evidenced fields and mark all absent fields unavailable. A provenance envelope or this specification must not imply values that were never captured. Do not reconstruct missing exclusions, timestamps, exit codes, logs, partial-output inventories, hashes or configuration values. Frozen protocol, run-spec and manifest contents remain unchanged. VALIDATED_PREDICTION_ENABLED=False.

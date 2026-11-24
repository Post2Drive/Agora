# M3 Dataset Acquisition Checklist

**Purpose:** track frozen v0.2 Package E evidence, Package A NOT EVALUABLE status and the separate prospective v1.0 2020 holdout gate. Claude reports Package E complete with a negative 2016 held-out result. PR #213's nine generated output/log artifacts and SHA256SUMS are merged to main; ChatGPT independently fetched the exact main-branch bytes of all nine artifacts, recomputed byte counts and SHA-256 values against SHA256SUMS, and all nine matched. SHA256SUMS itself is 755 bytes with SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d`. No held-out labels or raw source CSVs were accessed; no metrics were recalculated. The nine-file byte-counted inventory is complete. Full run-level configuration/provenance, the separate seven state-cycle exclusions, and the first calibration failure's exit/log/partial-output disposition remain outstanding. Package R/M5 is dropped. The 2020 polling file has not been downloaded. The owner/Claude's 24 Nov direction says the pinned MEDSL/Ember public sources require no private mirror/import for M3 v0.2. No new data, download, import, run, label release or flag change is authorized; the frozen 15-row v0.2 manifest remains unchanged.

## Prospective v1.0 — 2020 polling file and label custody (DRAFT; not an acquisition authorization)

Claude's latest 24 November log entry reports the owner direction as "exploratory now, 2020 later", with minimal fundamentals only (incumbent party and previous-election state result). The exploratory analysis is not validation because 2016 labels were already opened. The future 2020 confirmatory holdout is not yet acquired, frozen or authorized.

- [ ] **2020 FiveThirtyEight state averages:** owner must later supply the exact 2020 presidential general-election state-average file. The current 12-file FiveThirtyEight handoff does not contain a verified 2020 polling file. Do not guess a filename, use the uncorrected 2024 file, or substitute another source.
- [ ] Record exact source URL, publisher/release or commit, original filename/path, access date, licence text/version/terms, byte count, SHA-256, schema/header allow-list, margin field/units and any correction history.
- [ ] **MEDSL V20.0 outcomes:** use the already pinned public MEDSL V20.0 source/commit/path/bytes/SHA-256/CC0 1.0 record in the frozen v0.2 manifest; do not download, mirror or stage a private copy for M3. Before a future v1.0 freeze, verify that this exact pinned file includes the 2020 rows and reference the same source identity in the new versioned manifest. Keep the 2020 outcome rows sealed from the operator/model-development process until the prediction output freeze.
- [ ] Create a separate versioned, hash-only v1.0 manifest in an owner-approved repository containing every v1.0 input, including the later owner-supplied 2020 poll file and the already pinned public MEDSL file, with per-file bytes, SHA-256, source/version and licence. A raw MEDSL mirror is not required; do not edit the frozen `docs/VALIDATION_DATASET_MANIFEST.csv` or its 15-row v0.2 hash.
- [ ] Confirm the 2020 state/area universe, 28/14/7-day cutoffs, mode handling, blend-weight fitting/tie-break, incumbent-party treatment, interval construction/levels, bootstrap seed and exclusion rules before protocol freeze.
- [ ] Establish separate output-freeze and evaluator label-release custody. The 2020 labels may be released only after all prediction outputs and the complete output inventory are frozen and hashed.
- [ ] Obtain a complete owner v1.0 freeze sentence and a separate run authorization. Until then, no download, import, run, evaluation or label release.

**Current status:** no 2020 polling file has been downloaded for v1.0. The 2020 rows in the already pinned MEDSL file are future held-out labels, not training inputs; no private MEDSL copy or new download is required for M3. A tie or loss to poll alone is an acceptable reported result; do not tune or select a model using 2020 outcomes.

## FiveThirtyEight polls handoff — 23 November 2026 (P2D PR #5 branch inventory)

The private `Post2Drive/Post2Drive` main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR [#5](https://github.com/Post2Drive/Post2Drive/pull/5) is still **open, draft and unmerged** at branch commit `b06b29cb2071f048f0c234f65c1014ea4677d33d` on `data/import-fivethirtyeight-polls-2026-11-23`. The PR now contains 12 CSVs (94,181,506 bytes) and `validation-data/elections/fivethirtyeight-polls/DATASET_MANIFEST.csv` with one per-file SHA-256 row for each CSV. The pinned source is FiveThirtyEight/data commit `4c1ff5e3aef1816ae04af63218015066e186c147`; the import README identifies CC BY 4.0, includes the upstream licence text, and has a package-scoped `.gitattributes` rule to preserve CSV bytes on Windows checkouts.

The manifest's Git blob identifier is `308dfbd4fec4de36ffe1bda9dd3d15ec88870f8b`; this is a Git object ID, **not** the manifest file's SHA-256. The exact 4,679-byte manifest file has SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`, recorded in the private import README. Claude's STEP 5 report states that all 12 committed CSV byte counts and SHA-256 values matched the pinned publisher tree and that all 12 Windows checked-out files matched as well. ChatGPT's connector review inspected the PR metadata, manifest and import README only; it did not fetch raw CSV bytes or independently reproduce Claude's checks. The PR remains unmerged, so these files are not in P2D main or Agora main (`5ec1bdd62d562cb8ef2ef58d54b61d717232e4ec`).

| Relative path under `validation-data/elections/fivethirtyeight-polls/` | Bytes | Per-file SHA-256 in PR #5 manifest |
|---|---:|---|
| `old_model/2024_presidential_primary_averages_old_model.csv` | 23,289 | `fb6d3f09936126651d60f30bc1559703611dc6b3cf28ef6185116d3e952a4c26` |
| `old_model/donald_trump_favorability_old_model.csv` | 82,705 | `4c39fe81a0d753551395c5436aa920546e1c4caf4611fed481b6ac98955c973a` |
| `old_model/generic_ballot_averages_old_model.csv` | 229,659 | `caae521c49a1ec9387a84a1a40f8f5a4555215513334cb667474d4f2ff130840` |
| `old_model/joe_biden_approval_old_model.csv` | 105,827 | `a65f9320d7202809289a4de50032892a282c8e73970057b87bf58899ed5f4849` |
| `old_model/kamala_harris_approval_old_model.csv` | 84,376 | `7cb826b1b247fdcb7fcbb941586c1b0c042f39a45f5828c40d3c6e3dfd8431b8` |
| `old_model/mike_pence_favorability_old_model.csv` | 46,274 | `4e174e4affc7dfedb847d75cc1fbb162eba61ffb77961085e45c224a71613f03` |
| `old_model/nikki_haley_favorability_old_model.csv` | 23,681 | `edbba323c9c857adffe991cb4ce4720a33944828a0e4349b5a75a8b019bbddc3` |
| `old_model/ron_desantis_favorability_old_model.csv` | 48,231 | `60a6d875a0b201f29280facd6fe59d26fe147005445790676ec281fbc6ab6e20` |
| `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1,604,311 | `c66cf38aa566c3dfa0b50823e8259d9631bfb5ab830c18af13dd54204a8d8b35` |
| `polls/2024-averages/presidential_primary_averages_2024.csv` | 11,407,331 | `0d22110875abddbed1b0709553ba9e2c20e459f0ca8254961e321c9ac18791cc` |
| `polls/pres_pollaverages_1968-2016.csv` | 50,438,309 | `b897a8bc5f17ad0a2e959422cb8ec480dab5fcf25555b8eaaed60472ce68efcd` |
| `polls/pres_primary_avgs_1980-2016.csv` | 30,087,513 | `d30dd11829cd8748cbe3bfbb326d7708f03f3c3abe323edf43d29c0f7501944d` |

The 2024 general-average file is explicitly **uncorrected** and must not be described or used as the corrected 2024 averages. The 12-row manifest does not establish corrected-2024 or 2020 polling coverage, owner approval for use, or permission to run a benchmark. Claude's STEP 5 source review reports that `polls/pres_pollaverages_1968-2016.csv` contains FiveThirtyEight's daily state-level published averages, not individual poll records or sample sizes; usable elections in that file are 2000, 2004, 2008, 2012 and 2016, with 50–57 areas each from 1 October to Election Day. The draft default baseline is the latest publisher average for the same state/office dated on or before each cutoff, with previous-election state-margin persistence reported separately. Do not compute a sample-size-weighted 28-day mean from this averages file. The individual-poll alternative (`president_polls_historical.csv`) was not checked; use it only if the owner explicitly asks Claude to try the live links, then record the result and amend/version the draft protocol before freeze. Keep the source commit, path, byte count, per-file SHA-256 and CC BY 4.0 licence tied to each row.

## Current package source and custody status — 24 November 2026

- **FiveThirtyEight polls:** all 12 CSVs (94,181,506 bytes) remain on open/draft/unmerged Post2Drive PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; the 4,679-byte sub-manifest SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude reports source, PR-branch and Windows checkout bytes/hashes match; ChatGPT has not fetched/re-hashed the raw CSVs. PR #5 contains no MEDSL or Ember raw files.
- **MEDSL V20.0:** the frozen 15-row manifest pins the owner-approved public source `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7`, `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0. Claude reports workspace byte/hash verification. The latest owner/Claude direction says no private MEDSL import is required for frozen v0.2; no further download or import is authorized. Use TOTAL mode where present; otherwise sum modes, never both.
- **Ember:** the frozen 15-row manifest pins the owner-approved public source `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0; monthly rows only. Package A is NOT EVALUABLE, so no private Ember import or further acquisition is required for M3.
- Claude's 23-Nov 22:40 report says all 15 manifest files were re-fetched from pinned public commits and matched the recorded bytes and SHA-256. This remains Claude-reported verification; ChatGPT did not fetch or re-hash raw files. Claude's 24 Nov 08:35 entry explicitly stops the MEDSL/Ember private import: the frozen manifest pins public source commits and hashes, so no private copy is required for M3 v0.2. Do not download or import new copies. P2D PR #5 remains limited to the 12 FiveThirtyEight CSVs plus import support.
- Agora's `docs/VALIDATION_DATASET_MANIFEST.csv` is a 15-row hash-only register, finalized by PR #203 (exact head `3f85a1419921a142b3050d7094757bc32e19adba`, merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`), with SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf` and current Git blob `ba684b0a1884f11e6331bcf5130b092c71c1303b`; active E/A rows are `PLANNED - NOT EXECUTED`. For frozen v0.2, this hash-only register plus the exact pinned public source commits is the accepted source/version/hash record; no private raw-file copy is required. It is not a raw-data handoff. Any future v1.0 acquisition is a separate owner-supplied, separately versioned and approved task.
- **Package R/M5:** dropped by the owner on 23 November 2026. No Kaggle acquisition, no Rossmann substitute, no retail claim; this is not a remaining acquisition decision.

Package E is the only evaluable run scope; Package A is predeclared NOT EVALUABLE and Package R/M5 is dropped. Claude's results note reports a 2012 MAE tie with worse RMSE and a 2016 loss to published-average and persistence baselines. PR #213 merged nine output/log artifacts and SHA256SUMS to main. ChatGPT independently recomputed the SHA-256 and byte count of all nine PR #213 repository artifacts against SHA256SUMS; all matched. No held-out labels were accessed and no metrics were recalculated. The nine-file byte-counted inventory and SHA256SUMS hash are recorded in EVALUATOR_CUSTODY.md; complete run configuration, exact exclusions and first calibration failure disposition remain outstanding. No additional data/import/run is authorized.



## Important distinction

There are **two active benchmark packages, not three individual files**:

- Package E is a paired election benchmark with FiveThirtyEight polling averages and MEDSL election returns.
- Package A is an Ember monthly EV dataset, predeclared NOT EVALUABLE under v0.2.
- Package R/M5 was explicitly dropped by the owner; retail is untested and no Rossmann substitute is selected.

Keep original source filenames and archive structure until the source release, licence and SHA-256 values have been recorded. Do not commit raw benchmark data or derived label files to this repository.

## Package E — election polls and county returns

**Download locations:** [FiveThirtyEight 2000–2016 published averages](https://github.com/fivethirtyeight/data/tree/4c1ff5e3aef1816ae04af63218015066e186c147/polls), [MEDSL V20.0 owner-approved mirror](https://github.com/mathis-group/cas-201-data-project/tree/1358bc6047f0c22989d37fa64ac03ee755bd17e7/data/medsl), and [original MEDSL Dataverse DOI](https://doi.org/10.7910/DVN/VOQCHQ).

**Expected fields to verify against the exact downloaded headers (names below are semantic fields, not guaranteed literal column names):**

- Poll averages file: state/geography, date, candidate, published average and source-defined margin/trend fields actually present. This is not an individual-poll file; do not expect or infer poll ID, pollster, sample size, start/end dates or poll-quality metadata.
- Results file: election year, state/state code, county identifier/FIPS, candidate, party, candidate votes, total votes, `mode` and source/version metadata. MEDSL mode rule: use the `TOTAL` mode row where present; otherwise sum the available mode rows. Never sum a `TOTAL` row together with component mode rows. Claude reports 2024 has both `TOTAL` and mode rows, so naïve summation double-counts; 2024 is outside the selected 2000–2016 window.
- Exclude free-text notes if present, respondent-level data, personal identifiers and all post-cutoff/post-election fields from the predictor package.
- **Coverage gate:** the selected draft window is 2000–2016: training 2000/2004/2008, validation 2012, held-out test 2016. The pinned `polls/pres_pollaverages_1968-2016.csv` is a publisher daily state-level averages file, not individual polls or sample sizes. 2020 and 2024 are outside this selected window; the uncorrected 2024 file must not be used. Use the latest same-state/office publisher average available on or before each 28/14/7-day cutoff, plus a separately labelled previous-election state-margin persistence baseline. Do not derive a sample-size-weighted 28-day poll mean from the averages file. The individual-poll option is not selected unless the owner explicitly asks Claude to try the live links.

- [x] Pin the FiveThirtyEight published-average file `polls/pres_pollaverages_1968-2016.csv` to commit `4c1ff5e3aef1816ae04af63218015066e186c147`; its per-file hash is in P2D PR #5. Claude reports the source/destination bytes and SHA-256 match. Do not fetch individual-poll files unless the owner explicitly asks Claude to try option-b live links.
- [x] The 2000–2016 draft window is selected under Claude's delegated design choice: train 2000/2004/2008, validate 2012, test 2016. The 2020 and 2024 files are out of scope; explicitly exclude the uncorrected 2024 general-average file. Any later window change requires a versioned protocol amendment before freeze.
- [x] Record and retain the FiveThirtyEight CC BY 4.0 attribution and licence text/version in the pinned source and P2D import README.
- [x] The exact MEDSL public source commit and file SHA-256 are recorded in the frozen 15-row manifest; Claude reports the 10,222,208-byte file hash matched in its workspace. Per the 24 Nov owner/Claude direction, no private MEDSL import is required for M3 v0.2; no further download/import is authorized.
- [x] Record the original MEDSL Dataverse citation, Version 20.0 and CC0 1.0 dataset licence. The mirror repository's MIT licence is for code only; it does not replace the dataset's CC0 licence.
- [x] Private MEDSL import is not an M3 v0.2 gate: the frozen manifest pins the approved public source commit, file hash, version and CC0 licence. Keep the source assets logically separate; do not download/import another copy.

## Package R — M5 Walmart retail sales (DROPPED)

The owner explicitly dropped Package R/M5 on 23 November 2026. Do not acquire M5, do not substitute Rossmann, and do not include retail in the evaluation scope. Retail is untested. This section is retained only to document the excluded package; no acquisition checklist applies.

## Package A — Ember Monthly EV Sales

**Status under v0.2:** predeclared **NOT EVALUABLE**. The run specification records that no deterministic, defensible mapping exists from AGORA counted actions to monthly EV registrations without fitting an invented conversion rule on the same series. Do not run an Ember simulation or make a predictive claim for Package A under the current protocol. The 2024–2025 held-out labels remain sealed; no label release is required for a package already declared not evaluable.

**Source and mirror:** owner-approved 16-Nov-2026 snapshot at `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv`; 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0. Monthly rows only; quarterly rows excluded. Claude reports re-verification against the pinned commit in the 23-Nov 22:40 pre-run check. ChatGPT did not independently fetch or re-hash this raw file. The file is not included in P2D PR #5.



## Per-file evidence register

For every file, record:

| Field | Required value |
|---|---|
| Package | E, R or A |
| Source / publisher | Exact publisher and dataset title |
| Source URL / DOI | Canonical source |
| Licence / terms | Exact licence name/version or competition rules |
| Citation / attribution | Publisher's required wording |
| Release / version | Exact release or Dataverse version |
| Source commit | Full immutable source commit SHA; for non-Git publishers record `N/A — non-Git source` |
| Publisher release/version | Exact immutable release, Dataverse version or DOI for the file |
| Access date | Local date downloaded |
| Original filename | Do not rename before hashing |
| File size | Bytes |
| SHA-256 | Hash of the exact downloaded bytes (64 lowercase hexadecimal characters) |
| Intended split / role | As preregistered; never infer from filename |

## Required SHA-256 manifest (hard acquisition gate)

For any newly acquired or privately staged dataset, the owner-controlled private repository must contain a machine-readable manifest with one row per file: package, path, original filename, bytes, SHA-256, source URL/commit/release, licence/version, access date and citation. Frozen v0.2 uses Agora's 15-row `docs/VALIDATION_DATASET_MANIFEST.csv` (finalized by #203 merge `3872f2401a8c6c6de097ad82a701414e8b1a26c9`; SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) together with the pinned public source commits; no private MEDSL/Ember copy is required. P2D PR #5 stages only the 12 FiveThirtyEight CSVs and its separate 12-row sub-manifest. Claude reports all 15 selected manifest files were re-fetched from pinned commits with matching bytes and SHA-256; ChatGPT did not fetch or re-hash raw files. Package R/M5 is dropped. For future acquisitions, preserve per-file verification and do not substitute Git blob IDs, MD5 values or archive hashes for raw-file SHA-256. A missing source revision, hash, byte count or licence is a failed acquisition gate. No new acquisition, import or validation is authorized by this checklist.

### Pinned public-source metadata for frozen v0.2 (no private import required)

| package | repository / branch | relative_path | bytes | sha256 | source commit / release | licence / version |
|---|---|---|---:|---|---|---|
| E — MEDSL V20.0 | `mathis-group/cas-201-data-project` (owner-approved; Claude workspace only) | `data/medsl/countypres_2000-2024.csv` | 10222208 | `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8` | `1358bc6047f0c22989d37fa64ac03ee755bd17e7`; Dataverse V20.0 | CC0 1.0 dataset; mirror MIT is code only |
| A — Ember 16-Nov-2026 snapshot | `Awes0mer/fuel-cars-pollution` (owner-approved; Claude workspace only) | `data/raw/ember_ev_monthly/monthly_ev_sales.csv` | 7695642 | `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2` | `2c21f1edced7aae884314ebc28c89ab212f30563`; source manifest 2026-11-16 | CC BY 4.0 data; mirror MIT is code only |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |
|  |  |  |  |  |  |

Claude reports the 12 FiveThirtyEight rows verified against the pinned source and committed P2D destination. Claude also reports the MEDSL and Ember hashes above verified in its workspace; ChatGPT did not inspect raw CSV bytes. No private MEDSL/Ember copy is required for frozen v0.2 and no further import/download is authorized. Do not treat these Claude-reported checks as independent ChatGPT byte verification or substitute Git blob IDs/MD5 values for SHA-256.

## Handoff and stop conditions

1. For frozen v0.2, use the exact pinned public source commits and hash-only manifest; no private MEDSL/Ember copy is required. Do not transfer raw source CSVs or held-out labels to ChatGPT/Notion and do not commit raw source datasets to Agora. Non-sensitive generated prediction/output artifacts may be integrity-checked when explicitly requested; PR #213's nine output/log files were verified. Future v1.0 acquisition requires separate owner supply, approval and a new manifest.
2. P2D PR #5 remains open/draft/unmerged at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; its 18 paths contain 12 FiveThirtyEight CSVs plus import support only. MEDSL/Ember absence from that PR is intentional under the 24 Nov no-private-import direction and is not an M3 blocker.
3. Package A is predeclared NOT EVALUABLE and Package R/M5 is dropped. No Ember acquisition/run is required. Package E's one authorized run is reported complete; no rerun or new input acquisition is authorized. PR #213 merged nine output/log artifacts and SHA256SUMS into main. ChatGPT independently fetched and hashed all nine repository artifacts; per-file byte counts and SHA-256 values matched SHA256SUMS. SHA256SUMS itself is 755 bytes with SHA-256 `7ac2ffece93b4c923e26d35f8b59fc24c38373d8ad515b7f7d8165ca1c9a8c7d`. No held-out labels or raw source CSVs were accessed; no metrics were recalculated. The byte-counted inventory is recorded in EVALUATOR_CUSTODY.md. Remaining evidence gaps are the full run configuration, exact seven state-cycle exclusions and first calibration failure disposition. No separate raw-file handoff is required for frozen v0.2.
PR #211 merged the test-evaluate output-seal check before MEDSL hashing/loading (exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`, merge `2730903234196e9b38914ccb0fcab2de4e6c16ca`, exact-head CI `45229437458` passed 4/4). PR #214 merged the missing-seal negative and matching-seal positive controls at exact head `e6f48ed9a6305d9f325c99099bc1c653f274c9a5`, merge/current main `b111a4f918710f41650c659c40cad593419b02af`, CI `45313425335` passed 4/4. Static review of current main confirms test-evaluate reads and hashes test_outputs.json, rejects an absent or mismatched seal, then verifies MEDSL and calls load_outcomes. The missing-seal test instruments load_outcomes but not MEDSL sha256_file; the positive test proves one load/result but not explicit output-read-before-MEDSL-hash ordering. These are test-strengthening recommendations, not an observed ordering defect or evidence labels were accessed before the seal. The output files show cutoff-level exclusions: 2016 District of Columbia at 2016-10-11; 2012 District of Columbia and Idaho at 2012-10-09, each with no published average on or before that cutoff. The separate seven state-cycle exclusions remain unenumerated. ChatGPT did not inspect held-out labels or run project code/tests. The first calibration process's silent exit/partial-output disposition remains undocumented.
5. Protocol v0.2 is frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` under the owner's conditional pre-approval. The only addition to v0.1 is `docs/VALIDATION_RUN_SPEC.md` (SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`); v0.1 protocol file SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66` remains unchanged; the separately finalized 15-row manifest was merged in #203 at `3872f2401a8c6c6de097ad82a701414e8b1a26c9` (SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`) and is included unchanged in the v0.2 freeze. Claude reports exact-head and merge-commit CI 4/4.
Claude reports that the 2016 labels were opened for its completed test-evaluate only after the output seal matched. ChatGPT did not receive or access those labels. ChatGPT independently fetched and hashed the nine non-sensitive PR #213 repository artifacts; all nine byte counts and SHA-256 values match SHA256SUMS. No metrics were recalculated. A separate owner-designated evaluator is required only for any future label-based recalculation after explicit authorization. PR #214's missing-seal and valid-seal tests passed exact-head CI 4/4; static source order is correct, but tests do not instrument MEDSL sha256_file on the missing-seal path or explicitly assert output-read-before-MEDSL-hash order on the positive path. The seven state-cycle exclusions and first calibration failure disposition remain outstanding.
7. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged. No flag change, extra data, rerun, retail test or use of real/personal data is authorized.



## Personal-data and data-minimisation gate

Before hashing/import handoff, inspect the exact headers and a small, controlled sample of rows locally. Record only the inspection outcome, not raw row values:

- [ ] No respondent-level, customer-level, driver-level or other directly identifying records are present.
- [ ] No names, emails, phone numbers, addresses, account IDs or precise personal-location fields are included.
- [ ] Free-text notes/comments are excluded unless a separately approved, documented necessity exists; default is exclude.
- [ ] No sensitive personal attributes or inferred sensitive traits are included.
- [ ] Any unexpected personal/sensitive field causes a stop and owner review; do not upload it to ChatGPT, GitHub or Notion.
- [ ] Retain only source metadata, schema/header allow-list, licence evidence, file size and SHA-256 in the dataset register.

**Retail scope note:** Package R/M5 is dropped by the owner. No Kaggle files are to be acquired and no retail benchmark is included in the current validation scope.


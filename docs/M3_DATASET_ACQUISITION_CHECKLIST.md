# M3 Dataset Acquisition Checklist

**Purpose:** track Package E and Package A under frozen protocol v0.2. Claude reports the first Package E calibration process exited silently without outputs; a tracked background task was restarted from frozen commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`. No completed result or output inventory/hash is recorded. Package A is predeclared NOT EVALUABLE and Package R/M5 is dropped. This checklist does not authorize additional data, runs or imports; the 15-row manifest remains hash-only and unchanged.

## FiveThirtyEight polls handoff — 23 November 2026 (P2D PR #5 branch inventory)

The private `Post2Drive/Post2Drive` main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR [#5](https://github.com/Post2Drive/Post2Drive/pull/5) is still **open, draft and unmerged** at branch commit `b06b29cb2071f048f0c234f65c1014ea4677d33d` on `data/import-fivethirtyeight-polls-2026-11-23`. The PR now contains 12 CSVs (94,181,506 bytes) and `validation-data/elections/fivethirtyeight-polls/DATASET_MANIFEST.csv` with one per-file SHA-256 row for each CSV. The pinned source is FiveThirtyEight/data commit `4c1ff5e3aef1816ae04af63218015066e186c147`; the import README identifies CC BY 4.0, includes the upstream licence text, and has a package-scoped `.gitattributes` rule to preserve CSV bytes on Windows checkouts.

The manifest's Git blob identifier is `308dfbd4fec4de36ffe1bda9dd3d15ec88870f8b`; this is a Git object ID, **not** the manifest file's SHA-256. The exact 4,679-byte manifest file has SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`, recorded in the private import README. Claude's STEP 5 report states that all 12 committed CSV byte counts and SHA-256 values matched the pinned publisher tree and that all 12 Windows checked-out files matched as well. ChatGPT's connector review inspected the PR metadata, manifest and import README only; it did not fetch raw CSV bytes or independently reproduce Claude's checks. The PR remains unmerged, so these files are not in P2D main or Agora main (`2730903234196e9b38914ccb0fcab2de4e6c16ca`).

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

## Current package acquisition and custody status — 23 November 2026

- **FiveThirtyEight polls:** all 12 CSVs (94,181,506 bytes) remain on open/draft/unmerged Post2Drive PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; the 4,679-byte sub-manifest SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude reports source, PR-branch and Windows checkout bytes/hashes match; ChatGPT has not fetched/re-hashed the raw CSVs. PR #5 contains no MEDSL or Ember raw files.
- **MEDSL V20.0:** the owner-approved mirror is `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7`, `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0. Use TOTAL mode where present; otherwise sum modes, never both.
- **Ember:** the owner-approved 16-Nov-2026 mirror is `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0; monthly rows only.
- Claude's 23-Nov 22:40 report says all 15 manifest files were re-fetched from their pinned commits and matched the recorded bytes and SHA-256. This is Claude-reported verification; ChatGPT did not independently fetch or re-hash MEDSL/Ember raw files. The MEDSL/Ember files remain absent from P2D PR #5, whose changed-file list is still only the 12 FiveThirtyEight CSVs plus import support.
- Agora's `docs/VALIDATION_DATASET_MANIFEST.csv` is a 15-row hash-only register with SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`; active E/A rows are `PLANNED - NOT EXECUTED`. This documentation manifest is not a substitute for committing the raw selected files and their per-file manifest to the owner-controlled private data repository.
- **Package R/M5:** dropped by the owner on 23 November 2026. No Kaggle acquisition, no Rossmann substitute, no retail claim; this is not a remaining acquisition decision.

Package E is the only active run scope; Package A is predeclared NOT EVALUABLE and Package R/M5 is dropped. No raw benchmark file has been committed to Agora. Claude's 23:20 IST log reports the first calibration process exited silently with no output and no labels beyond training 2000/2004/2008; a tracked background task was restarted from frozen v0.2 commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` at approximately 17:43 UTC. No completed result, output inventory/hash or held-out-label release is recorded.



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
- [x] Owner approved the exact MEDSL mirror commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7` and file `data/medsl/countypres_2000-2024.csv`; Claude reports the 10,222,208-byte file SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`. The file remains in Claude's workspace only and must still be committed to the owner-controlled private repository.
- [x] Record the original MEDSL Dataverse citation, Version 20.0 and CC0 1.0 dataset licence. The mirror repository's MIT licence is for code only; it does not replace the dataset's CC0 licence.
- [ ] Commit the approved MEDSL mirror file, codebook and required attribution/manifest row to the owner-controlled private repository. Keep polling and returns as separate source assets; do not combine or aggregate them before the preregistered transformations are frozen.

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

Before any dataset import, the owner-controlled private data repository must contain a committed machine-readable manifest (CSV or JSON) with one row/object for every selected source file and at least: package, relative_path, original_filename, bytes, sha256, source_url, source_commit, publisher_release, licence_and_version, access_date and citation. Agora's 15-row `docs/VALIDATION_DATASET_MANIFEST.csv` is a hash-only register (SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`), not the private raw-file handoff. P2D PR #5 stages only the 12 FiveThirtyEight CSVs and its separate 12-row sub-manifest; MEDSL and Ember raw files are not in that PR. Claude reports all 15 selected manifest files re-fetched from pinned commits with matching byte counts and SHA-256, but ChatGPT has not independently reproduced the MEDSL/Ember checks. Package R/M5 is dropped. Preserve per-file verification for every later transfer; do not substitute Git blob IDs, MD5 values or archive hashes for raw-file SHA-256. A missing file, blank hash, byte-count mismatch, unknown source revision or unresolved licence is a failed acquisition gate. No validation is authorized by this checklist.

### Additional owner-approved mirror rows (Claude workspace only; not staged)

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

Claude reports the 12 FiveThirtyEight rows verified against the pinned source and committed P2D destination. Claude also reports the MEDSL and Ember mirror hashes above verified in its workspace; ChatGPT inspected GitHub tree/README/codebook/manifest metadata only, not raw CSV bytes. The two approved mirror files are not yet in P2D. Use `Get-FileHash -LiteralPath <exact path> -Algorithm SHA256` and `Get-Item -LiteralPath <exact path> | Select-Object FullName,Length` to independently recheck before owner acceptance. Do not put Git blob IDs or the MEDSL candidate MD5 in the SHA-256 column.

## Handoff and stop conditions

1. Keep raw source files in the owner-controlled private data repository, separate from AGORA. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to the AGORA source repository.
2. P2D PR #5 remains open/draft/unmerged at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; its 18 paths contain 12 FiveThirtyEight CSVs plus import support only. MEDSL and Ember are not included.
3. Package R/M5 is dropped and is not a blocker. The remaining custody task is to stage the approved MEDSL and Ember raw files, codebook/attribution and a complete per-file manifest in the owner-controlled private repository, with source/destination byte and SHA-256 equality.
PR #211 has merged the test-evaluate output-seal check ahead of MEDSL hashing/loading (exact head `1d90528de82d2a08f24ad38cf6c7c5c7bdd15eb0`, merge `2730903234196e9b38914ccb0fcab2de4e6c16ca`, exact-head CI `45229437458` passed 4/4). The merged test covers a wrong-seal negative only. A missing-seal negative and valid-seal positive control, with mutation proofs, remain required before any 2016 label release. No held-out labels before output freeze and independent output-integrity review.
5. Protocol v0.2 is frozen at `3fc4bc4f9b06e90b4602169de4cc13534a403ca0` under the owner's conditional pre-approval. The only addition to v0.1 is `docs/VALIDATION_RUN_SPEC.md` (SHA-256 `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`); v0.1 protocol file SHA-256 `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66` and manifest SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf` are unchanged. Claude reports exact-head and merge-commit CI 4/4.
The 2016 held-out labels remain closed until the output inventory is logged and independently hash-checked, the #211 seal-order correction is supplemented by missing-seal negative and valid-seal positive-control tests with exact-head CI 4/4, and the separate label handoff is recorded.
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


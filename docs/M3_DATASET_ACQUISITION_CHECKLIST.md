# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation. For non-technical, owner-operated download steps, use [`DATASET_DOWNLOAD_GUIDE.md`](DATASET_DOWNLOAD_GUIDE.md); this checklist remains the source-of-record for approved source/version/hash and licence gates.

## FiveThirtyEight polls handoff — 23 November 2026 (P2D PR #5 branch inventory)

The private `Post2Drive/Post2Drive` main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR [#5](https://github.com/Post2Drive/Post2Drive/pull/5) is still **open, draft and unmerged** at branch commit `b06b29cb2071f048f0c234f65c1014ea4677d33d` on `data/import-fivethirtyeight-polls-2026-11-23`. The PR now contains 12 CSVs (94,181,506 bytes) and `validation-data/elections/fivethirtyeight-polls/DATASET_MANIFEST.csv` with one per-file SHA-256 row for each CSV. The pinned source is FiveThirtyEight/data commit `4c1ff5e3aef1816ae04af63218015066e186c147`; the import README identifies CC BY 4.0, includes the upstream licence text, and has a package-scoped `.gitattributes` rule to preserve CSV bytes on Windows checkouts.

The manifest's Git blob identifier is `308dfbd4fec4de36ffe1bda9dd3d15ec88870f8b`; this is a Git object ID, **not** the manifest file's SHA-256. The exact 4,679-byte manifest file has SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`, recorded in the private import README. Claude's STEP 5 report states that all 12 committed CSV byte counts and SHA-256 values matched the pinned publisher tree and that all 12 Windows checked-out files matched as well. ChatGPT's connector review inspected the PR metadata, manifest and import README only; it did not fetch raw CSV bytes or independently reproduce Claude's checks. The PR remains unmerged, so these files are not in P2D main or Agora main (`4a0607f8946e32ef828b47183099ead4f8ae2bd7`).

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

## Remaining package acquisition gates — 23 November 2026 (updated after Claude's mirror check)

- **FiveThirtyEight polls:** all 12 CSVs and their per-file manifest are staged on open/draft/unmerged P2D PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d`. Claude's STEP 5 report states that source and committed-destination byte counts/SHA-256 values match for all 12 files and that the Windows checked-out files match after CSV line-ending conversion was disabled. The manifest file itself is 4,679 bytes with SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. ChatGPT did not fetch raw CSV bytes or independently reproduce those checks. The PR must be merged or otherwise owner-accepted before use. Its 2024 general-average file is uncorrected; corrected 2024 and 2020 coverage are not established by these 12 rows.
- **MEDSL Version 20.0:** the owner explicitly approved the exact mirror `mathis-group/cas-201-data-project` at commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7`, file `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes). Claude reports SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, 94,151 data rows, Version 20.0, and CC0 1.0 dataset licence; the mirror repo's MIT licence applies to code only. The exact codebook and data README are present at the pinned commit. The raw CSV is in Claude's session workspace only, not P2D or Agora. ChatGPT inspected repository tree, README and codebook metadata, not raw CSV bytes; it did not independently reproduce the hash. No Dataverse guestbook response was submitted.
- **M5 Walmart / Rossmann:** no retail files are present. M5 is now the only remaining owner download/terms decision: acquire the exact Kaggle bundle after personal competition-terms review, or explicitly drop retail from this benchmark. Rossmann was not selected and is not an automatic substitute.
- **Ember monthly EV:** the owner explicitly approved the exact mirror `Awes0mer/fuel-cars-pollution` at commit `2c21f1edced7aae884314ebc28c89ab212f30563`, file `data/raw/ember_ev_monthly/monthly_ev_sales.csv` (7,695,642 bytes). Claude reports SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, 46,799 rows, monthly and quarterly, 2005-01 to 2026-10, 59 countries; India has 729 rows from 2020-01 to 2026-09 across BEV, PHEV and total drivetrains. Label it **16-Nov-2026 snapshot**, not the 18-Nov update. Data licence is CC BY 4.0 per the mirror manifest/README; the mirror repo's MIT licence applies to code only. The raw CSV is in Claude's session workspace only, not P2D or Agora. ChatGPT inspected repository tree, README and manifest metadata, not raw CSV bytes; it did not independently reproduce the hash.
- **Manifest gate:** P2D PR #5 contains only the 12 FiveThirtyEight CSVs and its 4,679-byte manifest file SHA-256 is recorded above. Claude reports the MEDSL and Ember mirror hashes above verified, but both raw files remain in Claude's workspace only and are not staged in P2D. The complete all-package manifest cannot be frozen until the owner decides M5 vs drop-retail and the selected files are committed to the owner-controlled private repository.

Claude's STEP 5 report states that the 12 FiveThirtyEight CSVs were verified against the pinned source and committed P2D PR #5 branch, including Windows checkout bytes. A later Claude entry reports the owner-approved MEDSL and Ember mirror files fetched and SHA-256 verified in Claude's workspace only; neither was committed to P2D or Agora. ChatGPT inspected only public repository trees, README/codebook and manifest metadata, not raw CSV bytes, and did not independently reproduce those hashes. No raw dataset was downloaded by ChatGPT, no data was imported, and no simulation or validation was run.

## Important distinction

There are **three benchmark packages, not three individual files**:

- Package E is a paired election benchmark with polling and election-return sources.
- Package R is a multi-file M5 retail bundle.
- Package A is an Ember monthly EV dataset.

Keep original source filenames and archive structure until the source release, licence and SHA-256 values have been recorded. Do not commit raw benchmark data or derived label files to this repository.

## Package E — election polls and county returns

**Download locations:** [FiveThirtyEight 2000–2016 published averages](https://github.com/fivethirtyeight/data/tree/4c1ff5e3aef1816ae04af63218015066e186c147/polls), [MEDSL V20.0 owner-approved mirror](https://github.com/mathis-group/cas-201-data-project/tree/1358bc6047f0c22989d37fa64ac03ee755bd17e7/data/medsl), and [original MEDSL Dataverse DOI](https://doi.org/10.7910/DVN/VOQCHQ).

**Expected fields to verify against the exact downloaded headers (names below are semantic fields, not guaranteed literal column names):**

- Poll file(s): poll ID, pollster, state/geography, start/end date, sample size, population type, candidate, candidate percentage, mode and any source-defined poll-quality metadata used by the frozen mapping.
- Results file: election year, state/state code, county identifier/FIPS, candidate, party, candidate votes, total votes, `mode` and source/version metadata. MEDSL mode rule: use the `TOTAL` mode row where present; otherwise sum the available mode rows. Never sum a `TOTAL` row together with component mode rows. Claude reports 2024 has both `TOTAL` and mode rows, so naïve summation double-counts; 2024 is outside the selected 2000–2016 window.
- Exclude pollster free-text notes, respondent-level data, personal identifiers and all post-cutoff/post-election fields from the predictor package.
- **Coverage gate:** the selected draft window is 2000–2016: training 2000/2004/2008, validation 2012, held-out test 2016. The pinned `polls/pres_pollaverages_1968-2016.csv` is a publisher daily state-level averages file, not individual polls or sample sizes. 2020 and 2024 are outside this selected window; the uncorrected 2024 file must not be used. Use the latest same-state/office publisher average available on or before each 28/14/7-day cutoff, plus a separately labelled previous-election state-margin persistence baseline. Do not derive a sample-size-weighted 28-day poll mean from the averages file. The individual-poll option is not selected unless the owner explicitly asks Claude to try the live links.

- [x] Pin the FiveThirtyEight published-average file `polls/pres_pollaverages_1968-2016.csv` to commit `4c1ff5e3aef1816ae04af63218015066e186c147`; its per-file hash is in P2D PR #5. Claude reports the source/destination bytes and SHA-256 match. Do not fetch individual-poll files unless the owner explicitly asks Claude to try option-b live links.
- [x] The 2000–2016 draft window is selected under Claude's delegated design choice: train 2000/2004/2008, validate 2012, test 2016. The 2020 and 2024 files are out of scope; explicitly exclude the uncorrected 2024 general-average file. Any later window change requires a versioned protocol amendment before freeze.
- [ ] Record and retain the CC BY 4.0 attribution and licence text/version.
- [x] Owner approved the exact MEDSL mirror commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7` and file `data/medsl/countypres_2000-2024.csv`; Claude reports the 10,222,208-byte file SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`. The file remains in Claude's workspace only and must still be committed to the owner-controlled private repository.
- [x] Record the original MEDSL Dataverse citation, Version 20.0 and CC0 1.0 dataset licence. The mirror repository's MIT licence is for code only; it does not replace the dataset's CC0 licence.
- [ ] Commit the approved MEDSL mirror file, codebook and required attribution/manifest row to the owner-controlled private repository. Keep polling and returns as separate source assets; do not combine or aggregate them before the preregistered transformations are frozen.

## Package R — M5 Walmart retail sales

**Download location:** [Official M5 Forecasting — Accuracy data page](https://www.kaggle.com/c/m5-forecasting-accuracy/data). Review the competition rules before download/use.

**Expected fields to verify:**

- `sales_train_validation.csv`: item, department, category, store, state identifiers and daily unit-sales columns `d_1...`.
- `calendar.csv`: day ID, date, weekday, week, month, year, event name/type and SNAP indicators.
- `sell_prices.csv`: store, item, week and sell price.
- If retaining the protocol's reserved `d_1914`–`d_1941` window, include and pin `sales_train_evaluation.csv`; those days are not present in `sales_train_validation.csv`. Do not expose the reserve labels to scenario/model selection.
- Do not include submission-only identifiers or any target-window label as a feature. Verify exact headers and day/date mapping before freeze.

- [ ] Review the official M5 competition rules and licence/terms at https://www.kaggle.com/c/m5-forecasting-accuracy/data **before acquisition or use**. The protocol records the data as “Subject to Competition Rules”; do not assume unrestricted use or redistribution.
- [ ] If permitted for the intended evaluation, download the original files needed by the protocol, including `calendar.csv`, `sales_train_validation.csv` and `sell_prices.csv`.
- [ ] Preserve the source archive and original filenames. Do not commit raw data, hidden labels, submission files or derived copies to Git.
- [ ] Record the applicable rules/version, account/access conditions, source release, access date, citation and SHA-256 for every file.
- [ ] If the competition terms do not clearly permit the intended use, stop and request an owner-approved replacement; do not substitute Rossmann automatically.

## Package A — Ember Monthly EV Sales

**Download location:** [Ember Monthly EV Sales Data and methodology] (source file: 16-Nov-2026 snapshot, not the 18-Nov update) and owner-approved [GitHub mirror at pinned commit](https://github.com/Awes0mer/fuel-cars-pollution/tree/2c21f1edced7aae884314ebc28c89ab212f30563/data/raw/ember_ev_monthly).

**Expected fields to verify:** area, ISO 3 code, area type, date, frequency, drivetrain, aggregate-drivetrain flag, registrations, registrations YoY change and percentage, share of registrations, year-to-date registrations/share, rolling 12-month registrations/share. These are semantic field expectations; preserve the exact source headers and methodology version. Keep country/economy monthly rows separate from regional aggregates and quarterly observations.

- [x] Owner approved the exact Ember mirror commit `2c21f1edced7aae884314ebc28c89ab212f30563` and file `data/raw/ember_ev_monthly/monthly_ev_sales.csv`; Claude reports 7,695,642 bytes and SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`. This is the 16-Nov-2026 snapshot, not the 18-Nov update. The file remains in Claude's workspace only and must still be committed to the owner-controlled private repository.
- [x] Record the 16-Nov-2026 snapshot date, source URL and CC BY 4.0 licence. The mirror repository's MIT licence is for code only; it does not replace the dataset licence.
- [ ] Commit the approved Ember CSV and per-file manifest row to the owner-controlled private repository; preserve CC BY 4.0 attribution and underlying-country-source notes.
- [ ] Keep monthly rows distinct from quarterly rows; do not interpolate or combine them.
- [ ] Record a SHA-256 for each downloaded CSV and keep the exact release together.

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

Before any dataset import, the owner-controlled private data repository must contain a committed machine-readable manifest (CSV or JSON) with one row/object for **every** selected source file and at least: package, relative_path, original_filename, bytes, sha256, source_url, source_commit, publisher_release, licence_and_version, access_date and citation. P2D PR #5 stages a 12-row FiveThirtyEight `DATASET_MANIFEST.csv` on an unmerged branch; Claude reports source/destination byte and SHA-256 verification complete, and the 4,679-byte manifest file's own SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. This sub-manifest does not cover MEDSL, M5/Rossmann or Ember. Preserve per-file verification for every later transfer; do not substitute Git blob IDs, MD5 values or archive hashes for raw-file SHA-256. A missing file, blank hash, byte-count mismatch, unknown source revision or unresolved licence is a failed acquisition gate. No validation is authorized by this checklist.

### Blank per-file manifest rows for owner paste

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

1. Keep the source files in the owner-controlled private data repository, separate from AGORA. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to the AGORA source repository.
2. The current FiveThirtyEight handoff is 12 CSVs plus a per-file SHA-256 manifest on open/draft/unmerged P2D PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; the files remain absent from P2D main and Agora main. The per-file checks and manifest SHA-256 are recorded above.
3. M5 is the only remaining owner download/terms decision: acquire the exact Kaggle bundle after personal competition-terms review, or explicitly drop retail. The approved MEDSL and Ember mirror files must be committed with their hashes and licences to the owner-controlled private repository before the all-package manifest is complete.
4. The owner named ChatGPT as a separate-process evaluator, but the evaluator's restricted scope, output custody and label-release boundary are not established. Establish the restricted custody path before freeze.
5. The owner approved B=2000, bootstrap RNG seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on. These are owner-approved design values, effective only after they are merged into `VALIDATION_PROTOCOL.md` and the owner supplies a complete freeze sentence naming the actual manifest SHA. The received sentence used literal `<sha>` and is not effective.
6. The owner confirmed the synthetic-fixture Principal is acceptable for local public-data validation only; production CLI remains blocked/default-deny.
7. The owner's one-run approval is received but dormant. Do not use any dataset in a simulation or validation run until the protocol is frozen, the required implementation gates are satisfied, Claude has recorded M3 reached, and the separate run-approval preconditions are met.
8. Keep `VALIDATED_PREDICTION_ENABLED=False`; this checklist authorizes no acquisition, import, simulation, validation or write-back.

## Personal-data and data-minimisation gate

Before hashing/import handoff, inspect the exact headers and a small, controlled sample of rows locally. Record only the inspection outcome, not raw row values:

- [ ] No respondent-level, customer-level, driver-level or other directly identifying records are present.
- [ ] No names, emails, phone numbers, addresses, account IDs or precise personal-location fields are included.
- [ ] Free-text notes/comments are excluded unless a separately approved, documented necessity exists; default is exclude.
- [ ] No sensitive personal attributes or inferred sensitive traits are included.
- [ ] Any unexpected personal/sensitive field causes a stop and owner review; do not upload it to ChatGPT, GitHub or Notion.
- [ ] Retain only source metadata, schema/header allow-list, licence evidence, file size and SHA-256 in the dataset register.

**Important M5 split note:** the current protocol's `d_1914`–`d_1941` reserve requires `sales_train_evaluation.csv`. The owner/operator must reconcile this with the exact Kaggle files and competition terms before freezing the protocol.


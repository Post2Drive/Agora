# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation. For non-technical, owner-operated download steps, use [`DATASET_DOWNLOAD_GUIDE.md`](DATASET_DOWNLOAD_GUIDE.md); this checklist remains the source-of-record for approved source/version/hash and licence gates.

## FiveThirtyEight polls handoff — 23 November 2026 (P2D PR #5 branch inventory)

The private `Post2Drive/Post2Drive` main remains `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR [#5](https://github.com/Post2Drive/Post2Drive/pull/5) is still **open, draft and unmerged** at branch commit `17702622a7876e6c446ca87001983fe123662f42` on `data/import-fivethirtyeight-polls-2026-11-23`. The PR now contains 12 CSVs (94,181,506 bytes reported in the PR and import README) and `validation-data/elections/fivethirtyeight-polls/DATASET_MANIFEST.csv` with one per-file SHA-256 row for each CSV. The pinned source is FiveThirtyEight/data commit `4c1ff5e3aef1816ae04af63218015066e186c147`; the import README identifies CC BY 4.0 and includes the upstream licence text.

The manifest's Git blob identifier is `308dfbd4fec4de36ffe1bda9dd3d15ec88870f8b`; this is a Git object ID, **not** the manifest file's SHA-256. The manifest's own SHA-256 is not recorded in the repository. ChatGPT inspected only the manifest and import README metadata; no raw CSV bytes were downloaded or independently hash-verified. The PR remains unmerged, so these files are not in P2D main or Agora main (`4a0607f8946e32ef828b47183099ead4f8ae2bd7`).

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

The 2024 general-average file is explicitly **uncorrected** and must not be described or used as the corrected 2024 averages. The 12-row manifest does not by itself establish corrected-2024 or 2020 polling coverage, owner approval for use, or permission to run a benchmark. Keep the source commit, path, byte count, per-file SHA-256 and CC BY 4.0 licence tied to each row.

## Remaining package acquisition gates — 23 November 2026

- **FiveThirtyEight polls:** all 12 CSVs and their per-file manifest are now staged on open/draft/unmerged P2D PR #5 at `17702622a7876e6c446ca87001983fe123662f42`. The manifest is metadata evidence, not independent ChatGPT verification of raw bytes. The PR must be merged or otherwise owner-accepted, and source/destination SHA-256 and byte counts must be checked before use. Its 2024 general-average file is uncorrected; corrected 2024 coverage and 2020 coverage are not established by these 12 rows.
- **MEDSL Version 20.0:** no CSV or codebook is present in either target repository. PR #5 says Harvard Dataverse requires a guestbook response; no response was submitted. Do not submit one without the owner's response. The third-party candidate remains unapproved.
- **M5 Walmart / Rossmann:** no retail files are present. M5 remains blocked on the owner's personal Kaggle competition-terms review; Rossmann was not selected.
- **Ember monthly EV:** no official Ember file is staged. The older third-party 16-Nov snapshot is not a substitute for the newer official source and remains unapproved.
- **Manifest gate:** the PR #5 manifest covers only the 12 FiveThirtyEight CSVs. The manifest file's own SHA-256 is not recorded, and a complete manifest for the election-return, retail and adoption packages does not exist. No third-party mirror is approved by inclusion in this checklist.

ChatGPT read only `DATASET_MANIFEST.csv` and `IMPORT-README.md` from the PR branch. No raw benchmark CSV bytes were downloaded, read, hashed or imported by ChatGPT. No dataset, simulation or validation run is authorized.

## Important distinction

There are **three benchmark packages, not three individual files**:

- Package E is a paired election benchmark with polling and election-return sources.
- Package R is a multi-file M5 retail bundle.
- Package A is an Ember monthly EV dataset.

Keep original source filenames and archive structure until the source release, licence and SHA-256 values have been recorded. Do not commit raw benchmark data or derived label files to this repository.

## Package E — election polls and county returns

**Download locations:** [FiveThirtyEight polls data](https://github.com/fivethirtyeight/data/tree/master/polls) and [MEDSL County Presidential Election Returns 2000–2024, Dataverse DOI](https://doi.org/10.7910/DVN/VOQCHQ).

**Expected fields to verify against the exact downloaded headers (names below are semantic fields, not guaranteed literal column names):**

- Poll file(s): poll ID, pollster, state/geography, start/end date, sample size, population type, candidate, candidate percentage, mode and any source-defined poll-quality metadata used by the frozen mapping.
- Results file: election year, state/state code, county identifier/FIPS, candidate, party, candidate votes, total votes and source/version metadata.
- Exclude pollster free-text notes, respondent-level data, personal identifiers and all post-cutoff/post-election fields from the predictor package.
- **Coverage gate:** verify the pinned FiveThirtyEight release contains the required 2020 material and adequate corrected 2024 pre-election poll coverage before retaining the current validation/held-out split. If a required live URL fails, record it and stop; do not use the uncorrected 2024 file or a mirror. The owner delegated the design choice to prepare a separate 2000–2016 preregistration if the corrected 2024 general asset is unavailable after its single prescribed live-URL attempt. This is not a frozen protocol or run approval: version the draft protocol, retain the full-window design as a distinct option, and obtain explicit protocol-freeze approval before any run. Do not silently narrow, substitute the uncorrected file or use a mirror.

- [ ] Download the relevant FiveThirtyEight presidential general-election poll data from https://github.com/fivethirtyeight/data/tree/master/polls.
- [ ] Pin the full FiveThirtyEight commit and exact source URLs, filenames and releases for the 2020 and corrected 2024 poll/average files. Try each of the four README live URLs once and record success/failure, exact filename, bytes and SHA-256; do not retry via alternate URLs or mirrors. If corrected 2024 is unavailable, say so plainly and stop. Any proposed 2000–2016 polling-window narrowing requires explicit owner approval and a Claude amendment to the draft protocol before protocol freeze.
- [ ] Record and retain the CC BY 4.0 attribution and licence text/version.
- [ ] Download MIT Election Data and Science Lab, **County Presidential Election Returns 2000–2024**, Harvard Dataverse DOI https://doi.org/10.7910/DVN/VOQCHQ, Version 20.0.
- [ ] Record the Dataverse citation, CC0 1.0 licence, version, access date and exact downloaded filename.
- [ ] Keep the polling and returns files as separate source assets; do not combine or aggregate them before the preregistered transformations are frozen.

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

**Download location:** [Ember Monthly EV Sales Data and methodology](https://ember-energy.org/data/monthly-ev-sales-data/).

**Expected fields to verify:** area, ISO 3 code, area type, date, frequency, drivetrain, aggregate-drivetrain flag, registrations, registrations YoY change and percentage, share of registrations, year-to-date registrations/share, rolling 12-month registrations/share. These are semantic field expectations; preserve the exact source headers and methodology version. Keep country/economy monthly rows separate from regional aggregates and quarterly observations.

- [ ] Download the monthly CSV export(s) from https://ember-energy.org/data/monthly-ev-sales-data/.
- [ ] Record the Ember release/publication date, methodology version, source URL, access date and original filenames.
- [ ] Preserve CC BY 4.0 attribution and the relevant underlying-country-source notes.
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

Before any dataset import, the owner-controlled private data repository must contain a committed machine-readable manifest (CSV or JSON) with one row/object for **every** selected source file and at least: package, relative_path, original_filename, bytes, sha256, source_url, source_commit, publisher_release, licence_and_version, access_date and citation. P2D PR #5 currently stages a 12-row FiveThirtyEight `DATASET_MANIFEST.csv` on an unmerged branch; it does not cover MEDSL, M5/Rossmann or Ember. Verify source and destination byte counts and per-file SHA-256 after transfer; do not substitute Git blob IDs, MD5 values or archive hashes. Record a separate SHA-256 for the manifest file itself because the Git blob ID is not that digest. A missing file, blank hash, byte-count mismatch, unknown source revision or unresolved licence is a failed acquisition gate. No validation is authorized by this checklist.

### Blank per-file manifest rows for owner paste

| package | repository / branch | relative_path | bytes | sha256 | source commit / release | licence / version |
|---|---|---|---:|---|---|---|
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
|  |  |  |  |  |  |
|  |  |  |  |  |  |

For all 12 FiveThirtyEight files now listed in P2D PR #5, Claude/owner should compare the manifest's SHA-256 and byte count with the exact source and committed destination bytes before accepting the package. Use `Get-FileHash -LiteralPath <exact path> -Algorithm SHA256` and `Get-Item -LiteralPath <exact path> | Select-Object FullName,Length` locally for each row. ChatGPT did not run these commands or inspect raw CSV bytes. Add separate rows for every owner-approved MEDSL, retail and Ember file; do not put Git blob IDs or the MEDSL candidate MD5 in the SHA-256 column.

## Handoff and stop conditions

1. Keep the source files in the owner-controlled private data repository, separate from AGORA. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to the AGORA source repository.
2. The current FiveThirtyEight handoff is 12 CSVs plus a per-file SHA-256 manifest on open/draft/unmerged P2D PR #5 at `17702622a7876e6c446ca87001983fe123662f42`; the files remain absent from P2D main and Agora main. ChatGPT inspected manifest metadata only, not raw CSV bytes. The manifest file's own SHA-256 is not recorded.
3. Supply the exact election-return, retail and adoption files, immutable source releases, byte sizes, SHA-256 values and licence evidence. M5 remains blocked on the owner's Kaggle terms review.
4. The owner named ChatGPT as a separate-process evaluator, but the evaluator's restricted scope, output custody and label-release boundary are not established. Establish the restricted custody path before freeze.
5. The owner approved B=2000, bootstrap RNG seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on. These are owner-approved design values, effective only after they are merged into `VALIDATION_PROTOCOL.md` and the owner supplies a complete freeze sentence naming the actual manifest SHA. The received sentence used literal `<sha>` and is not effective.
6. The owner confirmed the synthetic-fixture Principal is acceptable for local public-data validation only; production CLI remains blocked/default-deny.
7. The owner's one-run approval is received but dormant. Do not import or run any dataset until the protocol is frozen, the required implementation gates are satisfied, Claude has recorded M3 reached, and the separate run-approval preconditions are met.
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

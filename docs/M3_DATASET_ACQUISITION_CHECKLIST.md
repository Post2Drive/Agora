# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation. For non-technical, owner-operated download steps, use [`DATASET_DOWNLOAD_GUIDE.md`](DATASET_DOWNLOAD_GUIDE.md); this checklist remains the source-of-record for approved source/version/hash and licence gates.

## FiveThirtyEight polls handoff — 23 November 2026 (read-only GitHub tree inventory of P2D PR #5)

The private `Post2Drive/Post2Drive` repository main is `5c8787a410a1aacaa9be9933b1c725a0b12e9689`. FiveThirtyEight import PR #5 remains open/unmerged at branch commit `15c9a053291925813ef568466a92fc5460f6b554`; the import branch is `data/import-fivethirtyeight-polls-2026-11-23`. The eight CSVs below exist only on the PR branch at `validation-data/elections/fivethirtyeight-polls/old_model/`; they are not in P2D main or Agora main (`4a0607f8946e32ef828b47183099ead4f8ae2bd7`). The PR also includes README/licence/import notes. These paths and byte sizes were read from the Git tree; no raw file contents were downloaded. Git blob IDs are not SHA-256 file checksums.

| File path in Post2Drive/Post2Drive PR #5 | Bytes | SHA-256 recorded in repo? |
|---|---:|---|
| `validation-data/elections/fivethirtyeight-polls/old_model/2024_presidential_primary_averages_old_model.csv` | 23,289 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/donald_trump_favorability_old_model.csv` | 82,705 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/generic_ballot_averages_old_model.csv` | 229,659 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/joe_biden_approval_old_model.csv` | 105,827 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/kamala_harris_approval_old_model.csv` | 84,376 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/mike_pence_favorability_old_model.csv` | 46,274 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/nikki_haley_favorability_old_model.csv` | 23,681 | No |
| `validation-data/elections/fivethirtyeight-polls/old_model/ron_desantis_favorability_old_model.csv` | 48,231 | No |

The eight CSVs total 644,042 bytes. The P2D PR #5 import README states CC BY 4.0 and the PR includes the upstream licence text. This is still an unmerged partial handoff, not a completed dataset package.

Four additional FiveThirtyEight files are missing from PR #5 and both repositories. The byte counts below are upstream-reported values from the import README, not measured destination sizes; none has a SHA-256 recorded:

| Missing upstream-relative path | Reported bytes | SHA-256 recorded? |
|---|---:|---|
| `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1,604,311 | No |
| `polls/2024-averages/presidential_primary_averages_2024.csv` | 11,407,331 | No |
| `polls/pres_pollaverages_1968-2016.csv` | 50,438,309 | No |
| `polls/pres_primary_avgs_1980-2016.csv` | 30,087,513 | No |

The uncorrected 2024 general file is not a substitute for corrected 2024 averages. Other 2020 polling files are linked in the import README but were not imported. No raw benchmark files are in Agora main.

**Other packages, repository presence and hashes:**

- **MEDSL V20:** no CSV or codebook in P2D main, P2D PR #5 changed-file set or Agora main. External candidate only: `mathis-group/cas-201-data-project` commit `1358bc6047f0c22989d37fa64ac03ee755bd17e`, `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes) plus codebook. Not present in either target repository. The candidate has MD5 `bd6661282936006b4ef4f5ee71418f3e` only, not SHA-256; source licence recorded as CC0 1.0. Not owner-approved.
- **M5 Walmart / Rossmann:** no `calendar.csv`, `sales_train_validation.csv`, `sell_prices.csv`, `sales_train_evaluation.csv` or Rossmann files in either target repository. No hashes. M5 remains blocked on the owner's Kaggle competition-terms review.
- **Ember monthly EV:** no Ember file in either target repository. External candidate only: `Awes0mer/fuel-cars-pollution` commit `2c21f1edced7aae884314ebc28c89ab212f30563`, `data/raw/ember_ev_monthly/monthly_ev_sales.csv` (7,695,642 bytes). SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2` is recorded in Agora docs for this external 16-Nov candidate snapshot, not a file in either target repository; the official Ember source had a newer 18-Nov update. Candidate CC BY 4.0; not owner-approved.

No per-file SHA-256 is recorded for the eight present FiveThirtyEight CSVs or four missing files; the MEDSL candidate has MD5 only; no M5/Rossmann files or hashes exist; the only SHA-256 in the docs is for the external Ember candidate, not a target-repository file.

## Claude reachability check — 23 November 2026, 09:05 IST (latest direct host check; owner-log recheck at 16:42 IST)

Claude's 09:05 IST reachability check reports FiveThirtyEight GitHub reachable, while Harvard Dataverse, Kaggle and Ember's official host were blocked by the workspace allowlist. No files were downloaded during that direct check. The owner shared the FiveThirtyEight polls folder listing at 15:40 IST and relayed a partial private-repository import at 16:31 IST; four large CSVs remain outstanding and no per-file SHA-256 manifest is recorded. Claude's 16:42 IST round reports no additional files or owner decisions. The 09:05 check remains the only direct host-reachability test; later log entries are handoff/status reports, not a new network test or source approval. The following GitHub-hosted snapshots are **candidates for owner approval only**, not approved substitutions:

| Package | Candidate route and evidence | Access status / caveat |
|---|---|---|
| E polls | Official [FiveThirtyEight/data](https://github.com/fivethirtyeight/data) at full commit `4c1ff5e3aef1816ae04af63218015066e186c147` (repository licence CC BY 4.0). The owner-shared listing contains `polls/pres_pollaverages_1968-2016.csv`, `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv`, and `polls/2024-averages/presidential_primary_averages_2024.csv`. The pinned README lists the four live current/historical poll, 2020 average and corrected 2024 average URLs documented in `DATASET_DOWNLOAD_GUIDE.md`. | Partial owner-reported import is recorded above; four large CSVs remain outstanding, and corrected 2024 coverage plus the SHA-256 manifest are not established. Owner must complete the exact-file handoff and hash checks before use. The GitHub 1968–2016 file does not supply 2020/2024 coverage; the 2024 general-average file is explicitly **uncorrected** and must not be substituted. If required 2020/corrected-2024 assets are unavailable, stop. If the corrected 2024 general asset is unavailable after its single prescribed live-URL attempt, the owner-delegated design choice is to prepare a separate versioned 2000–2016 preregistration with a fixed split. This is a proposed protocol amendment, not a frozen dataset scope or run authorization; do not silently narrow, substitute the uncorrected file or use a mirror. The protocol still requires explicit owner freeze before any run. No mirror is approved. |
| E returns | Third-party GitHub candidate [mathis-group/cas-201-data-project](https://github.com/mathis-group/cas-201-data-project) at commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7`: `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes) and `data/medsl/codebook.md`. Its `data/README.md` records 94,151 rows, MD5 `bd6661282936006b4ef4f5ee71418f3e` (claimed to match Dataverse), V20 released 2026-02-25, original format/unmodified, CC0 1.0; source DOI 10.7910/DVN/VOQCHQ. | GitHub candidate; not an official MEDSL-hosted mirror. Owner must approve this exact repository/commit/path. Verify the downloaded MD5 and SHA-256 against the owner-approved V20 source record and reconcile the codebook before acceptance. The repo's MIT code licence does not replace the data's separately stated CC0 source licence; the mirror's checksum statement is not independently verified here. |
| R — M5 | Official [Kaggle M5 data page](https://www.kaggle.com/c/m5-forecasting-accuracy/data). | Owner-supplied; requires Kaggle access and review/acceptance of competition terms. No third-party mirror is recommended. |
| A — Ember | Third-party GitHub candidate [Awes0mer/fuel-cars-pollution](https://github.com/Awes0mer/fuel-cars-pollution) at commit `2c21f1edced7aae884314ebc28c89ab212f30563`, file `data/raw/ember_ev_monthly/monthly_ev_sales.csv`. Its manifest records source URL `https://files.ember-energy.org/public-downloads/transport/outputs/monthly_ev_sales.csv`, retrieval 2026-11-16 05:54:52 UTC, 7,695,642 bytes, SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`; `fcp/sources.py` records CC BY 4.0 and the official source URL. The repo MIT licence covers code; its LICENSE says `data/raw` files retain publisher licences. | GitHub candidate, not an official Ember-hosted mirror. This is a 16-Nov snapshot; Claude reports Ember's official page had a newer update on 18-Nov-2026. Do not treat it as the latest release or silently replace the official 18-Nov source. Owner must approve this exact snapshot/version or supply the newer official file; verify its SHA-256 against the official source before acceptance. |

No mirror is approved by inclusion in this checklist. Claude must not download or use any candidate until the owner approves the exact repository, commit, path, version and licence evidence. The owner-operated handoff is a separate private GitHub repository (suggested name `agora-validation-data`) kept separate from AGORA and from ChatGPT/Notion; follow `DATASET_DOWNLOAD_GUIDE.md`. The owner may instead retain official source files locally until an approved handoff is available.

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

Before any dataset import, create and commit a machine-readable manifest (CSV or JSON) in the separate private data repository. It must contain one row/object for **every** source file, including every file in a multi-file bundle and all four outstanding FiveThirtyEight files, with at least these fields: package, relative_path, original_filename (file), bytes, sha256, source_url, source_commit, publisher_release, licence_and_version, access_date, and citation. The SHA-256 must be a 64-character lowercase hexadecimal digest of that exact file's downloaded bytes. Calculate SHA-256 from the final downloaded bytes (for example, Get-FileHash -Algorithm SHA256 on Windows); do not substitute Git blob IDs, MD5 values, or a hash of an archive for the hash of each extracted file. Recompute after transfer and compare source and destination hashes. A missing file, blank hash, byte-count mismatch, unknown source revision or unresolved licence is a failed acquisition gate. The manifest itself must be committed before any import or run; no validation is authorized by this checklist.

## Handoff and stop conditions

1. Keep the source files in the owner-controlled private data repository, separate from AGORA. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to the AGORA source repository.
2. The only current in-repository dataset files are eight FiveThirtyEight old-model CSVs on unmerged P2D PR #5; exact paths, Git-tree byte sizes and no-SHA status are listed above. Four large poll files are missing from P2D PR #5 and both main trees.
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

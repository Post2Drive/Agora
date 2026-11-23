# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation. For non-technical, owner-operated download steps, use [`DATASET_DOWNLOAD_GUIDE.md`](DATASET_DOWNLOAD_GUIDE.md); this checklist remains the source-of-record for approved source/version/hash and licence gates.

## Claude reachability check — 23 November 2026, 09:05 IST (latest direct host check; owner-log recheck at 16:42 IST)

Claude's 09:05 IST check reports GitHub reachable, while Harvard Dataverse, Kaggle and Ember's official host are blocked by the current network allowlist. No files were downloaded during that check. The owner shared the FiveThirtyEight `polls/` folder listing at 15:40 IST and relayed a partial private-repository import at 16:31 IST; this does not change the 09:05 host-reachability result. The latest 16:42 IST Claude round records no additional files or owner decisions. The following GitHub-hosted snapshots are **candidates for owner approval only**, not approved substitutions:

| Package | Candidate route and evidence | Access status / caveat |
|---|---|---|
| E polls | Official [FiveThirtyEight/data](https://github.com/fivethirtyeight/data) at full commit `4c1ff5e3aef1816ae04af63218015066e186c147` (repository licence CC BY 4.0). The owner-shared listing contains `polls/pres_pollaverages_1968-2016.csv`, `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv`, and `polls/2024-averages/presidential_primary_averages_2024.csv`. The pinned README lists the four live current/historical poll, 2020 average and corrected 2024 average URLs documented in `DATASET_DOWNLOAD_GUIDE.md`. | No files are in hand. Owner should try each live URL once and report failures. The GitHub 1968–2016 file does not supply 2020/2024 coverage; the 2024 general-average file is explicitly **uncorrected** and must not be substituted. If required 2020/corrected-2024 assets are unavailable, stop. Narrowing the polling test window to 2000–2016 requires explicit owner approval and a Claude protocol amendment before separate protocol-freeze approval; no such approval is recorded. No mirror is approved. |
| E returns | Third-party GitHub candidate [mathis-group/cas-201-data-project](https://github.com/mathis-group/cas-201-data-project) at commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7`: `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes) and `data/medsl/codebook.md`. Its `data/README.md` records 94,151 rows, MD5 `bd6661282936006b4ef4f5ee71418f3e` (claimed to match Dataverse), V20 released 2026-02-25, original format/unmodified, CC0 1.0; source DOI 10.7910/DVN/VOQCHQ. | GitHub candidate; not an official MEDSL-hosted mirror. Owner must approve this exact repository/commit/path. Verify the downloaded MD5 and SHA-256 against the owner-approved V20 source record and reconcile the codebook before acceptance. The repo's MIT code licence does not replace the data's separately stated CC0 source licence; the mirror's checksum statement is not independently verified here. |
| R — M5 | Official [Kaggle M5 data page](https://www.kaggle.com/c/m5-forecasting-accuracy/data). | Owner-supplied; requires Kaggle access and review/acceptance of competition terms. No third-party mirror is recommended. |
| A — Ember | Third-party GitHub candidate [Awes0mer/fuel-cars-pollution](https://github.com/Awes0mer/fuel-cars-pollution) at commit `2c21f1edced7aae884314ebc28c89ab212f30563`, file `data/raw/ember_ev_monthly/monthly_ev_sales.csv`. Its manifest records source URL `https://files.ember-energy.org/public-downloads/transport/outputs/monthly_ev_sales.csv`, retrieval 2026-11-16 05:54:52 UTC, 7,695,642 bytes, SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`; `fcp/sources.py` records CC BY 4.0 and the official source URL. The repo MIT licence covers code; its LICENSE says `data/raw` files retain publisher licences. | GitHub candidate, not an official Ember-hosted mirror. This is a 16-Nov snapshot; Claude reports Ember's official page had a newer update on 18-Nov-2026. Do not treat it as the latest release or silently replace the official 18-Nov source. Owner must approve this exact snapshot/version or supply the newer official file; verify its SHA-256 against the official source before acceptance. |

No mirror is approved by inclusion in this checklist. Claude must not download or use any candidate until the owner approves the exact repository, commit, path, version and licence evidence. The owner-operated handoff is a separate private GitHub repository kept separate from AGORA and from ChatGPT/Notion; follow `DATASET_DOWNLOAD_GUIDE.md`. The owner-reported FiveThirtyEight partial import is recorded below, but it is not accepted as complete until every required file has an exact per-file SHA-256 manifest committed in that private repository.

## Owner-reported private-repository handoff — 23 November 2026, 16:31 IST

This status is relayed from the collaboration log and has **not** been independently verified against the private repository. The owner reported a partial FiveThirtyEight import into private repository `Post2Drive/Post2Drive`, branch `data/import-fivethirtyeight-polls-2026-11-23`, PR #5, import commit `15c9a053`; the pinned FiveThirtyEight source commit is `4c1ff5e3aef1816ae04af63218015066e186c147`. The `old_model/` folder and polls README were reported present. Four files remained outstanding and no SHA-256 values were recorded:

| Owner-reported file | Approximate size | Status at 16:31 IST |
|---|---:|---|
| 2024 general averages CSV | 1.6 MB | Outstanding; verify this is the corrected general-election release, not the uncorrected file |
| 2024 primary averages CSV | 11.4 MB | Outstanding; preserve as a distinct primary-election asset |
| Presidential averages 1968–2016 CSV | 50.4 MB | Outstanding; exact original filename/version must be recorded |
| Primary averages 1980–2016 CSV | 30.1 MB | Outstanding; exact original filename/version must be recorded |

The reported import commit `15c9a053` is the private-repository handoff commit, not the FiveThirtyEight source commit. Preserve both identities separately. Record exact original filenames, byte sizes and full SHA-256 values after the files are pushed. ChatGPT has not accessed the private repository, downloaded or read dataset bytes, or verified the reported file contents. The four-file list is not an acceptance decision: the corrected 2024 general file must be confirmed, and the uncorrected 2024 file remains prohibited as a substitute.

## Required per-file SHA-256 manifest — hard pre-run gate

Commit one manifest in the owner-controlled private data repository before any dataset import, simulation or validation. Every file, including each of the four outstanding polls files, must have all of these fields:

| Manifest field | Required value |
|---|---|
| `file` | Exact original filename and relative path in the private repository |
| `bytes` | Exact integer byte length of the original file (not rounded MB) |
| `sha256` | Full SHA-256 digest of those exact bytes |
| `source_commit` | Full immutable Git source commit for GitHub assets; for non-Git publishers record `N/A — non-Git source` and the exact publisher release/version/DOI in the release field |
| `licence` | Exact licence name/version or competition-rules reference applying to that file |
| `source_url` | Canonical publisher URL or DOI |
| `release` | Immutable release/version and access date |
| `citation` | Required attribution/citation text |

No dataset run before the complete manifest is committed in the private repository and reconciled against the owner-approved source, file list, split and licence. A private-repository commit is not itself permission to import or run.

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
- **Coverage gate:** retain the full 2020/2024 window only if all four owner-required poll files arrive with exact filenames, byte sizes, SHA-256 values, source commit and licence evidence, and the 2024 general file is confirmed corrected. If the corrected 2024 general asset is unavailable after its single prescribed live-URL attempt, use the owner-delegated 2000–2016 fallback only in a separately versioned preregistration with a fixed 2000/2004/2008 training, 2012 validation and 2016 held-out test split. Do not silently narrow, use the uncorrected 2024 file or substitute a mirror. The fallback still requires its own complete source manifest and explicit protocol freeze before any run.

- [ ] Download the relevant FiveThirtyEight presidential general-election poll data from https://github.com/fivethirtyeight/data/tree/master/polls.
- [ ] Pin the full FiveThirtyEight source commit and exact source URLs, filenames and releases for every poll/average file. Try each of the four README live URLs once and record success/failure, exact filename, bytes and SHA-256. If the corrected 2024 general asset is unavailable, record the failure and use the owner-delegated 2000–2016 fallback only through a separate versioned preregistration with its own exact split and file manifest; do not silently narrow, use the uncorrected file or use a mirror. The amended protocol still requires explicit owner freeze before any run.
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
| Release / version | Exact release, commit or Dataverse version |
| Source commit | Full immutable source commit for GitHub files; for non-Git sources record N/A and pin the publisher release/version/DOI |
| Access date | Local date downloaded |
| Original filename | Do not rename before hashing |
| File size | Bytes |
| SHA-256 | Hash of the exact downloaded bytes |
| Intended split / role | As preregistered; never infer from filename |

## Handoff and stop conditions

1. Owner downloads the exact publisher files manually, retains the source archives and licence evidence, and completes the per-file register for every file: exact source/release or source commit, licence/citation, access date, original filename, byte size and SHA-256. Commit the complete manifest to the separate private repository before any import, simulation or validation run.
2. After owner review of the exact sources and terms, push only the approved, licence-permitted files to a separate **private** GitHub repository (suggested name `agora-validation-data`) using the steps in `DATASET_DOWNLOAD_GUIDE.md`. Keep it separate from the AGORA source repository.
3. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to AGORA. Do not include credentials, personal/customer/driver data or unrelated files. Claude receives read access only through the owner's GitHub authorization; never send passwords, tokens or cookies in chat.
4. **M5 gate:** do not push M5 files until the owner has personally reviewed the Kaggle competition terms and confirmed the private collaborator handoff is permitted. If unclear, leave M5 local and stop.
5. Before any import, reconcile the owner-approved files against the dataset register and the field allow-lists/time splits in `VALIDATION_PROTOCOL.md`. The private-repository handoff is not approval to import.
6. **No validation run yet:** the owner selected the synthetic-fixture Principal for local validation on public datasets only, but the direct-engine opaque receipt is not implemented. The production CLI policy source `_governed_policy()` still returns `None`, so the policy-required builder denies governed input before opening snapshot bytes. Do not bypass this guard or inject a permissive policy.
7. Validation also requires the complete per-file manifest committed in the private repository, the direct-engine receipt and TOCTOU hardening to be implemented/reviewed, and explicit owner approval to freeze the protocol in a merged docs commit. Dataset availability alone is not authorization to run.
8. Keep `VALIDATED_PREDICTION_ENABLED=False`; report any future outputs as exploratory simulations, not observed demand or validated predictions.

## Personal-data and data-minimisation gate

Before hashing/import handoff, inspect the exact headers and a small, controlled sample of rows locally. Record only the inspection outcome, not raw row values:

- [ ] No respondent-level, customer-level, driver-level or other directly identifying records are present.
- [ ] No names, emails, phone numbers, addresses, account IDs or precise personal-location fields are included.
- [ ] Free-text notes/comments are excluded unless a separately approved, documented necessity exists; default is exclude.
- [ ] No sensitive personal attributes or inferred sensitive traits are included.
- [ ] Any unexpected personal/sensitive field causes a stop and owner review; do not upload it to ChatGPT, GitHub or Notion.
- [ ] Retain only source metadata, schema/header allow-list, licence evidence, file size and SHA-256 in the dataset register.

**Important M5 split note:** the current protocol's `d_1914`–`d_1941` reserve requires `sales_train_evaluation.csv`. The owner/operator must reconcile this with the exact Kaggle files and competition terms before freezing the protocol.

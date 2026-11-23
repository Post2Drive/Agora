# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation.

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
- **Coverage gate:** verify the pinned FiveThirtyEight release contains adequate 2024 pre-election poll coverage before selecting the 2024 held-out cycle. If not, stop and request a new owner-approved protocol; do not quietly replace the source or election cycle.

- [ ] Download the relevant FiveThirtyEight presidential general-election poll data from https://github.com/fivethirtyeight/data/tree/master/polls.
- [ ] Pin the exact repository commit/release and the exact 2020 and 2024 poll file(s) used. Preserve the original filenames.
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
| Access date | Local date downloaded |
| Original filename | Do not rename before hashing |
| File size | Bytes |
| SHA-256 | Hash of the exact downloaded bytes |
| Intended split / role | As preregistered; never infer from filename |

## Handoff and stop conditions

1. Owner downloads the files manually and retains the source archives and licence evidence.
2. Provide the files through the approved local file workflow; do not provide credentials or grant AGORA network access.
3. Keep the files outside the repository. No raw data is to be committed.
4. Before import, the owner and operator reconcile the files against the dataset register and the field allow-lists/time splits in `VALIDATION_PROTOCOL.md`.
5. **No validation run yet:** the current CLI policy source `_governed_policy()` returns `None` because a production identity adapter is not implemented. The policy-required builder therefore denies governed input before opening snapshot bytes. Do not bypass this guard or inject a permissive policy.
6. Validation also requires explicit owner approval to freeze the protocol in a merged docs commit. Dataset availability alone is not authorization to run.
7. Keep `VALIDATED_PREDICTION_ENABLED=False`; report any future outputs as exploratory simulations, not observed demand or validated predictions.


## Personal-data and data-minimisation gate

Before hashing/import handoff, inspect the exact headers and a small, controlled sample of rows locally. Record only the inspection outcome, not raw row values:

- [ ] No respondent-level, customer-level, driver-level or other directly identifying records are present.
- [ ] No names, emails, phone numbers, addresses, account IDs or precise personal-location fields are included.
- [ ] Free-text notes/comments are excluded unless a separately approved, documented necessity exists; default is exclude.
- [ ] No sensitive personal attributes or inferred sensitive traits are included.
- [ ] Any unexpected personal/sensitive field causes a stop and owner review; do not upload it to ChatGPT, GitHub or Notion.
- [ ] Retain only source metadata, schema/header allow-list, licence evidence, file size and SHA-256 in the dataset register.

**Important M5 split note:** the current protocol's `d_1914`–`d_1941` reserve requires `sales_train_evaluation.csv`. The owner/operator must reconcile this with the exact Kaggle files and competition terms before freezing the protocol.

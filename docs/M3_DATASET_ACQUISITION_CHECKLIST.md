# M3 Dataset Acquisition Checklist

**Purpose:** prepare the three public benchmark packages named in `VALIDATION_PROTOCOL.md`. This is an acquisition checklist only. It does not authorize importing data into AGORA, launching a simulation, or beginning validation.

## Important distinction

There are **three benchmark packages, not three individual files**:

- Package E is a paired election benchmark with polling and election-return sources.
- Package R is a multi-file M5 retail bundle.
- Package A is an Ember monthly EV dataset.

Keep original source filenames and archive structure until the source release, licence and SHA-256 values have been recorded. Do not commit raw benchmark data or derived label files to this repository.

## Package E — election polls and county returns

- [ ] Download the relevant FiveThirtyEight presidential general-election poll data from https://github.com/fivethirtyeight/data/tree/master/polls.
- [ ] Pin the exact repository commit/release and the exact 2020 and 2024 poll file(s) used. Preserve the original filenames.
- [ ] Record and retain the CC BY 4.0 attribution and licence text/version.
- [ ] Download MIT Election Data and Science Lab, **County Presidential Election Returns 2000–2024**, Harvard Dataverse DOI https://doi.org/10.7910/DVN/VOQCHQ, Version 20.0.
- [ ] Record the Dataverse citation, CC0 1.0 licence, version, access date and exact downloaded filename.
- [ ] Keep the polling and returns files as separate source assets; do not combine or aggregate them before the preregistered transformations are frozen.

## Package R — M5 Walmart retail sales

- [ ] Review the official M5 competition rules and licence/terms at https://www.kaggle.com/c/m5-forecasting-accuracy/data **before acquisition or use**. The protocol records the data as “Subject to Competition Rules”; do not assume unrestricted use or redistribution.
- [ ] If permitted for the intended evaluation, download the original files needed by the protocol, including `calendar.csv`, `sales_train_validation.csv` and `sell_prices.csv`.
- [ ] Preserve the source archive and original filenames. Do not commit raw data, hidden labels, submission files or derived copies to Git.
- [ ] Record the applicable rules/version, account/access conditions, source release, access date, citation and SHA-256 for every file.
- [ ] If the competition terms do not clearly permit the intended use, stop and request an owner-approved replacement; do not substitute Rossmann automatically.

## Package A — Ember Monthly EV Sales

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

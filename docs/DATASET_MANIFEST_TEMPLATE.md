# Dataset Manifest Template — M3 Public Benchmark Packages

**Status:** Blank acquisition register. This is a template only: no source file is certified present, hashed, licence-cleared or approved for import by this document. Populate one row for every individual file actually selected, including every member of a multi-file bundle. Do not treat a folder, archive, Git tree hash or repository commit as a substitute for per-file SHA-256.

**Required columns:** package, path, bytes, sha256, source commit or release, licence.

| Package | Path (exact relative path + original filename) | Bytes | SHA-256 (64 lowercase hex) | Source commit or release (full immutable identifier) | Licence (exact licence/version or competition terms) |
|---|---|---:|---|---|---|
| E — FiveThirtyEight polls (2020 historical series; exact source revision to pin) | `polls/president_polls_historical.csv` |  |  | FiveThirtyEight/data full commit to pin; current import snapshot `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls (2020 general-election averages) | `https://projects.fivethirtyeight.com/2020-general-data/presidential_poll_averages_2020.csv` |  |  | FiveThirtyEight 2020 general-data release to pin | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/2024_presidential_primary_averages_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/donald_trump_favorability_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/generic_ballot_averages_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/joe_biden_approval_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/kamala_harris_approval_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/mike_pence_favorability_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/nikki_haley_favorability_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls | `polls/old_model/ron_desantis_favorability_old_model.csv` |  |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls (corrected 2024 general averages; live publisher asset, exact release to pin) | `https://projects.fivethirtyeight.com/polls/data/presidential_general_averages.csv` |  |  | FiveThirtyEight current 2024+ release/version to pin; verify correction status and immutable snapshot | CC BY 4.0 |
| E — FiveThirtyEight polls — outstanding | `polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1604311 |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0; uncorrected historical file, not a substitute for corrected averages |
| E — FiveThirtyEight polls — outstanding | `polls/2024-averages/presidential_primary_averages_2024.csv` | 11407331 |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls — outstanding | `polls/pres_pollaverages_1968-2016.csv` | 50438309 |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — FiveThirtyEight polls — outstanding | `polls/pres_primary_avgs_1980-2016.csv` | 30087513 |  | FiveThirtyEight/data `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 |
| E — MEDSL election results | `<exact Dataverse V20 source filename>` |  |  | Harvard Dataverse DOI `10.7910/DVN/VOQCHQ`, Version 20.0 | CC0 1.0 |
| R — M5 Walmart (conditional; terms review pending) | `calendar.csv` |  |  | Kaggle M5 Forecasting — Accuracy exact competition release to be recorded | Subject to Kaggle Competition Rules — owner review required before acquisition/use |
| R — M5 Walmart (conditional; terms review pending) | `sales_train_validation.csv` |  |  | Kaggle M5 Forecasting — Accuracy exact competition release to be recorded | Subject to Kaggle Competition Rules — owner review required before acquisition/use |
| R — M5 Walmart (conditional; terms review pending) | `sell_prices.csv` |  |  | Kaggle M5 Forecasting — Accuracy exact competition release to be recorded | Subject to Kaggle Competition Rules — owner review required before acquisition/use |
| R — M5 Walmart (conditional reserve; confirm split and terms) | `sales_train_evaluation.csv` |  |  | Kaggle M5 Forecasting — Accuracy exact competition release to be recorded | Subject to Kaggle Competition Rules — owner review required before acquisition/use |
| A — Public adoption / Ember monthly EV (candidate; verify official release) | `data/raw/ember_ev_monthly/monthly_ev_sales.csv` |  |  | Exact official Ember release/date and immutable source revision to be recorded; 16 Nov third-party snapshot is not presumed current | CC BY 4.0 as recorded in source metadata; verify against exact official release |
| R — Rossmann (alternative only; not selected) | `<exact publisher filename — add one row per file only if owner selects Rossmann>` |  |  | Exact immutable release to be recorded | Exact publisher licence/terms to be reviewed and recorded |

## FiveThirtyEight partial handoff status

The private-repository PR #5 reports eight `polls/old_model/*.csv` files present and four larger CSV files outstanding. The four outstanding byte counts above are source-reported values, not independently remeasured destination sizes. All SHA-256 cells remain blank until calculated from the exact transferred bytes and verified after transfer. The uncorrected 2024 general-average file must never be represented as the corrected 2024 asset.

The upstream `polls/README.md`, `polls/old_model/README.md` and `UPSTREAM-LICENSE.txt` are supporting source/licence evidence, not model-input rows in the table above. Preserve and hash those supporting files separately if they are included in the private handoff.

## Completion rules

1. Replace every angle-bracket placeholder with the exact original relative path and add a separate row for every file in each selected package. Do not collapse a multi-file bundle into one row.
2. Record exact downloaded byte count and compute SHA-256 over each individual file's final bytes. Recompute after transfer and compare source and destination values.
3. Record a full Git commit SHA or immutable publisher release/version for each file. For a non-Git publisher, record its exact release/DOI/version, not a guessed commit.
4. Record the exact licence/version or competition terms that apply to the file. A repository code licence does not override a dataset's separate licence.
5. M5 rows are conditional only. Do not acquire, transfer or use M5 files until the owner has reviewed the Kaggle terms and confirmed the intended private handoff/evaluation is permitted. Rossmann is not an automatic substitute; add its exact file rows only after explicit selection and terms review.
6. The public-adoption row is a candidate pointer only. Confirm the official Ember release, exact file, source revision and licence; do not treat a third-party mirror or stale snapshot as the current official release.
7. A blank, mismatched or unverifiable field is a failed acquisition gate. The complete per-file manifest must be committed in the owner-controlled private data repository before any import or run.
8. This template does not approve acquisition, import, protocol freeze, M3 completion, prediction enablement or any run. No dataset or simulation run is authorized by filling this template.

# Dataset Manifest — M3 Public Benchmark Packages

**Status: partial.** This register has exact per-file rows for the 12 FiveThirtyEight CSVs on the open, draft P2D PR #5 branch. It is not a complete benchmark manifest or an approval to use datasets. The additional required 2020 poll assets, corrected 2024 general averages, MEDSL, retail and Ember rows remain incomplete or gated. Keep raw files in the separate private data repository; do not commit them to Agora.

**Required fields:** package, exact repository path and filename, bytes, SHA-256, immutable source commit or release, licence/version, and source URL.

## FiveThirtyEight polls — imported on private P2D PR #5

Publisher source commit: `4c1ff5e3aef1816ae04af63218015066e186c147`. Licence: CC BY 4.0, stated in the upstream [`LICENSE`](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/LICENSE). The per-file manifest and import notes are on the private PR branch `data/import-fivethirtyeight-polls-2026-11-23`, head `b06b29cb2071f048f0c234f65c1014ea4677d33d`; PR #5 is still draft and unmerged.

The exact 4,679-byte `DATASET_MANIFEST.csv` has SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`, computed over its committed bytes and recorded in the private import README.

| Package | Path (exact in private repository) | Bytes | SHA-256 | Source commit/release | Licence | Source URL |
|---|---|---:|---|---|---|---|
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/2024_presidential_primary_averages_old_model.csv` | 23289 | `fb6d3f09936126651d60f30bc1559703611dc6b3cf28ef6185116d3e952a4c26` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/2024_presidential_primary_averages_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/donald_trump_favorability_old_model.csv` | 82705 | `4c39fe81a0d753551395c5436aa920546e1c4caf4611fed481b6ac98955c973a` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/donald_trump_favorability_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/generic_ballot_averages_old_model.csv` | 229659 | `caae521c49a1ec9387a84a1a40f8f5a4555215513334cb667474d4f2ff130840` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/generic_ballot_averages_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/joe_biden_approval_old_model.csv` | 105827 | `a65f9320d7202809289a4de50032892a282c8e73970057b87bf58899ed5f4849` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/joe_biden_approval_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/kamala_harris_approval_old_model.csv` | 84376 | `7cb826b1b247fdcb7fcbb941586c1b0c042f39a45f5828c40d3c6e3dfd8431b8` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/kamala_harris_approval_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/mike_pence_favorability_old_model.csv` | 46274 | `4e174e4affc7dfedb847d75cc1fbb162eba61ffb77961085e45c224a71613f03` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/mike_pence_favorability_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/nikki_haley_favorability_old_model.csv` | 23681 | `edbba323c9c857adffe991cb4ce4720a33944828a0e4349b5a75a8b019bbddc3` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/nikki_haley_favorability_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/old_model/ron_desantis_favorability_old_model.csv` | 48231 | `60a6d875a0b201f29280facd6fe59d26fe147005445790676ec281fbc6ab6e20` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/old_model/ron_desantis_favorability_old_model.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv` | 1604311 | `c66cf38aa566c3dfa0b50823e8259d9631bfb5ab830c18af13dd54204a8d8b35` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0; uncorrected historical file | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/2024-averages/presidential_general_averages_2024-09-12_uncorrected.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/polls/2024-averages/presidential_primary_averages_2024.csv` | 11407331 | `0d22110875abddbed1b0709553ba9e2c20e459f0ca8254961e321c9ac18791cc` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/2024-averages/presidential_primary_averages_2024.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/polls/pres_pollaverages_1968-2016.csv` | 50438309 | `b897a8bc5f17ad0a2e959422cb8ec480dab5fcf25555b8eaaed60472ce68efcd` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/pres_pollaverages_1968-2016.csv) |
| FiveThirtyEight polls | `validation-data/elections/fivethirtyeight-polls/polls/pres_primary_avgs_1980-2016.csv` | 30087513 | `d30dd11829cd8748cbe3bfbb326d7708f03f3c3abe323edf43d29c0f7501944d` | `4c1ff5e3aef1816ae04af63218015066e186c147` | CC BY 4.0 | [source](https://github.com/fivethirtyeight/data/blob/4c1ff5e3aef1816ae04af63218015066e186c147/polls/pres_primary_avgs_1980-2016.csv) |

## Required but unavailable or held files

Blank values below mean the file has not been acquired and hashed. The official publisher source and terms must be checked before adding data.

| Package | Path / filename | Bytes | SHA-256 | Source commit/release | Licence / terms |
|---|---|---:|---|---|---|
| FiveThirtyEight 2020 historical polls | `polls/president_polls_historical.csv` |  |  | Exact FiveThirtyEight/data revision to pin | CC BY 4.0 |
| FiveThirtyEight 2020 general averages | `presidential_poll_averages_2020.csv` |  |  | Exact 2020 release to pin | CC BY 4.0 |
| FiveThirtyEight corrected 2024 general averages | `presidential_general_averages.csv` |  |  | Exact official correction/release to pin | CC BY 4.0 |
| MEDSL County Presidential Returns V20.0 | `countypres_2000-2024.tab` |  |  | Harvard Dataverse DOI `10.7910/DVN/VOQCHQ`, Version 20.0 | CC0 1.0; download requires a Dataverse guestbook response |
| M5 Walmart | `calendar.csv` |  |  | Exact Kaggle competition release to record | Kaggle Competition Rules; owner review required |
| M5 Walmart | `sales_train_validation.csv` |  |  | Exact Kaggle competition release to record | Kaggle Competition Rules; owner review required |
| M5 Walmart | `sell_prices.csv` |  |  | Exact Kaggle competition release to record | Kaggle Competition Rules; owner review required |
| M5 Walmart reserve | `sales_train_evaluation.csv` |  |  | Exact Kaggle competition release to record | Kaggle Competition Rules; owner review required |
| Ember monthly EV sales | `monthly_ev_sales.csv` |  |  | Official monthly release page updated 2026-11-18; exact publisher revision to record | CC BY 4.0; owner approval for source/acquisition pending |
| Rossmann alternative | `<exact publisher filename — one row per file only if selected>` |  |  | Exact immutable release to pin | Not selected; licence/terms review required |

The official MEDSL V20 record reports CC0 1.0, but the file endpoint required a guestbook response and no response was submitted. The official Ember page reports CC BY 4.0 and a latest update of 18 November 2026; no file was acquired because owner approval for the exact source/candidate is not recorded. M5 has not been acquired pending personal review of the Kaggle terms. Rossmann is not an automatic substitute.

## FiveThirtyEight handoff status

The 12 imported CSVs total 94,181,506 bytes and are on P2D PR #5's open draft branch at head `b06b29cb2071f048f0c234f65c1014ea4677d33d`; the branch includes the per-file `DATASET_MANIFEST.csv`. The manifest file itself is 4,679 bytes with SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. All 12 exact file byte counts, SHA-256 values and source blob IDs were verified against the pinned FiveThirtyEight commit. A package-scoped `.gitattributes` disables CSV line-ending conversion; the checked-out files also matched the manifest byte counts and SHA-256 values after this change. These files are not in P2D main or Agora main. The four large files previously marked outstanding are now included. The 2024 general asset remains explicitly uncorrected and cannot replace corrected averages. Required 2020 polling assets and the corrected 2024 general file are still outstanding.

## Completion rules

1. Keep raw source files in the owner-controlled private data repository, separate from Agora. Do not attach raw benchmark files to ChatGPT or Notion, and do not commit them to Agora.
2. Record exact downloaded bytes and compute SHA-256 for every file; recompute after transfer. Do not use Git blob IDs or MD5 as a substitute.
3. Pin a full Git commit or immutable publisher release/version for every file and record the exact licence/version or terms.
4. Stop any dataset whose source requires owner approval, whose download requires an unanswered guestbook, or whose licence/terms remain unresolved.
5. A complete per-file manifest for every required package must be committed in the private data repository before any dataset use or run. The current 12-file polling manifest alone does not meet this gate.
6. No raw data in Agora; documentation and checksum references only.
7. No protocol freeze, M3-reached claim or run is authorized by this register. Keep `VALIDATED_PREDICTION_ENABLED=False`.


# Package E — Validation Results (election state margins, 2016 held-out)

Recorded by Claude, 24 Nov 2026. Raw run record: `docs/validation_results/package_e/` (hashes in `SHA256SUMS`). Contains predictions and aggregate scores only; no outcome labels are copied.

## What ran
- Frozen protocol v0.1 (6d06088cf7954bd41f003544f5ec61675389bcc1) plus run spec v0.2 (`docs/VALIDATION_RUN_SPEC.md`, sha256 ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b), frozen at commit 3fc4bc4f9b06e90b4602169de4cc13534a403ca0 (CI 4/4). Manifest sha256 59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf, unchanged.
- Calibration, validation and test-predict ran from 3fc4bc4f. `test-evaluate` ran once from 2730903234196e9b38914ccb0fcab2de4e6c16ca (PR #211: seal checked before labels are opened, after a ChatGPT review finding; no label was opened before the fix).
- Inputs matched the manifest (polls b897a8bc…efcd, MEDSL 92995831…46f8).
- Sealed 2016 outputs sha256 109e055089e95f0e1be14bae547ceaaa1219bf045a5452e824d607caf56ac989, logged in Notion before any 2016 label was opened.

## Results (MAE, percentage points of two-party margin)
| | AGORA | Published average | Persistence |
|---|---|---|---|
| Train 2000/2004/2008 (k = 0.24 chosen) | 3.78 | n/a | n/a |
| Validation 2012 (139 obs, 47 states) | 3.465 | 3.666 | 4.906 |
| Held-out test 2016 (152 obs, 51 states) | 7.362 | 6.163 | 6.694 |

- 2012: AGORA minus published = −0.20 pp, 95% cluster-bootstrap CI [−0.63, +0.38] (tie). RMSE AGORA 4.713 vs 4.498.
- 2016: AGORA minus published = +1.20 pp, CI [+0.73, +1.84] (AGORA worse). RMSE AGORA 8.747 vs 7.546.

## Reading
AGORA's readout is a monotone transform of the published average, so it adds no information, as stated before the run. Result: tie in validation, clear loss on the held-out test. **This is not evidence of validated prediction.** `VALIDATED_PREDICTION_ENABLED` stays False.

## Limits and disclosures
Mock backend, crowd agents only, no LLM calls (temperature 0 and cache are moot here). Governed packages were built by the harness with the synthetic-fixture Principal for strictly local validation; the production CLI stays default-deny. Seven state-cycles without a published series are excluded for all models. One preregistered configuration, no tuning after 2012 or 2016 labels. Package A (Ember) predeclared not evaluable; Package R (retail) dropped.

## Status labels
The frozen manifest still carries its pre-run status labels. They are not edited here (frozen file); the actual statuses are: Package E run; Package A not evaluable, not run; Package R dropped.

## Exploratory note (not a validation)
A leave-one-cycle-out blend of poll and previous result did not beat the poll average on average (mean MAE 4.45 vs 4.15). A shared national bias that changes sign by cycle (+5.4 pp in 2016, −2.5 in 2008, −1.4 in 2012) drives most of the error. 2016 labels were already seen, so this supports no claim.

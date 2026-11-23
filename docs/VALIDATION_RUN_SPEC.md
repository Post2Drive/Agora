# AGORA Validation Run Specification — Protocol v0.2 (additive to v0.1)

Status: DRAFT until merged and frozen. v0.1 (`docs/VALIDATION_PROTOCOL.md` at 6d06088cf7954bd41f003544f5ec61675389bcc1) is **not edited**. This file only adds the five items the owner pre-approved for v0.2 (22:25 IST, 23 Nov 2026): (1) how published averages become AGORA inputs, (2) how AGORA vote share becomes a state margin, (3) how counted actions become EV registrations, (4) the run command, (5) the backend. Splits, metrics, baselines, data and the dataset manifest (SHA-256 59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf) are unchanged. `VALIDATED_PREDICTION_ENABLED` stays False.

## 1. Package E

### 1.1 Published average → AGORA input
For each (cycle, state, cutoff) the latest FiveThirtyEight state average dated on or before `Election Day − {28, 14, 7} days` gives two-party margin `m` in percentage points (Democratic minus Republican candidate listed in the harness for that cycle; National and district rows excluded). One governed package row per state-cutoff is built by `agora/validation/election_harness.py::make_run`: a single segment, option set {Democratic, Republican}, segment leaning `+s` for Democratic and `−s` for Republican, where `s = clip(k · m / 100, −1, 1)`. Mapping is via the optional `leaning` key of `project_segments` (merged separately, PR #205). All other segment fields are fixed constants (stance_sd 0.3, stubbornness 0.5, activity 0.4, influence 1.0, openness 0.5).

`k` is chosen **only** on cycles 2000, 2004, 2008 from the predeclared grid {0.10, 0.14, 0.17, 0.19, 0.21, 0.24, 0.28} by lowest MAE against MEDSL outcomes; ties go to the smaller k. 2012 is run once with that k as validation. 2016 is run once with the same k, as the held-out test. No retuning after any label from 2012 or 2016 is seen.

### 1.2 Vote share → state margin
The engine's weighted option share is read with `Analysis(project).choice()`; margin = `two_party_margin(share_D, share_R)` in pp. Reported error = predicted margin − actual two-party margin (MEDSL).

### 1.3 Outcomes
MEDSL `countypres_2000-2024.csv`: per county use the TOTAL mode row if present, else the sum of modes (2024-style double counting is avoided); state totals are county sums for the two named candidates; two-party margin. State-cycles without a published poll series (e.g. 2004 DC, 2004 WY, 2008 DC, 2012 AK/DE/MS) are excluded for all models alike and counted in the report.

### 1.4 Baselines and metrics (unchanged from v0.1)
Primary baseline: latest published same-state average on or before the cutoff. Secondary: previous-election persistence. MAE primary, RMSE secondary, 95% percentile cluster bootstrap by state, B = 2000, seed 20261123, paired against the primary baseline.

### 1.5 Backend and determinism
Mock LLM backend; 2000 crowd agents, 0 LLM agents, 16 rounds, seed 20261123 per run. No model calls are made, so "temperature 0 with cache on" is moot for this package; this is disclosed, not hidden. Governed packages are constructed directly by the harness (not through the governed importer) and authorised with the synthetic-fixture Principal, which is acceptable only for this strictly local validation on approved public datasets; the production CLI stays fail-closed.

### 1.6 Expected behaviour (stated before running)
AGORA's readout is a monotone function of the published margin by construction, so beating the published average is not expected; the honest finding may be that AGORA matches or slightly degrades it. This is reported as found.

### 1.7 Run command (stages, in order; labels stay sealed until step 3)
```
python -m agora.validation.run_election_validation calibrate    --polls P --medsl M --manifest MAN --out OUT
python -m agora.validation.run_election_validation validate     --polls P --medsl M --manifest MAN --out OUT --k <k>
python -m agora.validation.run_election_validation test-predict --polls P --manifest MAN --out OUT --k <k>   # opens NO outcome file; prints outputs SHA-256
python -m agora.validation.run_election_validation test-evaluate --polls P --medsl M --manifest MAN --out OUT --sealed-sha <sha>
```
Each input file is verified against the frozen manifest (bytes and SHA-256) before use; a mismatch aborts. `test-evaluate` refuses to open labels unless the sealed outputs' SHA-256 equals `--sealed-sha`, which is logged in Notion before the stage runs.

### 1.8 Not-evaluable and stop rules
Fewer than 10 clusters, any manifest mismatch, a seal mismatch, or an engine failure stops the package and is reported. Global stop rules in v0.1 §6 apply unchanged.

## 2. Package A (Ember monthly EV sales)

### 2.1 Counted actions → EV registrations
Decision recorded before the run: **no deterministic, defensible mapping exists** from AGORA counted actions (option choices of a synthetic population) to monthly EV registrations without inventing a conversion rule that would be fitted on the same series. Package A is therefore predeclared **NOT EVALUABLE** under v0.1 ("if no defensible mapping exists the package is not evaluable / lineage-only"). Only the seasonal-naive (t−12) baseline WAPE on the 2024–2025 test window may be reported for lineage, with no AGORA claim. If a defensible mapping is later proposed, it needs a new owner-approved revision.

## 3. Reporting
Every result, including losses, goes to the Notion log with: frozen commit, manifest hash, k, per-stage output SHA-256, MAE/RMSE for AGORA, published average and persistence, paired bootstrap CIs, excluded state-cycles, and the statement that no claim of validated prediction follows.

## 4. Diff discipline
This revision adds this file only. Changes to splits, metrics, baselines, data or manifest require new owner approval.

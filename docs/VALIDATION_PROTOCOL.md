# Validation Protocol — Three Public Benchmark Packages

**Status:** Draft preregistration. This document is written before any validation run. It is not yet frozen or committed as a protocol, and no dataset has been run through AGORA under this protocol. Do not report validation results or claim validation reached.

**Draft baseline:** main `15a92c56fdac14bb6266eec4acbd15b528d4b035` (22 November 2026). #132's fixture manifest pin, direct fixture symlink/version and direct workdir-root symlink hardening are merged; M2 remains in progress and M3 is proposal-only. This protocol is not frozen/committed and no validation runs have occurred. Validation runs remain blocked until M2 is confirmed by Claude, M3 is built and confirmed, and this protocol is reviewed and committed before any run.

## 1. Purpose, scope and non-claims

Evaluate whether a governed, reproducible AGORA simulation workflow can consume a defined public input package and produce a labelled, traceable output that can be compared with known outcomes under a predeclared time split.

This is not a claim that AGORA is a statistical forecasting model, that a simulated social system is causally valid, or that any output is fit for operational decisions. A benchmark is evaluable only if the M3 adapter can produce the exact target and unit defined below. If the engine cannot produce a semantically compatible output, mark that dataset **not evaluable** and stop; do not invent a proxy target after seeing results.

No P2D, NCC, Nutrivance, customer, driver, personal, private or owner operational data is in this protocol. P2D remains pre-launch with no real data. No connectors, credentials, live database access, network access from AGORA or write-back are allowed. Dataset acquisition is by manually supplied/downloaded export files outside AGORA; the run itself is offline.

## 2. Preregistration and freeze procedure

Before the first run:

1. Confirm Claude's exact M2 completion entry and exact M3 implementation/confirmation entry.
2. Freeze this protocol in a merged documentation commit. Record the commit SHA and approved run scope in the collaboration log.
3. Resolve each dataset's licence/terms and save source URL, licence text/version, access date, citation, source release/version and local file SHA-256 in a dataset register.
4. Freeze dataset field allow-lists, exclusions, time cutoffs, transformations, output targets, metrics, baselines, uncertainty procedure and stop rules.
5. Freeze AGORA repository SHA, Python/runtime/dependency lock, M3 adapter version, scenario/configuration hash, random seeds, model/backend/version and generation parameters.
6. Create a fresh isolated project per dataset and split. Do not use a previous project, run, calibration artifact or mutable `latest` pointer.
7. Seal test labels/outcomes from training, calibration, prompt construction, parameter tuning and scenario editing. An independent evaluator releases them only after the prediction/output is frozen.
8. Record every attempted run, including failed, denied, interrupted and invalid runs. Never delete a failed attempt or replace its record with a successful rerun.

If any field, split, metric, baseline, dataset version, adapter, model, seed, scenario, run count or stop rule must change after freeze, increment the protocol version, explain why, obtain approval and treat the changed evaluation as a new preregistration. Do not silently amend this protocol after seeing outcomes.

## 3. Approved benchmark packages

The owner-approved domains are election results and polls, retail sales (M5 Walmart or Rossmann), and public adoption series (UPI or EV registrations). This draft selects the following concrete packages for review. Substitution is not automatic; any replacement must be named and approved before protocol freeze.

### Package E — FiveThirtyEight 2020 Presidential Polls paired with MEDSL County Presidential Election Returns 2000–2024

**Purpose:** time-ordered poll-to-election comparison. Polling records are predictors; compiled election returns are the outcome source. These are two source datasets forming one paired election benchmark.

**Sources and terms**

- Polls: FiveThirtyEight `data/polls` presidential general-election poll files, including the 2020 historical poll series and 2020 polling averages where needed for source cross-check. The repository is marked CC BY 4.0. Preserve attribution and exact file/version/hash. Source: https://github.com/fivethirtyeight/data and https://github.com/fivethirtyeight/data/tree/master/polls
- Outcomes: MIT Election Data and Science Lab, **County Presidential Election Returns 2000–2024**, Harvard Dataverse DOI https://doi.org/10.7910/DVN/VOQCHQ, Version 20.0, CC0 1.0. Cite the dataset exactly as required by its Dataverse record.

**Candidate fields to inspect and allow-list**

- Polls: poll ID, pollster, state/geography, start date, end date, sample size, population type, candidate name, candidate percentage, poll mode and source-defined poll-quality metadata actually present in the pinned file.
- Results: election year, state/state code, county ID, candidate, party, candidate votes, total votes and dataset version.
- Exclude pollster free-text notes, respondent-level data if encountered, personal data, any post-election field and fields calculated using future results.
- Aggregate county returns to state-level two-party vote share using a deterministic documented grouping; independently reconcile aggregate totals to source totals. Exclude territories and any state/office/contest that cannot be matched unambiguously.

**Time split**

- Training/calibration election cycles: 2008, 2012 and 2016, subject to verified coverage in pinned poll and result files.
- Validation cycle: 2020.
- Held-out test cycle: 2024.
- For each election cycle, freeze forecast cutoffs at 28, 14 and 7 calendar days before Election Day. Only polls with `enddate` on or before cutoff may be used. Exclude any poll or derived field published after cutoff.
- The 2024 outcome labels remain sealed until predictions are frozen. If the pinned poll source does not contain adequate pre-election 2024 coverage, stop this benchmark rather than substitute another cycle after inspecting outcomes.

**Target and metrics**

- Target: state-level two-party margin (percentage points) at the election result.
- Primary metric: mean absolute error (MAE) in percentage points across eligible state/cutoff pairs.
- Secondary metrics: root mean squared error (RMSE) and, only if the engine emits a genuine probability, Brier score for state winner.
- Report coverage (number and share of states with a valid output) beside every metric. No post-hoc state exclusions.

**Naive baseline**

- Sample-size-weighted mean two-party poll margin from the 28-day window ending at each cutoff.
- If no eligible poll exists for a state/cutoff, report missing coverage; do not impute after seeing the result.
- A separate persistence baseline may carry forward the previous election's state margin, clearly labelled as a second baseline.

**Uncertainty**

- Use a predeclared 95% block-bootstrap interval, resampling states as clusters and pollsters within state only where source supports that grouping.
- Report distribution of errors across states and cutoffs, not only one national aggregate.
- If too few independent clusters exist for a stable interval, report not estimable; do not substitute a misleading narrow interval.

**Suitability stop:** if AGORA cannot emit state-level margins/probabilities from a governed input with a defensible predeclared mapping, this package is data-lineage-only and no predictive metric is calculated.

### Package R — M5 Forecasting — Accuracy (Walmart retail sales)

**Purpose:** 28-day retail unit-sales time-series benchmark at item/store level.

**Source and terms**

- Official competition dataset: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Kaggle identifies the dataset licence as **Subject to Competition Rules**. The rules, permitted research/non-commercial use, access requirements, attribution, retention and redistribution restrictions must be read and recorded before acquisition. Do not assume CC0 or unrestricted redistribution. Do not commit raw data to this repository. If intended evaluation use is not clearly permitted, stop and request a named owner-approved replacement (Rossmann is not an automatic substitute).

**Candidate fields to inspect and allow-list**

- Sales: `item_id`, `dept_id`, `cat_id`, `store_id`, `state_id`, daily unit-sales columns.
- Calendar: day/date, week, month, year, event name/type and SNAP indicators.
- Prices: store/item/week and sell price.
- Exclude competition submission identifiers or labels that leak the target window; do not use hidden or later evaluation labels as features.

**Time split**

- Use the official M5 chronological daily index.
- Training: `d_1`–`d_1857`.
- Validation: `d_1858`–`d_1885` (28 days).
- Held-out test: `d_1886`–`d_1913` (28 days).
- Keep `d_1914`–`d_1941` sealed and unused as a reserve; it must not be used for model/scenario selection or to choose between adapters.
- Verify calendar mapping from day IDs to actual dates using pinned `calendar.csv`; stop if official file structure differs from this split.

**Target and metrics**

- Target: daily unit sales per item/store series over the 28-day horizon.
- Primary metric: M5 Weighted Root Mean Squared Scaled Error (WRMSSE), implemented from the published M5 hierarchy/weights with an independent calculation check.
- Secondary metrics: WAPE and RMSSE. Report aggregate and category/store-level metrics; disclose zero-denominator handling before the run.
- If AGORA engine output cannot be mapped to a numeric item/store/day prediction without inventing a conversion rule, classify the benchmark as not evaluable.

**Naive baseline**

- Seasonal-naive forecast: repeat the corresponding weekday's observed sales from the previous week (`t-7`) for each series across the 28-day horizon.
- No external training data or additional predictors outside pinned competition files.

**Uncertainty**

- Calculate 95% intervals using a predeclared block bootstrap over store/item series, preserving the 28-day time block within each sampled series.
- Report metric intervals and empirical interval coverage if the model emits prediction intervals. If the engine emits no probabilistic range, do not fabricate one; report bootstrap uncertainty of evaluation metric only.

**Suitability/licence stop:** no run until M5 Competition Rules have been reviewed and recorded as permitting intended use. Do not publish or redistribute competition data or derived files where rules prohibit it.

### Package A — Ember Monthly EV Sales Data

**Purpose:** monthly public adoption/market-share time series for battery-electric and plug-in-hybrid passenger cars.

**Source and terms**

- Ember, **Monthly EV Sales Data**, direct CSV downloads and methodology: https://ember-energy.org/data/monthly-ev-sales-data/
- Ember describes the files as open data under Creative Commons Attribution 4.0 (CC BY 4.0). Preserve attribution, source version/date, methodology version and SHA-256. Underlying national-source scope/definitions must remain attached to relevant country notes.

**Candidate fields to inspect and allow-list**

- Area, ISO 3 code, area type, date, data frequency, drivetrain, aggregate-drivetrain flag, registrations, registrations YoY change, registrations YoY change (%), share of registrations (%), year-to-date registrations/share, rolling 12-month registrations/share.
- Use country/economy rows only; exclude World, EU and other regional aggregates from the primary metric to avoid double counting.
- Use monthly rows only. Exclude quarterly observations from the monthly benchmark rather than filling/interpolating them.
- Predeclare whether target is aggregate BEV+PHEV registrations or share of all-drivetrain registrations. Do not switch target after results.

**Time split**

- Training: all eligible monthly observations through December 2022.
- Validation: January–December 2023.
- Held-out test: January 2024–December 2025.
- Include only country series with at least 60 monthly observations before the test period and a valid predeclared coverage rule. Freeze eligible country list before opening test labels.
- Freeze exact Ember release and CSV hashes. If source revisions change historical values, treat revised release as a new dataset version and do not mix versions across splits.

**Target and metrics**

- Primary target: monthly BEV+PHEV registrations by country.
- Primary metric: WAPE over all eligible country-month observations.
- Secondary metric: MAE in percentage points for EV share of all-drivetrain registrations.
- Report per-country metrics and coverage; do not allow large markets to conceal poor country-level performance.

**Naive baseline**

- Seasonal-naive: repeat same country's value from same month one year earlier (`t-12`).
- If source has no prior-year value, exclude that country-month under the predeclared coverage rule; do not interpolate.

**Uncertainty**

- Use 95% block-bootstrap intervals, resampling countries as clusters and contiguous 12-month blocks within country.
- Report per-country and aggregate intervals. If too few eligible country clusters remain, mark uncertainty not estimable and stop broad generalisation.

**Methodology stop:** Ember notes source publishers and reporting definitions differ by country and may be revised; retain country-level notes and do not interpret series as perfectly harmonised ground truth.

## 4. Common run and evidence procedure

For each package, after all gates pass:

1. Acquire files manually outside AGORA, retain source page, licence/rules, access date and citation, then place permitted files in an isolated local read-only input directory.
2. Record file names, byte sizes, SHA-256 hashes, source version and exact field allow-list. Do not store raw files in Git.
3. Independently inspect schemas/date coverage; verify pinned release matches split table. If not, stop and issue a protocol revision before any run.
4. Prepare governed snapshot with exact import ID, schema, binding, ontology and policy fingerprints. No network fetch or connector is available to AGORA.
5. Record repository SHA, clean-checkout environment, dependency versions, OS, Python version, M3 adapter version, scenario hash, seeds, model/backend/version, run configuration and protocol commit SHA.
6. Run training/calibration and validation only within declared windows. Keep held-out test outcomes inaccessible to scenario builder and model operator.
7. Freeze output artifacts and hashes before releasing test labels to independent evaluator.
8. Calculate declared metrics and uncertainty intervals using a separately checked evaluation script. Preserve raw logs, failures and denials; redact secrets and do not publish restricted source data.
9. Record all run IDs, input manifest hashes, report hashes, output hashes, evaluation script SHA, metric values and exclusions in validation register. Claude alone records validation status/results in collaboration log.

The exact M3 run invocation and evaluator command are intentionally not invented here: they must match merged M3 CLI/API and be inserted into a versioned protocol revision before first run. Existing `agora run <project>` is the current simulation CLI, but it does not yet prove governed tabular-input wiring.

## 5. Common metrics and reporting rules

- Compare AGORA output with declared naive baseline on exactly the same eligible observations.
- Report numerator, denominator, units, coverage and exclusions with every metric.
- Provide absolute error and relative-to-baseline difference; do not select best metric after results.
- Report 95% uncertainty intervals and sample/cluster counts. An interval that cannot be estimated is explicitly marked not estimable.
- Report all three packages separately. Do not combine them into one score or imply cross-domain generalisation from three datasets.
- Retain every failed, denied, interrupted and invalid run. No cherry-picking of seeds, model variants, cutoffs, geographies, subgroups.
- Better metric than baseline does not establish causal validity, commercial usefulness, deployment fitness or permission to enable validated-prediction output.

## 6. Global stop rules

Stop the affected package immediately if licence/competition terms are missing, ambiguous or inconsistent with intended use; pinned file hashes, source versions, schema, field definitions or date coverage do not match; test labels/future-dated features are exposed before output freeze; M3 adapter cannot produce exact target/unit without a post-hoc proxy; engine/report cannot preserve full input provenance; a personal/sensitive field, P2D/NCC/Nutrivance data, credential, connector or live network source appears; any result is presented as observed reality or validated prediction; an unplanned parameter/model/seed/split/exclusion/transformation is introduced; `VALIDATED_PREDICTION_ENABLED` is not `False`; or an unapproved file under `agora/sim/**` is changed.

A stop is recorded as a failed/blocked attempt, not silently retried. Protocol changes require a new version and commit before another run.

## 7. Dataset licence and field checklist

| Package | Source/version and exact files | Licence/terms evidence | Field allow-list and exclusions | Hashes and access date | Approved before run |
|---|---|---|---|---|---|
| E — FiveThirtyEight polls + MEDSL results | TBD | FiveThirtyEight repository CC BY 4.0; MEDSL Dataverse CC0 1.0; archive exact notices | TBD | TBD | No |
| R — M5 Walmart | TBD | Subject to Kaggle Competition Rules; explicit review required | TBD | TBD | No |
| A — Ember Monthly EV Sales | TBD | CC BY 4.0; preserve source-country notes | TBD | TBD | No |

## 8. Preregistration record

| Field | Value |
|---|---|
| Protocol version | Draft 0.1 |
| Protocol commit SHA | Not yet frozen |
| M2 confirmation entry | Pending Claude |
| M3 confirmation entry | Pending Claude |
| Dataset register SHA | TBD |
| Repository SHA | TBD |
| M3 adapter SHA/version | TBD |
| Python/runtime/dependency lock | TBD |
| Scenario/configuration hashes | TBD |
| Model/backend/version and parameters | TBD |
| Random seeds and number of runs | TBD |
| Evaluation script SHA | TBD |
| Independent evaluator | TBD |
| Dataset-specific owner approval references | 12:52 IST named approval; confirm scope at freeze |
| First run date | Not scheduled |
| Validation results | None recorded in this draft |

## 9. Sources

- FiveThirtyEight polls data repository and file index: https://github.com/fivethirtyeight/data/tree/master/polls
- FiveThirtyEight repository licence: https://github.com/fivethirtyeight/data
- MIT Election Data and Science Lab, County Presidential Election Returns 2000–2024, Harvard Dataverse DOI: https://doi.org/10.7910/DVN/VOQCHQ
- M5 Forecasting — Accuracy official dataset page and competition terms: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Ember Monthly EV Sales Data and methodology: https://ember-energy.org/data/monthly-ev-sales-data/

**No dataset was downloaded, imported, run or evaluated while drafting this protocol. No validation result is claimed.**

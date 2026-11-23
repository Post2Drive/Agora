# Validation Protocol — Three Public Benchmark Packages

**Status:** Draft preregistration. This document is committed as draft documentation, not frozen or owner-approved as an execution protocol. No dataset has been run through AGORA under this protocol. Do not report validation results or claim validation reached.

**Baseline:** main `9dad1c8f9ab9ccc3c73aee76403cecab222d25e6` (23 November 2026; documentation-only merge #181 at exact head `73a4947efc1beb94b55718568a1d453d579bae1b`, CI run `45122674011` passed 4/4). M3 governed-input slices 4.1–4.4 and 4.6 are merged: #163/#164 deterministic fail-closed projection, #171 governed-input engine path, #172 CLI entry point, #173 order-independent instance-row hashing, and #178 original/projected scenario-hash separation. Exact-head CI passed 4/4 for #171 (`45089066900`), #172 (`45093439437`), #173 (`45096233966`) and #178 (`45113858688`). Supporting dataset-independent metrics #175, #176 and #179 are also merged; exact-head CI passed 4/4 for #175 (`45105990141`), #176 (`45110601617`) and #179 (`45116463242`). #176 pins the official M5 RMSSE scale convention (calculate adjacent differences from the first non-zero training observation, excluding pre-sale leading zeros) and hardens poll date/window and boolean input checks. #179 adds strict non-bool integer checks for bootstrap `samples` (minimum 100) and `min_clusters` (minimum 1), plus finite non-bool `alpha` in (0,1). #180 adds a non-negative seed guard and invalid-seed tests (merged, merge commit `76ee7625`; exact-head workflow `45119572140` passed 4/4). The earlier review note that the standard M5 denominator includes pre-sale leading zeros was incorrect; the merged helper follows the first-nonzero convention and #176 adds a regression test for it. The production CLI still denies governed runs because `_governed_policy()` returns `None` until an approved identity adapter exists; direct-constructor policy authorization remains an open M3 trust-boundary item. The hash distinction is implemented in #178. This protocol remains a draft; no dataset has been run and no validation is authorized.



## 1. Purpose, scope and non-claims

Evaluate whether a governed, reproducible AGORA simulation workflow can consume a defined public input package and produce a labelled, traceable output that can be compared with known outcomes under a predeclared time split.

This is not a claim that AGORA is a statistical forecasting model, that a simulated social system is causally valid, or that any output is fit for operational decisions. A benchmark is evaluable only if the M3 adapter can produce the exact target and unit defined below. If the engine cannot produce a semantically compatible output, mark that dataset **not evaluable** and stop; do not invent a proxy target after seeing results.

No P2D, NCC, Nutrivance, customer, driver, personal, private or owner operational data is in this protocol. P2D remains pre-launch with no real data. No connectors, credentials, live database access, network access from AGORA or write-back are allowed. Dataset acquisition is by manually supplied/downloaded export files outside AGORA; the run itself is offline.

## 2. Preregistration and freeze procedure

Before the first run:

1. Confirm Claude's exact M2 completion entry and a distinct M3 implementation-complete entry. Merged M3 slices do not by themselves freeze this validation protocol or authorize a validation run.
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
- Secondary metrics: WAPE and RMSSE. For RMSSE, the M5 scale denominator is the mean squared first difference **from the first non-zero training observation onward**; leading zero periods before the first sale are excluded, matching the official M5 convention. If no non-zero observation or fewer than two observations remain, or the resulting scale is zero, report `NotEstimable`; do not impute. Report aggregate and category/store-level metrics; disclose zero-scale handling before the run.

**Implementation status:** main `agora/validation/benchmark_metrics.py::rmsse()` starts its scale segment at the first non-zero training observation. #176 pins the official M5 convention and hardens poll date/window, malformed required poll fields, sample sizes and boolean inputs (exact-head CI `45110601617`, 4/4). #179 adds strict bootstrap `samples`, `min_clusters` and `alpha` guards (exact-head CI `45116463242`, 4/4). The negative-seed guard (#180) is merged (exact-head CI `45119572140`, 4/4). These pure helper checks do not establish that AGORA emits a semantically compatible M5 target or authorize dataset use.
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

The merged helper module is a starting point, not a frozen evaluator. Before use, require `weighted_poll_margin()` to reject malformed date types and non-positive/non-integer windows as `NotEstimable`, and require `two_party_margin()` to reject boolean shares rather than treating `True`/`False` as numeric percentages. The evaluator must preserve the protocol's cutoff and denominator rules and must not silently coerce malformed inputs.

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

## 8.1 Freeze-blocking review findings

This review is documentation-only. The protocol remains **Draft 0.1**, is not frozen, and has not been approved for execution. Resolve each item in a versioned revision before any owner freeze decision:

1. **Run-count and randomness contract is incomplete.** The preregistration table leaves random seeds and number of runs as TBD. Specify the exact seed list, runs per dataset/split/configuration, whether any LLM sampling is deterministic, generation temperature/top-p/timeout/retry/cache settings, and the rule for failed/interrupted attempts. Bootstrap replicate counts and bootstrap RNG seeds are also unspecified. These values must be fixed before outputs are observed.
2. **Exact source assets and field names are not pinned.** Package E's 2024 poll-file availability and exact file names/columns are not demonstrated by this draft. Pin immutable source commits/Dataverse versions, exact filenames and observed headers; do not assume candidate field labels are literal CSV headers. If 2024 pre-election coverage is inadequate, stop as already specified. Package R must list every source file needed for the chosen split, including the evaluation file if the reserved `d_1914`–`d_1941` window is retained. Package A must pin the exact monthly export and methodology release.
3. **M5 file/split alignment needs a source-file check.** The stated `d_1914`–`d_1941` reserve is not in `sales_train_validation.csv` (which ends at `d_1913`); if that reserve is retained, the acquisition register must include the corresponding `sales_train_evaluation.csv` release and explicitly protect those labels. Otherwise remove the reserve claim in a new preregistration revision. Verify all day/date mappings against the pinned calendar.
4. **Output-target compatibility is unproven.** The current projection converts tabular rows into social-simulation segment parameters; the three benchmarks require election-margin, item/store/day sales, or country/month registration outputs. No evidence yet demonstrates that the simulation emits these exact target units. A package must be marked **not evaluable** unless a deterministic, predeclared mapping exists without post-hoc proxy conversion. Do not run the engine to discover a mapping under this draft.
5. **Uncertainty procedures need executable parameters.** Fix bootstrap replicate count, sampling algorithm, cluster/block definitions, replacement policy, RNG seed, handling of sparse clusters, and whether intervals are percentile, basic or bias-corrected. State the exact independently checked implementation/version.
6. **Evaluator and label custody are unresolved.** Name the independent evaluator, specify how held-out labels are kept inaccessible, who controls release, and what immutable evidence proves output freeze preceded label release. A TBD evaluator is a stop condition, not an administrative detail.
7. **Licence and privacy review must be per-file.** M5 Competition Rules must be checked against intended use and derived outputs before download/use. For every package, inspect headers and representative rows for personal identifiers, free-text fields or sensitive data; record the result and exclude disallowed fields. Public availability does not remove privacy or licence obligations.
8. **Identity/policy is not ready.** The current CLI policy source returns `None`, so governed CLI construction is denied before snapshot bytes are opened. The owner must decide whether a synthetic Principal is acceptable for a strictly local public-data evaluation. Any accepted adapter must be Principal-bound, scoped, expiring, fail-closed and proven to deny before source bytes are opened. Direct engine construction must not bypass the policy authorization boundary.
9. **Provenance/report completeness remains to be verified.** #178 pins distinct original `base_scenario_hash` and projection-bound `projected_scenario_hash` values, alongside the row-bound `instances_hash` and mapping/projection hashes in the immutable record. Verify reports/exports expose both scenario hashes and the complete required provenance with the exploratory label.

Do not freeze by merely replacing TBD with assumptions. Record source evidence and owner decisions first. No protocol change here authorizes a dataset import, simulation or validation run.

## 8. Preregistration record

| Field | Value |
|---|---|
| Protocol version | Draft 0.1 |
| Protocol commit SHA | Not yet frozen |
| M2 confirmation entry | Claude confirmed 23:43 IST, 22 November 2026; link exact log entry at freeze |
| M3 confirmation entry | Pending Claude; implementation slices alone do not establish M3 reached |
| Dataset register SHA | TBD |
| Repository SHA | TBD |
| M3 adapter SHA/version | TBD |
| Python/runtime/dependency lock | TBD |
| Scenario/configuration hashes | TBD |
| Model/backend/version and parameters | TBD |
| Random seeds and number of runs | TBD — freeze blocker; exact list and count required per package/split/configuration |
| Evaluation script SHA | TBD |
| Independent evaluator | TBD — freeze blocker; name evaluator and label-release procedure |
| Dataset-specific owner approval references | 12:52 IST named approval; confirm scope at freeze |
| First run date | Not scheduled |
| Validation results | None recorded in this draft |

## 8.2 Acquisition reachability and mirror approval

Claude's 09:05 IST reachability check reports FiveThirtyEight GitHub data fetchable, but Harvard Dataverse, Kaggle and Ember's official host blocked by its workspace allowlist. The dataset checklist records candidate GitHub mirrors for MEDSL V20 and Ember's monthly CSV. These are **not approved substitutions**: the MEDSL mirror is third-party (its README records the Dataverse V20 MD5 and CC0 source licence); the Ember mirror is third-party and snapshots the official CSV on 16 November 2026, while Ember's official page reports an 18 November 2026 update. Owner approval must identify exact repo, commit, file, version and licence before use. M5 remains owner-supplied via Kaggle and its competition rules.

No dataset has been downloaded or approved for use. The protocol's canonical publishers and licence terms remain authoritative; mirror reachability does not change the source or grant permission.

## 9. Sources

- FiveThirtyEight polls data repository and file index: https://github.com/fivethirtyeight/data/tree/master/polls
- FiveThirtyEight repository licence: https://github.com/fivethirtyeight/data
- MIT Election Data and Science Lab, County Presidential Election Returns 2000–2024, Harvard Dataverse DOI: https://doi.org/10.7910/DVN/VOQCHQ
- M5 Forecasting — Accuracy official dataset page and competition terms: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Ember Monthly EV Sales Data and methodology: https://ember-energy.org/data/monthly-ev-sales-data/

**No dataset was downloaded, imported, run or evaluated while drafting this protocol. No validation result is claimed.**

# Validation Protocol — Three Public Benchmark Packages

**Status:** Draft preregistration. This document is committed as draft documentation, not frozen or owner-approved as an execution protocol. No dataset has been run through AGORA under this protocol. Do not report validation results or claim validation reached.

**Baseline:** main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2` (23 November 2026; #192 closes the RT05d source-side backup-record gap at exact head `bdf13a0663e5498c9d2e857817769985a8419e94`, merge `3e55e5505cda38a2ccfdc93a3e9996120ebb659e`, exact-head CI `45150068645` passed 4/4; #195 is the latest docs-only sync at exact head `fedab29c7d1e5b3d67e252d73bb97c9ae37acf93`, merge/current main `e29ee4b1428fbc27458b547cc8c68bd4833c6ff2`, exact-head CI `45160887328` passed 4/4, six paths all under `docs/**`). #183 static symlink/reparse-point hardening, #189 backup record verification/restore and #192 source-side preflight are merged. The owner selected the synthetic-fixture Principal for strictly local validation on approved public datasets only; the production CLI remains fail-closed and the direct-engine receipt is not implemented. The owner included concurrent local path replacement in the synthetic/validation threat model; Claude has claimed a handle-based SQLite-open slice for chain, anchor and seal checks, not yet merged. The full polls window is conditional on all four required owner files and their per-file SHA-256/source/licence manifest; if the corrected 2024 general asset is unavailable, a separate 2000–2016 preregistration is the proposed fallback. Bias controls and evaluator rules are proposed for freeze, not frozen. No dataset has been run; this protocol remains a draft and no validation is authorized.

## 1. Purpose, scope and non-claims

Evaluate whether a governed, reproducible AGORA simulation workflow can consume a defined public input package and produce a labelled, traceable output that can be compared with known outcomes under a predeclared time split.

This is not a claim that AGORA is a statistical forecasting model, that a simulated social system is causally valid, or that any output is fit for operational decisions. A benchmark is evaluable only if the M3 adapter can produce the exact target and unit defined below. If the engine cannot produce a semantically compatible output, mark that dataset **not evaluable** and stop; do not invent a proxy target after seeing results.

No P2D, NCC, Nutrivance, customer, driver, personal, private or owner operational data is in this protocol. P2D remains pre-launch with no real data. No connectors, credentials, live database access, network access from AGORA or write-back are allowed. Dataset acquisition is by manually supplied/downloaded export files outside AGORA; the run itself is offline.

## 2. Preregistration and freeze procedure

Before the first run:

1. Confirm Claude's exact M2 completion entry and a distinct M3 implementation-complete entry. Merged M3 slices do not by themselves freeze this validation protocol or authorize a validation run.
2. Freeze this protocol in a merged documentation commit. Record the commit SHA and approved run scope in the collaboration log.
3. Resolve each dataset's licence/terms and save source URL, licence text/version, access date, citation, source release/version or full source commit, exact original filename, byte size and SHA-256 for every file in a per-file manifest. Commit the complete manifest to the owner-controlled private data repository before any import or run.
4. Freeze dataset field allow-lists, exclusions, time cutoffs, transformations, output targets, metrics, baselines, uncertainty procedure and stop rules.
5. Freeze AGORA repository SHA, Python/runtime/dependency lock, M3 adapter version, scenario/configuration hash, random seeds, model/backend/version and generation parameters.
6. Create a fresh isolated project per dataset and split. Do not use a previous project, run, calibration artifact or mutable `latest` pointer.
7. Seal test labels/outcomes from training, calibration, prompt construction, parameter tuning and scenario editing. An independent evaluator releases them only after the prediction/output is frozen.
8. Record every attempted run, including failed, denied, interrupted and invalid runs. Never delete a failed attempt or replace its record with a successful rerun.

If any field, split, metric, baseline, dataset version, adapter, model, seed, scenario, run count or stop rule must change after freeze, increment the protocol version, explain why, obtain approval and treat the changed evaluation as a new preregistration. Do not silently amend this protocol after seeing outcomes.


## 2.1 Bias controls and evaluator rule — proposed for freeze

These controls follow the owner's 23 November design delegation and Claude's written proposal C/D. The suggested owner acceptance paste for the broader A–D bundle is not present. They are **proposed for freeze**, not frozen or owner-approved as an execution protocol. This document remains a draft and this section does not authorize data acquisition, import, simulation, validation or prediction enablement.

| Package | Fixed time split / cutoffs | Naive baseline | Metrics to report | Uncertainty for every metric | Stop rule |
|---|---|---|---|---|---|
| E — FiveThirtyEight polls + MEDSL returns | Full window: training cycles 2008, 2012, 2016; validation: 2020; held-out test: 2024. For each cycle, use only polls ending on or before 28-, 14- and 7-day cutoffs. Election Days and cutoffs: 2008-11-04 (10-07, 10-21, 10-28); 2012-11-06 (10-09, 10-23, 10-30); 2016-11-08 (10-11, 10-25, 11-01); 2020-11-03 (10-06, 10-20, 10-27); 2024-11-05 (10-08, 10-22, 10-29). **Conditional fallback if the corrected 2024 general asset is unavailable after its single prescribed live-URL attempt:** a separate preregistration with training cycles 2000/2004/2008, validation 2012 and held-out test 2016; cutoffs must be fixed at the same 28/14/7-day offsets for each election (2000-11-07: 10-10/10-24/10-31; 2004-11-02: 10-05/10-19/10-26; 2008-11-04: 10-07/10-21/10-28; 2012-11-06: 10-09/10-23/10-30; 2016-11-08: 10-11/10-25/11-01). Do not mix the full and fallback windows or silently change splits. | Prior-election sample-size-weighted poll-average margin for the same state and office at the matching 28/14/7-day cutoff, calculated only from polls available by that prior-cycle cutoff. If a comparable prior-cycle poll average is not available for a state/cutoff, report missing baseline coverage; do not substitute an election result, current-cycle average or a different office/window. | MAE (primary), RMSE (secondary), and Brier score only if the engine emits a genuine probability. Report state/cutoff coverage and per-state errors. | 95% cluster/block-bootstrap interval for every estimable metric, resampling states as clusters and pollsters within state only where source fields support it. Report cluster count; mark not estimable if too few independent clusters. | Stop if pinned sources do not provide required pre-cutoff coverage or a comparable last-election poll-average baseline, state/office matching is ambiguous, or AGORA cannot emit the exact state-level margin/probability without a post-hoc proxy. Never substitute uncorrected 2024 averages for corrected 2024 polls. |
| R — M5 Walmart sales | Training d_1–d_1857; validation d_1858–d_1885; held-out test d_1886–d_1913; reserve d_1914–d_1941 stays sealed and unused. Resolve the reserve against the exact sales_train_evaluation.csv and Kaggle terms before freeze. | Seasonal-naive: repeat each series' corresponding weekday from t-7. | WRMSSE (primary), WAPE and RMSSE (secondary), with hierarchy/category/store breakdowns and explicit zero-scale handling. | 95% block-bootstrap interval for every estimable metric, resampling store/item series and preserving the 28-day horizon block. If the engine emits no prediction range, report metric uncertainty only; do not fabricate predictive intervals. | Stop if the pinned calendar/day mapping or file bundle differs, the reserve labels are not protected, Kaggle terms do not permit intended use, or no exact item/store/day target can be emitted. |
| A — Ember monthly EV | Training through 2022-12; validation 2023-01–2023-12; held-out test 2024-01–2025-12. Freeze the eligible-country list before test labels are opened. | Last-value: carry forward the last observed monthly registration for the same country across the forecast horizon. Do not use future months or revise the baseline after seeing test outcomes. | WAPE (primary) for monthly registrations; MAE in percentage points (secondary) for EV share. Report aggregate and per-country coverage/results. | 95% block-bootstrap interval for every estimable metric, resampling countries as clusters and contiguous 12-month blocks within each country. Mark uncertainty not estimable when cluster count is inadequate. | Stop if monthly frequency/definitions are inconsistent, source revisions mix versions, eligible-country coverage fails, or AGORA cannot emit the exact declared registration/share target. |

### Bias controls

1. **Predeclare the split.** Fix every time split and cutoff before any run. No moving cutoffs after seeing outcomes.
2. **Baseline every result.** Report every loss metric alongside its dataset-specific naive baseline on the exact same eligible observations. Include AGORA loss, baseline loss and the signed difference, with direction and units. Never report an AGORA loss without its baseline.
3. **Seal the test period.** Keep held-out test labels sealed until outputs and their hashes are frozen. No prompt, scenario, parameter, mapping, feature, model or threshold tuning on validation/test outcomes; tuning is confined to the declared training/calibration window.
4. **One run per frozen configuration.** Use one run per frozen configuration and preregistered seed. Do not select a favourable rerun or seed. A failed, denied, interrupted or invalid attempt remains in the register. Any additional seed/configuration must be separately preregistered before outcomes are seen.
5. **Uncertainty for every metric.** Report a 95% uncertainty range and sample/cluster count for every metric where estimable, using the package-specific resampling unit above. If not estimable, state that explicitly rather than omit it or replace it with a narrower interval.
6. **Freeze uncertainty mechanics before freeze.** Bootstrap replicate count, bootstrap RNG seed, interval construction (percentile/basic/BCa), replacement policy, sparse-cluster handling and evaluator identity remain explicit freeze blockers. Select and record them before protocol freeze, never after observing results.
7. **Write stop rules first.** Each package's stop rule in the table is frozen before the first run; missing files, incompatible target units, unresolved licences, sparse clusters or missing labels stop the package rather than trigger a proxy or substitution.
8. **No outcome-led changes.** No post-hoc exclusions, proxy targets, source substitutions, split changes, metric switching or outcome-informed scenario revisions. A changed choice requires a new protocol version and approval before another run.

### Independent evaluator rule

The evaluator must be a **separate person or process** that sees only (1) this frozen protocol, (2) the committed dataset manifest, and (3) the raw outputs. The evaluator must not change or amend the protocol after seeing results. Preserve the evaluator identity/process version and the exact protocol, manifest and raw-output hashes with the evaluation record. Evaluator identity and custody arrangements must be named before protocol freeze. The evaluator does not get authority to change source approvals, run scope, prediction flags or owner gates.

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

1. **Run-count and randomness contract is incomplete.** The owner selected one run per frozen configuration and no test-period tuning. The exact seed list, number of configurations, LLM sampling determinism, generation temperature/top-p/timeout/retry/cache settings, bootstrap replicate count and bootstrap RNG seeds remain unspecified. Freeze them before any output is observed; failed, denied, interrupted and invalid attempts remain recorded and are not silently replaced.
2. **Exact source assets, hashes and field names are not pinned.** The owner reports a partial FiveThirtyEight private-repository import; four large files remain outstanding and no per-file SHA-256 manifest is recorded. Keep the full 2020/2024 polling window only if all required files, corrected 2024 general averages, exact byte sizes, hashes, source commit/release and licence evidence are present. If the corrected 2024 general asset is unavailable after its single live-URL attempt, use the separate 2000–2016 fallback in the proposed table; do not silently narrow, use the uncorrected file or substitute a mirror. Pin immutable source commits/Dataverse versions, exact filenames and observed headers. Package R must list every source file needed for the chosen split, including the evaluation file if the reserved `d_1914`–`d_1941` window is retained. Package A must pin the exact monthly export and methodology release.
3. **M5 file/split alignment needs a source-file check.** The stated `d_1914`–`d_1941` reserve is not in `sales_train_validation.csv` (which ends at `d_1913`); if that reserve is retained, the acquisition register must include the corresponding `sales_train_evaluation.csv` release and explicitly protect those labels. Otherwise remove the reserve claim in a new preregistration revision. Verify all day/date mappings against the pinned calendar.
4. **Output-target compatibility is unproven.** The current projection converts tabular rows into social-simulation segment parameters; the three benchmarks require election-margin, item/store/day sales, or country/month registration outputs. No evidence yet demonstrates that the simulation emits these exact target units. A package must be marked **not evaluable** unless a deterministic, predeclared mapping exists without post-hoc proxy conversion. Do not run the engine to discover a mapping under this draft.
5. **Uncertainty procedures need executable parameters.** A 95% uncertainty range is required for every primary and secondary metric. Fix bootstrap replicate count, sampling algorithm, cluster/block definitions, replacement policy, RNG seed, handling of sparse clusters, and whether intervals are percentile, basic or bias-corrected. State the exact independently checked implementation/version; if an interval is not estimable, report that rather than omit it.
6. **Evaluator identity and custody are unresolved.** The proposed evaluator rule is that a separate person or process sees only the frozen protocol, committed manifest and raw outputs and cannot change the protocol after seeing results. The owner still must name the evaluator/process, define label custody/release and preserve immutable evidence that output freeze preceded release. A TBD evaluator is a stop condition.
7. **Licence and privacy review must be per-file.** M5 Competition Rules must be checked against intended use and derived outputs before download/use. For every package, inspect headers and representative rows for personal identifiers, free-text fields or sensitive data; record the result and exclude disallowed fields. Public availability does not remove privacy or licence obligations.
8. **Identity/policy implementation is not ready.** The owner selected the synthetic-fixture Principal for strictly local validation on approved public datasets only; this is not production authentication. The production CLI policy source still returns `None` and denies before snapshot bytes are opened. The direct engine path still needs an opaque, exact-type Principal-bound receipt scoped to project/import/binding/dataset/schema/manifest/scenario and expiry, verified before any Store/provenance/population side effect. The only explicit owner approval under `agora/sim/**` remains `agora/sim/engine.py`; do not edit another `agora/sim/**` path without separate written approval.
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

Claude's 09:05 IST reachability check reports FiveThirtyEight GitHub data fetchable, while Harvard Dataverse, Kaggle and Ember's official host were blocked by the workspace allowlist. Candidate MEDSL V20 and Ember GitHub mirrors remain unapproved substitutions; owner approval must identify the exact repository, commit, path, release and licence. M5 remains owner-supplied via Kaggle and its competition terms.

The owner relayed a partial FiveThirtyEight import in private `Post2Drive/Post2Drive` PR #5: import commit `15c9a053291925813ef568466a92fc5460f6b554`, source commit `4c1ff5e3aef1816ae04af63218015066e186c147`. The README/licence and complete `old_model/` folder were reported present; four large CSVs remain outstanding and no per-file SHA-256 manifest is recorded. The acquisition checklist records exact reported filenames and byte sizes. This handoff has not been independently verified and does not establish complete coverage, licence approval or permission to run.

Do not begin any import or run until the complete per-file manifest (exact file/path, byte size, SHA-256, source commit/release, licence/version, URL and citation) is committed in the owner-controlled private repository and reconciled against the frozen split. Retain the full polling window only if all required files and hashes arrive and the corrected 2024 general asset is verified. If that corrected asset is unavailable after the prescribed single live-URL attempt, use the separate 2000–2016 fallback in section 2.1; no silent narrowing, uncorrected-file substitution or mirror substitution. The protocol remains draft/unfrozen; no dataset has been run or approved.
## 9. Sources

- FiveThirtyEight polls data repository and file index: https://github.com/fivethirtyeight/data/tree/master/polls
- FiveThirtyEight repository licence: https://github.com/fivethirtyeight/data
- MIT Election Data and Science Lab, County Presidential Election Returns 2000–2024, Harvard Dataverse DOI: https://doi.org/10.7910/DVN/VOQCHQ
- M5 Forecasting — Accuracy official dataset page and competition terms: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Ember Monthly EV Sales Data and methodology: https://ember-energy.org/data/monthly-ev-sales-data/

**No dataset was downloaded, imported, run or evaluated while drafting this protocol. No validation result is claimed.**

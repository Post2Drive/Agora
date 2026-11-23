# Validation Protocol — Three Public Benchmark Packages

**Status:** Draft preregistration only; not frozen and not approved for execution. No dataset has been run through AGORA. The selected election draft window is now 2000–2016 (training 2000/2004/2008, validation 2012, held-out test 2016), chosen by Claude under the owner's "you choose" delegation; this replaces the conditional 2000–2016 fallback and excludes 2020/2024. The 2024 general-average file in P2D PR #5 is explicitly uncorrected and excluded. The poll source `pres_pollaverages_1968-2016.csv` contains daily publisher state-level averages, not individual polls or sample sizes; the default baseline is the latest same-state/office published average on or before each cutoff, with previous-election state-margin persistence reported separately. FiveThirtyEight PR #5 remains open/draft/unmerged at P2D branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d`; its 12 CSVs total 94,181,506 bytes, and its 4,679-byte manifest file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude reports all 12 source/committed-destination and Windows checkout hashes match. The owner explicitly approved exact MEDSL and Ember mirrors in the latest Claude entry; Claude reports their SHA-256 values verified in its workspace: MEDSL V20.0, 10,222,208 bytes, `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, CC0 1.0; Ember 16-Nov-2026 snapshot, 7,695,642 bytes, `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0. ChatGPT inspected public GitHub trees and metadata only, not raw dataset bytes, and did not independently reproduce these hashes. The MEDSL/Ember raw files remain in Claude's workspace, not P2D or Agora. M5 is the only remaining owner download/terms decision (acquire under Kaggle terms or drop retail). The complete all-package manifest is not committed. The five owner-approved protocol values remain effective only after merge and a complete freeze sentence; the received sentence contains literal `<sha>`. The owner-named evaluator's restricted scope, output custody and label-release boundary are not established. The one-run approval remains dormant. No validation result or M3 completion is claimed.

**Baseline:** main `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026). #197 RT06 read-side snapshots, #198 Principal-bound receipt, #199 adapter-origin guard and docs #196 are merged; their exact-head CI runs `45167913607`, `45170449040`, `45173316190` and `45170530846` each passed 4/4. The read-side SQLite limitation, in-process receipt limitations and production CLI default-deny remain as documented below. P2D PR #5 is open/draft/unmerged at `b06b29cb2071f048f0c234f65c1014ea4677d33d`; its 12-file FiveThirtyEight sub-manifest SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. Claude reports the owner-approved MEDSL and Ember mirror hashes and byte counts verified at exact commits `1358bc6047f0c22989d37fa64ac03ee755bd17e7` and `2c21f1edced7aae884314ebc28c89ab212f30563`; these raw files are not in P2D/Agora. The selected 2000–2016 polls window, MEDSL mode rule and 16-Nov Ember snapshot label are specified below. M5 remains pending owner choice; the complete all-package manifest is not committed. The protocol remains draft; no run is authorized.

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


## 2.1 Bias controls and evaluator rule — owner-approved design, effective at freeze

These controls reflect the owner's 23 November design delegation and explicit acceptance of Claude's A–D design decisions. The owner separately confirmed that the synthetic-fixture Principal is acceptable for strictly local validation on approved public datasets only; the production CLI remains blocked. The owner also approved the five fixed values listed in point 6 below. These are **owner-approved design choices, effective only when merged into this protocol and covered by a complete freeze sentence**; they are not a protocol freeze or run authorization. Within `agora/sim/**`, the only authorized path remains `agora/sim/engine.py`; no additional `agora/sim/**` path is authorized. No dataset acquisition, import, simulation or validation is authorized by this approval.

| Package | Fixed time split / cutoffs | Naive baseline | Metrics to report | Uncertainty for every metric | Stop rule |
|---|---|---|---|---|---|
| E — FiveThirtyEight 2000–2016 averages + MEDSL returns | Training: 2000/2004/2008; validation: 2012; held-out test: 2016. Election Days/cutoffs: 2000-11-07 (10-10/10-24/10-31); 2004-11-02 (10-05/10-19/10-26); 2008-11-04 (10-07/10-21/10-28); 2012-11-06 (10-09/10-23/10-30); 2016-11-08 (10-11/10-25/11-01). Only publisher averages dated on/before each cutoff are eligible. | Latest same-state/office FiveThirtyEight publisher average on/before cutoff (primary); previous-election state-margin persistence (separate secondary). No sample-size-weighted 28-day poll mean from the averages file. | MAE (primary), RMSE (secondary), Brier only for genuine probabilities; report state/cutoff coverage and per-state errors. | 95% cluster/block-bootstrap for every estimable metric, resampling states and pollsters only where source supports it; report cluster counts. | Stop on missing same-state/office/date coverage, ambiguous MEDSL mode handling, or output-target mismatch. 2020/2024 are out of window; never use the uncorrected 2024 file. |
| R — M5 Walmart sales | Training d_1–d_1857; validation d_1858–d_1885; held-out test d_1886–d_1913; reserve d_1914–d_1941 stays sealed and unused. Resolve the reserve against the exact sales_train_evaluation.csv and Kaggle terms before freeze. | Seasonal-naive: repeat each series' corresponding weekday from t-7. | WRMSSE (primary), WAPE and RMSSE (secondary), with hierarchy/category/store breakdowns and explicit zero-scale handling. | 95% block-bootstrap interval for every estimable metric, resampling store/item series and preserving the 28-day horizon block. If the engine emits no prediction range, report metric uncertainty only; do not fabricate predictive intervals. | Stop if the pinned calendar/day mapping or file bundle differs, the reserve labels are not protected, Kaggle terms do not permit intended use, or no exact item/store/day target can be emitted. |
| A — Ember monthly EV (16-Nov-2026 snapshot) | Training through 2022-12; validation 2023-01–2023-12; held-out test 2024-01–2025-12. Use monthly rows only; exclude quarterly observations and regional aggregates. Freeze the eligible-country list before test labels are opened. | Last-value: carry forward the last observed monthly registration for the same country across the forecast horizon. | WAPE (primary) for monthly registrations; MAE in percentage points (secondary) for EV share. Report aggregate and per-country coverage/results. | 95% block-bootstrap interval for every estimable metric, resampling countries as clusters and contiguous 12-month blocks within each country. | Stop if monthly frequency/definitions are inconsistent, source revisions mix versions, eligible-country coverage fails, or AGORA cannot emit the exact declared registration/share target. Label the file 16-Nov snapshot, not the 18-Nov update. |

**LLM sampling (owner-approved 23 November; effective at freeze):** temperature 0; cache on. Pin the model/backend/version and remaining generation parameters in the frozen run configuration.

### Bias controls

1. **Predeclare the split.** Fix every time split and cutoff before any run. No moving cutoffs after seeing outcomes.
2. **Baseline every result.** Report every loss metric alongside its dataset-specific naive baseline on the exact same eligible observations. Include AGORA loss, baseline loss and the signed difference, with direction and units. Never report an AGORA loss without its baseline.
3. **Seal the test period.** Keep held-out test labels sealed until outputs and their hashes are frozen. No prompt, scenario, parameter, mapping, feature, model or threshold tuning on test outcomes. Any validation-based tuning must be confined to the declared validation window, limited to the preregistered search space, recorded in run records and frozen before test labels are released.
4. **One run per frozen configuration.** Use one run per frozen configuration and preregistered seed. Do not select a favourable rerun or seed. A failed, denied, interrupted or invalid attempt remains in the register. Any additional seed/configuration must be separately preregistered before outcomes are seen.
5. **Uncertainty for every metric.** Report a 95% uncertainty range and sample/cluster count for every metric where estimable, using the package-specific resampling unit above. If not estimable, state that explicitly rather than omit it or replace it with a narrower interval.
6. **Owner-approved uncertainty and sampling values — effective at freeze.** On 23 November the owner approved bootstrap B=2000, bootstrap RNG seed 20261123, percentile interval construction, one preregistered seed per configuration, and LLM temperature 0 with cache on. Record these values in the frozen configuration. Confirm the resampling unit, replacement policy, sparse-cluster handling and implementation version in the merged protocol. These approved values are not effective until this protocol is merged and the owner freeze sentence names the actual complete manifest SHA; the received sentence still contains literal `<sha>`.
7. **Write stop rules first.** Each package's stop rule in the table is frozen before the first run; missing files, incompatible target units, unresolved licences, sparse clusters or missing labels stop the package rather than trigger a proxy or substitution.
8. **No outcome-led changes.** No post-hoc exclusions, proxy targets, source substitutions, split changes, metric switching or outcome-informed scenario revisions. A changed choice requires a new protocol version and approval before another run.

### Independent evaluator rule

The evaluator must be a **separate person or process** that sees only (1) this frozen protocol, (2) the committed dataset manifest, and (3) the raw outputs. The evaluator must not change or amend the protocol after seeing results. Preserve the evaluator identity/process version and the exact protocol, manifest and raw-output hashes with the evaluation record. Evaluator identity and custody arrangements must be named before protocol freeze. The evaluator does not get authority to change source approvals, run scope, prediction flags or owner gates.

## 3. Approved benchmark packages

The owner-approved domains are election results and polls, retail sales (M5 Walmart or Rossmann), and public adoption series (UPI or EV registrations). This draft selects the following concrete packages for review. Substitution is not automatic; any replacement must be named and approved before protocol freeze.

### Package E — FiveThirtyEight 2000–2016 Published State Averages paired with MEDSL County Presidential Election Returns

**Purpose:** time-ordered published-average-to-election comparison. FiveThirtyEight's daily state-level averages are predictors; MEDSL county returns are the outcome source. The selected evaluation window is five elections from 2000 through 2016.

**Sources and terms**

- Polls: FiveThirtyEight `polls/pres_pollaverages_1968-2016.csv` at commit `4c1ff5e3aef1816ae04af63218015066e186c147`, CC BY 4.0. This is the publisher's daily state-level average series, not individual poll records and not a source of poll-level sample sizes. Preserve attribution and exact file/version/hash. Source: https://github.com/fivethirtyeight/data/tree/4c1ff5e3aef1816ae04af63218015066e186c147/polls
- Outcomes: MIT Election Data and Science Lab, **County Presidential Election Returns 2000–2024**, Harvard Dataverse DOI https://doi.org/10.7910/DVN/VOQCHQ, Version 20.0, CC0 1.0. The owner approved the exact mirror `mathis-group/cas-201-data-project` commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7`, file `data/medsl/countypres_2000-2024.csv` (10,222,208 bytes; Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`). The mirror repo's MIT licence covers code only; the dataset remains CC0 1.0 per its data README. Cite the original Dataverse dataset as required.

**Candidate fields to inspect and allow-list**

- Poll averages: state/geography, date, candidate, published average and source-defined margin/trend fields actually present. Do not expect poll ID, pollster or sample-size fields in this averages series; do not infer individual-poll records.
- Results: election year, state/state code, county ID/FIPS, candidate, party, candidate votes, total votes, `mode` and dataset version. Mode rule: use the `TOTAL` row where present; otherwise sum the available mode rows. Never sum a `TOTAL` row with component modes. Claude reports 2024 contains both `TOTAL` and mode rows, so naïve summation double-counts; 2024 is outside the selected 2000–2016 window.
- Exclude pollster free-text notes, respondent-level data if encountered, personal data, any post-election field and fields calculated using future results.
- Aggregate county returns to state-level two-party vote share using a deterministic documented grouping; independently reconcile aggregate totals to source totals. Exclude territories and any state/office/contest that cannot be matched unambiguously.

**Time split**

- Training/calibration election cycles: 2000, 2004 and 2008.
- Validation cycle: 2012.
- Held-out test cycle: 2016.
- For each election cycle, freeze forecast cutoffs at 28, 14 and 7 calendar days before Election Day. Use only publisher-average records dated on or before cutoff; exclude later averages and any derived field published after cutoff. Election Days/cutoffs: 2000-11-07 (10-10, 10-24, 10-31); 2004-11-02 (10-05, 10-19, 10-26); 2008-11-04 (10-07, 10-21, 10-28); 2012-11-06 (10-09, 10-23, 10-30); 2016-11-08 (10-11, 10-25, 11-01).
- The 2016 outcome labels remain sealed until predictions and output hashes are frozen. The 2020 and 2024 cycles are outside this selected draft window. Do not use the uncorrected 2024 general-average asset as corrected data or silently reintroduce 2020/2024; any later window change requires a versioned protocol amendment before freeze.

**Target and metrics**

- Target: state-level two-party margin (percentage points) at the election result.
- Primary metric: mean absolute error (MAE) in percentage points across eligible state/cutoff pairs.
- Secondary metrics: root mean squared error (RMSE) and, only if the engine emits a genuine probability, Brier score for state winner.
- Report coverage (number and share of states with a valid output) beside every metric. No post-hoc state exclusions.

**Naive baseline**

- Primary baseline (default, option a): use the latest FiveThirtyEight published daily state-level average for the same state and office dated on or before the cutoff. `pres_pollaverages_1968-2016.csv` contains publisher averages, not individual polls or sample sizes; do not calculate a sample-size-weighted 28-day mean from it.
- Report missing coverage when no exact state/office/cutoff average exists; do not substitute an election result, a later/current-cycle average or a different office/window.
- Report previous-election state-margin persistence as a separate secondary baseline.
- Option b (a sample-size-weighted poll-level mean using individual-poll files) is not selected. Attempt the live `president_polls_historical.csv` links only if the owner explicitly asks Claude to do so; record access success/failure and amend/version this draft before freeze.
- If no eligible publisher average exists for a state/cutoff, report missing coverage; do not impute after seeing the result.
- The previous-election state-margin persistence baseline is reported separately from the latest-publisher-average baseline.

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

### Package A — Ember Monthly EV Sales Data (16-Nov-2026 snapshot)

**Purpose:** monthly public adoption/market-share time series for battery-electric and plug-in-hybrid passenger cars.

**Source and terms**

- Ember, **Monthly EV Sales Data**, source file `monthly_ev_sales.csv`, 16-Nov-2026 snapshot (not the 18-Nov update). The owner approved mirror `Awes0mer/fuel-cars-pollution` at commit `2c21f1edced7aae884314ebc28c89ab212f30563`, path `data/raw/ember_ev_monthly/monthly_ev_sales.csv` (7,695,642 bytes; Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`). The mirror manifest points to Ember's official CSV URL and CC BY 4.0 data licence. The mirror repo's MIT licence applies to code only. Claude reports 46,799 rows spanning monthly and quarterly records, 2005-01 to 2026-10, 59 countries; use monthly rows only.
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
| E — FiveThirtyEight 2000–2016 averages + MEDSL V20.0 | FiveThirtyEight `polls/pres_pollaverages_1968-2016.csv` at `4c1ff5e3aef1816ae04af63218015066e186c147`; MEDSL `data/medsl/countypres_2000-2024.csv` at mirror commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7` | FiveThirtyEight CC BY 4.0; MEDSL dataset CC0 1.0 (mirror repo MIT applies to code only) | State/date/average fields; county returns and mode; exclude free text and out-of-window cycles | 12 FiveThirtyEight hashes in P2D PR #5; MEDSL 10,222,208 bytes, Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8` | No — raw MEDSL file only in Claude workspace; complete private manifest pending |
| R — M5 Walmart | TBD | Subject to Kaggle Competition Rules; explicit review required | TBD | TBD | No |
| A — Ember Monthly EV Sales (16-Nov-2026 snapshot) | `data/raw/ember_ev_monthly/monthly_ev_sales.csv` at mirror commit `2c21f1edced7aae884314ebc28c89ab212f30563` | CC BY 4.0 for data (mirror repo MIT applies to code only) | Country/economy monthly rows only; exclude quarterly and regional aggregates | 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2` | No — raw file only in Claude workspace; complete private manifest pending |

## 8.1 Freeze-blocking review findings

This review is documentation-only. The protocol remains **Draft 0.1**, is not frozen, and has not been approved for execution. Resolve each item in a versioned revision before any effective owner freeze decision:

1. **Run-count and randomness contract is partly owner-approved, not yet frozen.** The owner approved one run per frozen configuration, B=2000, bootstrap RNG seed 20261123, percentile intervals, one preregistered seed per configuration and LLM temperature 0 with cache on. These values are effective only after they appear in the merged protocol and the owner supplies the complete freeze sentence. Confirm the remaining replacement, sparse-cluster and deterministic-backend settings before freeze.
2. **FiveThirtyEight, MEDSL and Ember source evidence is now partially pinned; private staging and M5 decision remain.** P2D main `5c8787a410a1aacaa9be9933b1c725a0b12e9689` has no raw benchmark files. Open/draft/unmerged P2D PR #5 at `b06b29cb2071f048f0c234f65c1014ea4677d33d` contains 12 FiveThirtyEight CSVs (94,181,506 bytes) and a 12-row manifest pinned to `4c1ff5e3aef1816ae04af63218015066e186c147`, CC BY 4.0; Claude reports source/committed-destination and Windows checkout hashes match. The 4,679-byte manifest file SHA-256 is `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`. The owner approved MEDSL mirror `mathis-group/cas-201-data-project@1358bc6047f0c22989d37fa64ac03ee755bd17e7`, path `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, dataset licence CC0 1.0. The owner approved Ember mirror `Awes0mer/fuel-cars-pollution@2c21f1edced7aae884314ebc28c89ab212f30563`, path `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, data licence CC BY 4.0 and 16-Nov snapshot label. Claude reports both raw files fetched/verified in its workspace only; ChatGPT inspected public GitHub tree/README/codebook/manifest metadata, not raw bytes, and did not independently reproduce hashes. Neither mirror file is in P2D or Agora. The selected election window is 2000–2016; 2020/2024 are out of scope and the uncorrected 2024 file is excluded. M5 is the only remaining owner download/terms decision (acquire under Kaggle rules or drop retail). The complete all-package manifest remains uncommitted; pin exact versions, paths, bytes, hashes, licences and observed headers before freeze.
3. **M5 file/split alignment needs a source-file check.** The stated `d_1914`–`d_1941` reserve requires `sales_train_evaluation.csv`; reconcile it against the exact Kaggle bundle and competition terms. Do not acquire or use M5 until the owner reviews and accepts those terms.
4. **Output-target compatibility is unproven.** The current projection converts tabular rows into social-simulation segment parameters; the three benchmarks require election-margin, item/store/day sales, or country/month registration outputs. A package is not evaluable unless a deterministic, predeclared mapping exists without post-hoc proxy conversion. Do not run the engine to discover a mapping under this draft.
5. **Uncertainty procedures need executable parameters.** The owner approved B=2000, seed 20261123 and percentile intervals. Confirm sampling units, replacement policy, sparse-cluster handling and exact implementation/version in the merged protocol before freeze. If an interval is not estimable, report that rather than omit it.
6. **Evaluator custody is named but not established.** The owner named ChatGPT as a separate-process evaluator restricted to the frozen protocol, committed manifest and raw outputs. The owner must establish the evaluator's restricted access to only the frozen protocol, committed manifest and raw outputs; output custody; immutable output hashes; and proof that outputs were frozen before labels were released. The name alone is not a completed custody arrangement.
7. **Licence and privacy review must be per-file.** M5 Competition Rules require owner review before acquisition/use. For every package, inspect headers and a controlled sample locally for identifiers, free-text fields and sensitive data; record only the inspection outcome and exclude disallowed fields.
8. **Identity/policy implementation remains non-operational.** #198/#199 merge a Principal-bound receipt and adapter-origin marker, but `_ISSUED` and `_MINT` remain accessible in-process; the public receipt constructor accepts `_MINT`, and `object.__setattr__` bypasses the setter. The fixture adapter accepts caller-supplied fixtures and is test-only. There is no production identity adapter; the CLI's `_governed_policy()` remains `None` and denies before snapshot bytes. Keep this default-deny behaviour.
9. **Read/write path race coverage is incomplete.** #197 adds held-descriptor read-side snapshots for chain, anchor and seal verification. `AuditChainStore` writer opens remain path-based; Python <3.11 fails closed rather than reopening by path. Do not claim full read/write TOCTOU resistance.
10. **Provenance/report completeness remains to be verified.** #178 pins distinct original `base_scenario_hash` and projection-bound `projected_scenario_hash`, alongside row-bound `instances_hash` and mapping/projection hashes. Verify reports/exports expose both scenario hashes and required provenance with the exploratory label.

The owner's freeze sentence received 23 November names evaluator ChatGPT but uses the literal `<sha>` placeholder for the dataset manifest. It is incomplete and is not a freeze. The owner's one-run approval is received but dormant. No protocol change here authorizes dataset import, simulation or validation.


## 8. Preregistration record

| Field | Value |
|---|---|
| Protocol version | Draft 0.1 |
| Protocol commit SHA | Not yet frozen |
| M2 confirmation entry | Claude confirmed 23:43 IST, 22 November 2026; link exact log entry at freeze |
| M3 confirmation entry | Pending Claude; implementation slices alone do not establish M3 reached |
| Dataset register SHA | Not supplied; owner freeze sentence contains literal `<sha>` placeholder |
| Repository SHA | TBD |
| M3 adapter SHA/version | TBD |
| Python/runtime/dependency lock | TBD |
| Scenario/configuration hashes | TBD |
| Model/backend/version and parameters | LLM temperature 0 and cache on (owner-approved 23 Nov; effective at freeze); model/backend/version and remaining generation parameters TBD |
| Random seeds and number of runs | One preregistered seed per configuration (owner-approved 23 Nov; exact seed/configuration list must be frozen) |
| Evaluation script SHA | TBD |
| Independent evaluator | ChatGPT, owner-named separate process; restricted scope, output custody and label-release procedure still to be established |
| Dataset-specific owner approval references | 12:52 IST named approval; 23 Nov owner "Approve both" for exact MEDSL/Ember mirror commits (recorded in Claude's 21:30 entry); Claude's delegated 2000–2016 window choice; confirm scope at freeze |
| First run date | Not scheduled |
| Validation results | None recorded in this draft |

## 8.2 Acquisition reachability and mirror approval

The latest Claude log records owner approval of the exact MEDSL and Ember mirrors and reports that both files were fetched and SHA-256 verified in Claude's workspace. ChatGPT's connector review confirmed the public GitHub repository commits, exact paths, sizes and metadata files, but did not download raw CSV bytes or independently reproduce the reported hashes.

Read-only GitHub inspection confirms private `Post2Drive/Post2Drive` PR #5 is open/draft/unmerged at branch head `b06b29cb2071f048f0c234f65c1014ea4677d33d` and stages only the 12 FiveThirtyEight CSVs plus their 4,679-byte manifest (SHA-256 `bd7434240765c1d368bd0874f84e4290a40e677751d5448d5c7cbe42996925cb`), pinned to source commit `4c1ff5e3aef1816ae04af63218015066e186c147`, CC BY 4.0. Claude reports those 12 source/committed-destination and Windows checkout hashes match. The owner-approved MEDSL mirror is `mathis-group/cas-201-data-project` commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7`, path `data/medsl/countypres_2000-2024.csv`, 10,222,208 bytes, Claude-reported SHA-256 `9299583148f5f8264baf50b5d929c260699c46d915909b13ea3c3850918946f8`, dataset CC0 1.0 (mirror repo MIT applies to code only). The owner-approved Ember mirror is `Awes0mer/fuel-cars-pollution` commit `2c21f1edced7aae884314ebc28c89ab212f30563`, path `data/raw/ember_ev_monthly/monthly_ev_sales.csv`, 7,695,642 bytes, Claude-reported SHA-256 `76e241d07d2086477ef0279d4ce20cd6a02c7869b5152ecc016bf132d2734fb2`, CC BY 4.0 data (mirror repo MIT applies to code only); label it 16-Nov-2026 snapshot, not 18-Nov update. Claude reports both raw mirror files fetched and verified in its workspace only; ChatGPT inspected public GitHub tree/README/codebook/manifest metadata, not raw data bytes, and did not independently reproduce hashes. Neither mirror file is committed to P2D or Agora. The 2000–2016 poll window excludes 2020/2024; the uncorrected 2024 general-average file is not used. M5 remains the only pending owner download/terms decision (acquire under Kaggle rules or drop retail). The complete all-package manifest is not yet committed.

The owner named ChatGPT as a separate-process evaluator restricted to the frozen protocol, manifest and raw outputs; the evaluator's restricted scope, output custody and label-release boundary are not established. The owner freeze sentence includes a literal `<sha>` placeholder and is not effective. Do not begin import or run until the complete per-file manifest is committed in the owner-controlled private repository, the exact package files and licences are accepted, the M5 acquire-or-drop decision is resolved, the protocol parameters are frozen in a merged commit, and the owner re-pastes the freeze sentence with the actual protocol and complete manifest SHAs. The MEDSL and Ember mirrors are owner-approved, but their raw files remain only in Claude's workspace and are not staged in P2D. No dataset has been run.
## 9. Sources

- FiveThirtyEight polls data repository and file index: https://github.com/fivethirtyeight/data/tree/master/polls
- FiveThirtyEight repository licence: https://github.com/fivethirtyeight/data
- Owner-approved MEDSL mirror at commit `1358bc6047f0c22989d37fa64ac03ee755bd17e7` and source DOI https://doi.org/10.7910/DVN/VOQCHQ (V20.0, dataset CC0 1.0; mirror repo MIT applies to code only).
- Owner-approved Ember mirror at commit `2c21f1edced7aae884314ebc28c89ab212f30563`; 16-Nov-2026 snapshot, data CC BY 4.0: https://github.com/Awes0mer/fuel-cars-pollution/tree/2c21f1edced7aae884314ebc28c89ab212f30563/data/raw/ember_ev_monthly
- MIT Election Data and Science Lab, County Presidential Election Returns 2000–2024, Harvard Dataverse DOI:
- M5 Forecasting — Accuracy official dataset page and competition terms: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Ember Monthly EV Sales Data and methodology: https://ember-energy.org/data/monthly-ev-sales-data/

**No dataset was downloaded, imported, run or evaluated while drafting this protocol. No validation result is claimed.**

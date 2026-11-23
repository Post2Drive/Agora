# Validation Protocol — Three Public Benchmark Packages

**Status:** Draft preregistration only. This document is not frozen and has not been approved as an execution protocol. No dataset has been run through AGORA. On 23 November the owner approved five design values: bootstrap B=2000, bootstrap RNG seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on. These values become effective only after they are merged into this protocol and the owner supplies a complete freeze sentence naming the actual manifest SHA. The received sentence contains the literal `<sha>` placeholder and is not effective. The per-file manifest and several benchmark files are still missing. The owner named ChatGPT as a separate-process evaluator, but private-repository access and label/output custody are not established. The one-run approval is received but dormant. Do not report validation results or claim M3 reached.

**Baseline:** main `4a0607f8946e32ef828b47183099ead4f8ae2bd7` (23 November 2026). RT06 #197 merged at exact head `5d67cb4ceed8200a9a952b05ae1db9a58c3b0ba6`, merge `5cbe4cfbb82039543d408ab5c67e045e17e10a99`, exact-head CI `45167913607` passed 4/4; it hardens read-side SQLite snapshots, while AuditChainStore writers remain path-based and Python <3.11 fails closed. Principal-bound receipt #198 merged at exact head `d3a8435bbabc28a1e488d87b752b1350b99c687d`, merge `4a55f2efd44da7aea54adda6ca7787471dd97cba`, exact-head CI `45170449040` passed 4/4. Adapter-origin guard #199 merged at exact head `851bbf1a217f018695133ee9c42f1c538fa088f0`, merge/current main `4a0607f8946e32ef828b47183099ead4f8ae2bd7`, exact-head CI `45173316190` passed 4/4. Docs PR #196 merged at exact head `f9d34afa5914ee1cd2ccfd39a722fbb791ac4591`, merge `34e5cc39b2bb9f53ca6be0dc057de53e5aa5532c`, exact-head CI `45170530846` passed 4/4 (seven docs-only paths). The synthetic fixture remains test-only: `_ISSUED`/`_MINT` are reachable in-process, `object.__setattr__` bypasses receipt immutability, and the adapter accepts caller-supplied fixture definitions. No production identity adapter exists; `_governed_policy()` remains `None` and the CLI denies before snapshot bytes. The owner-reported dataset handoff is partial and no complete per-file SHA-256 manifest is available. The owner-approved 23 November design values are B=2000, bootstrap seed 20261123, percentile interval, one preregistered seed per configuration, and LLM temperature 0 with cache on. They take effect only when merged into this protocol and covered by a complete owner freeze sentence. The protocol remains draft; no run is authorized.

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
| E — FiveThirtyEight polls + MEDSL returns | Full window: training cycles 2008, 2012, 2016; validation: 2020; held-out test: 2024. For each cycle, use only polls ending on or before 28-, 14- and 7-day cutoffs. Election Days and cutoffs: 2008-11-04 (10-07, 10-21, 10-28); 2012-11-06 (10-09, 10-23, 10-30); 2016-11-08 (10-11, 10-25, 11-01); 2020-11-03 (10-06, 10-20, 10-27); 2024-11-05 (10-08, 10-22, 10-29). **Conditional fallback if the corrected 2024 general asset is unavailable after its single prescribed live-URL attempt:** a separate preregistration with training cycles 2000/2004/2008, validation 2012 and held-out test 2016; cutoffs must be fixed at the same 28/14/7-day offsets for each election (2000-11-07: 10-10/10-24/10-31; 2004-11-02: 10-05/10-19/10-26; 2008-11-04: 10-07/10-21/10-28; 2012-11-06: 10-09/10-23/10-30; 2016-11-08: 10-11/10-25/11-01). Do not mix the full and fallback windows or silently change splits. | Prior-election sample-size-weighted poll-average margin for the same state and office at the matching 28/14/7-day cutoff, calculated only from polls available by that prior-cycle cutoff. If a comparable prior-cycle poll average is not available for a state/cutoff, report missing baseline coverage; do not substitute an election result, current-cycle average or a different office/window. | MAE (primary), RMSE (secondary), and Brier score only if the engine emits a genuine probability. Report state/cutoff coverage and per-state errors. | 95% cluster/block-bootstrap interval for every estimable metric, resampling states as clusters and pollsters within state only where source fields support it. Report cluster count; mark not estimable if too few independent clusters. | Stop if pinned sources do not provide required pre-cutoff coverage or a comparable last-election poll-average baseline, state/office matching is ambiguous, or AGORA cannot emit the exact state-level margin/probability without a post-hoc proxy. Never substitute uncorrected 2024 averages for corrected 2024 polls. |
| R — M5 Walmart sales | Training d_1–d_1857; validation d_1858–d_1885; held-out test d_1886–d_1913; reserve d_1914–d_1941 stays sealed and unused. Resolve the reserve against the exact sales_train_evaluation.csv and Kaggle terms before freeze. | Seasonal-naive: repeat each series' corresponding weekday from t-7. | WRMSSE (primary), WAPE and RMSSE (secondary), with hierarchy/category/store breakdowns and explicit zero-scale handling. | 95% block-bootstrap interval for every estimable metric, resampling store/item series and preserving the 28-day horizon block. If the engine emits no prediction range, report metric uncertainty only; do not fabricate predictive intervals. | Stop if the pinned calendar/day mapping or file bundle differs, the reserve labels are not protected, Kaggle terms do not permit intended use, or no exact item/store/day target can be emitted. |
| A — Ember monthly EV | Training through 2022-12; validation 2023-01–2023-12; held-out test 2024-01–2025-12. Freeze the eligible-country list before test labels are opened. | Last-value: carry forward the last observed monthly registration for the same country across the forecast horizon. Do not use future months or revise the baseline after seeing test outcomes. | WAPE (primary) for monthly registrations; MAE in percentage points (secondary) for EV share. Report aggregate and per-country coverage/results. | 95% block-bootstrap interval for every estimable metric, resampling countries as clusters and contiguous 12-month blocks within each country. Mark uncertainty not estimable when cluster count is inadequate. | Stop if monthly frequency/definitions are inconsistent, source revisions mix versions, eligible-country coverage fails, or AGORA cannot emit the exact declared registration/share target. |

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

This review is documentation-only. The protocol remains **Draft 0.1**, is not frozen, and has not been approved for execution. Resolve each item in a versioned revision before any effective owner freeze decision:

1. **Run-count and randomness contract is partly owner-approved, not yet frozen.** The owner approved one run per frozen configuration, B=2000, bootstrap RNG seed 20261123, percentile intervals, one preregistered seed per configuration and LLM temperature 0 with cache on. These values are effective only after they appear in the merged protocol and the owner supplies the complete freeze sentence. Confirm the remaining replacement, sparse-cluster and deterministic-backend settings before freeze.
2. **Exact source assets, hashes and field names are not pinned.** The owner reports a partial FiveThirtyEight private-repository import: eight `old_model/*.csv` files plus README/licence are reported present, but four large CSVs remain outstanding and no per-file SHA-256 manifest is recorded. Election, retail and adoption source files also lack a complete verified per-file manifest. Pin exact immutable source versions, filenames, bytes, SHA-256, licence and observed headers; do not treat owner-reported metadata or Git blob IDs as raw-file SHA evidence.
3. **M5 file/split alignment needs a source-file check.** The stated `d_1914`–`d_1941` reserve requires `sales_train_evaluation.csv`; reconcile it against the exact Kaggle bundle and competition terms. Do not acquire or use M5 until the owner reviews and accepts those terms.
4. **Output-target compatibility is unproven.** The current projection converts tabular rows into social-simulation segment parameters; the three benchmarks require election-margin, item/store/day sales, or country/month registration outputs. A package is not evaluable unless a deterministic, predeclared mapping exists without post-hoc proxy conversion. Do not run the engine to discover a mapping under this draft.
5. **Uncertainty procedures need executable parameters.** The owner approved B=2000, seed 20261123 and percentile intervals. Confirm sampling units, replacement policy, sparse-cluster handling and exact implementation/version in the merged protocol before freeze. If an interval is not estimable, report that rather than omit it.
6. **Evaluator custody is named but not established.** The owner named ChatGPT as a separate-process evaluator restricted to the frozen protocol, committed manifest and raw outputs. The owner must establish private-repository access, output/label custody, immutable output hashes and proof that outputs were frozen before labels were released. The name alone is not a completed custody arrangement.
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
| Independent evaluator | ChatGPT, owner-named separate process; private-repository access and label/output custody still to be established |
| Dataset-specific owner approval references | 12:52 IST named approval; confirm scope at freeze |
| First run date | Not scheduled |
| Validation results | None recorded in this draft |

## 8.2 Acquisition reachability and mirror approval

The only direct host-reachability evidence remains Claude's 09:05 IST check: FiveThirtyEight GitHub was reachable, while Harvard Dataverse, Kaggle and Ember's official host were blocked by the workspace allowlist. Later collaboration-log entries are handoff/status updates, not new network tests. Candidate MEDSL V20 and Ember GitHub mirrors remain unapproved substitutions; owner approval must identify the exact repository, commit, path, release and licence. M5 remains owner-supplied via Kaggle and its competition terms.

The owner reports a partial FiveThirtyEight import in private `Post2Drive/Post2Drive` PR #5, import commit `15c9a053291925813ef568466a92fc5460f6b554`, source commit `4c1ff5e3aef1816ae04af63218015066e186c147`: README/licence and eight `old_model/*.csv` files are reported present; four large CSVs remain outstanding. No per-file SHA-256 manifest is recorded. The private repository and raw bytes were not inspected through the permitted connector. The exact MEDSL, M5 and Ember files, source versions and licence records also remain to be supplied and verified.

The owner named ChatGPT as a separate-process evaluator restricted to the frozen protocol, manifest and raw outputs; private-repository access and label/output custody are not established. The owner freeze sentence includes a literal `<sha>` placeholder and is not effective. Do not begin import or run until the complete per-file manifest is committed in the owner-controlled private repository, the exact package files and licences are verified, the protocol parameters are frozen in a merged commit, and the owner re-pastes the freeze sentence with the actual protocol and manifest SHAs. No mirror is approved; no dataset has been run.
## 9. Sources

- FiveThirtyEight polls data repository and file index: https://github.com/fivethirtyeight/data/tree/master/polls
- FiveThirtyEight repository licence: https://github.com/fivethirtyeight/data
- MIT Election Data and Science Lab, County Presidential Election Returns 2000–2024, Harvard Dataverse DOI: https://doi.org/10.7910/DVN/VOQCHQ
- M5 Forecasting — Accuracy official dataset page and competition terms: https://www.kaggle.com/c/m5-forecasting-accuracy/data
- Ember Monthly EV Sales Data and methodology: https://ember-energy.org/data/monthly-ev-sales-data/

**No dataset was downloaded, imported, run or evaluated while drafting this protocol. No validation result is claimed.**

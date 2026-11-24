# Validation Protocol v1.0 — 2020 Confirmatory Election Holdout (DRAFT)

**Status:** Draft for owner/technical review only. Not frozen, not approved for data acquisition, import, execution, evaluation or label release. No 2020 polling file has been downloaded for this protocol. This document is a prospective, separately versioned follow-on; it does not amend the frozen v0.1 protocol, the frozen v0.2 run specification, or the 15-row v0.2 dataset manifest. It is not M3 completion evidence.

**Owner direction reported in Claude's latest 24 November 2026 log entry:** exploratory analysis now, 2020 confirmatory holdout later; fundamentals kept minimal (incumbent party and previous-election state result only); no new data/download and no prediction-flag change in that instruction. The owner accepted that a tie or loss is a valid result and that the benchmark need not beat published polls. The exploratory analysis below is reported by Claude and is not a validation result.

## 1. Purpose and non-claims

The prospective confirmatory question is whether a predeclared blend of published state polling averages and the previous election's state result adds useful information for the 2020 U.S. presidential state-margin target, and how the existing AGORA readout compares with simple statistical baselines.

This is not a claim that AGORA is a general election forecaster, that a simulated social system is causally valid, or that any output is fit for operational decisions. A tie or loss is a valid outcome. All models, baselines, exclusions and metrics must be reported; no model may be selected or described as successful because it happens to win on 2020.

No P2D, Nutrivance, customer, driver, personal, private operational or other non-public data is in scope. No connector, credential, live database, AGORA network access or write-back is allowed. `VALIDATED_PREDICTION_ENABLED=False` remains mandatory.

## 2. Relationship to earlier work

- Frozen v0.1 protocol remains at commit `6d06088cf7954bd41f003544f5ec61675389bcc1`; its file SHA-256 is `b776948e14d6dc5c72262b3572365ebc0288fd632bc0bb13743d96fe7d8fea66`.
- Frozen v0.2 run specification remains at commit `3fc4bc4f9b06e90b4602169de4cc13534a403ca0`; its file SHA-256 is `ca87e4f47f39b1112e4ef808e949a49b1c87720f5e6576032acbba8723b5987b`.
- The v0.2 15-row hash-only manifest remains unchanged; SHA-256 `59b39b96c83085fee2b3d4e150d242389f9536417ff2ab8d728c5336bfbf3fdf`.
- Package E's 2016 labels have already been opened by Claude for the completed v0.2 test-evaluate. Therefore the 2004/2008/2012/2016 leave-one-cycle-out analysis below is exploratory only and cannot be represented as an untouched held-out validation.
- The v1.0 2020 outcome is the prospective held-out target. No 2020 outcome may be used for training, calibration, prompt construction, feature selection, weight selection, scenario editing or model choice.

Any v1.0 freeze must identify its own exact commit, new dataset manifest and file hashes. Do not amend the frozen v0.1/v0.2 files or the v0.2 manifest.

## 3. Prior exploratory analysis — Claude-reported, not independently verified

Claude's 24 November approximately 08:00 IST entry reports a leave-one-cycle-out statistical comparison over 2004, 2008, 2012 and 2016 using existing approved polling averages and MEDSL returns. The 2016 labels had already been opened, so this is descriptive exploration only, not validation and not evidence of generalisation.

Reported MAE in percentage points of state margin:

| Held-out cycle | Poll alone | Previous result | One-weight blend | Poll rescaled |
|---|---:|---:|---:|---:|
| 2004 | 2.49 | 4.34 | 2.40 | 2.86 |
| 2008 | 4.30 | 10.86 | 6.03 | 4.24 |
| 2012 | 3.67 | 4.91 | 3.47 | 3.53 |
| 2016 | 6.16 | 6.69 | 5.91 | 6.06 |
| Mean | 4.15 | 6.70 | 4.45 | 4.17 |

Claude reports that the blend improved on poll alone in three cycles but was materially worse in 2008; its mean MAE (4.45) did not beat poll alone (4.15). The rescaled-poll result (4.17) was effectively a wash against poll alone. These values have not been independently reproduced by ChatGPT.

Claude also reports mean signed poll error by cycle of approximately +0.0 pp (2004), −2.5 pp (2008), −1.4 pp (2012) and +5.4 pp (2016). The sign changes across cycles. Report this shared-bias decomposition in the future test, but do not subtract a post-hoc bias correction from 2020 predictions.

## 4. Data and custody requirements

### 4.1 Polling input — 2020 FiveThirtyEight state averages

The owner must later download and supply the exact 2020 presidential general-election state-average file. The current 12-file FiveThirtyEight import does not establish 2020 polling coverage; its general-election file is for 2024 and is explicitly uncorrected, so it is not a substitute.

Before v1.0 freeze, record a **new, separately versioned hash-only v1.0 manifest** in an owner-approved repository. Reference the exact public source/version/path/bytes/SHA-256/licence for each input; do not duplicate or privately mirror the already pinned MEDSL source. The later owner-supplied 2020 polling file must have its own exact source, licence, byte count and SHA-256 before freeze.

- exact source URL and publisher;
- exact original filename and relative path;
- source release, commit or snapshot identifier;
- access/download date;
- licence name, version and applicable licence text/terms;
- byte count and SHA-256 of the exact downloaded file;
- schema/header allow-list and the documented state-margin field/units;
- any source corrections, exclusions or transformation, with a reproducible description.

Do not guess the filename, infer a licence from an older release, use a mirror without approval, or silently substitute another poll product. The exact file, source, licence and hash remain acquisition blockers until the owner supplies and verifies them.

### 4.2 Outcome labels — MEDSL Version 20.0

The previously owner-approved MEDSL V20.0 source is already pinned by public source commit, path, byte count, SHA-256 and CC0 1.0 licence in the frozen v0.2 manifest. Do not download, mirror or stage a private copy for M3 or v1.0. Before a future v1.0 freeze, verify that the exact pinned public file includes the 2020 rows and reference that same immutable source identity in the new hash-only manifest. Use the existing mode rule: use the TOTAL row when present; otherwise sum mutually exclusive modes; never count both.

The 2020 MEDSL state outcomes are held-out labels. Keep them outside the model-development/operator workspace. The owner or designated custodian must retain them and release a separately inventoried label bundle only after the 2020 predictions and complete output inventory have been frozen and hashed. The v0.2 2016 label opening does not authorize early access to 2020 labels.

### 4.3 Manifest separation

Create a new versioned hash-only v1.0 manifest; do not edit `docs/VALIDATION_DATASET_MANIFEST.csv` or its frozen 15-row hash. Include every v1.0 input, including the exact later owner-supplied 2020 polling file and the already pinned public MEDSL outcome file, with per-file bytes, SHA-256, source/version and licence. No raw MEDSL copy is required; record the new manifest's own SHA-256 in the v1.0 freeze attestation.

No raw dataset is to be uploaded to ChatGPT or Notion. No data download or import is authorized by this draft.

## 5. Proposed target, observation unit and time cutoffs

- **Target:** 2020 U.S. presidential two-party state margin, in percentage points, derived from the predeclared MEDSL V20.0 state returns using the frozen mode rule.
- **Observation unit:** state/area × forecast cutoff. Freeze the included state/area universe and treatment of DC/territories before outcome release; do not silently drop an area after seeing its result.
- **Election Day:** 3 November 2020.
- **Proposed cutoffs:** 28, 14 and 7 days before Election Day: 6 October, 20 October and 27 October 2020. These dates are a draft proposal and must be confirmed in the v1.0 freeze.
- **Poll value:** for each state/area and cutoff, use the latest eligible published FiveThirtyEight state average dated on or before that cutoff. No poll published after the cutoff may be used.
- **Previous result:** the 2016 two-party state margin, carried forward without post-hoc adjustment.

If the supplied polling file does not provide the required state/area, office, date or margin coverage, mark the affected target not evaluable and stop. Do not substitute national averages, individual polls, a later date or a different source after inspecting outcomes.

## 6. Predeclared model set

The following four comparisons are proposed. Their exact formulas and input mapping must be frozen before any 2020 outcome is released.

1. **Poll alone:** the eligible 2020 FiveThirtyEight state average at each fixed cutoff.
2. **Previous result:** the 2016 two-party state margin carried forward unchanged.
3. **One-weight blend:** one global scalar (w) applied to poll and previous-result margins:
   [
   \widehat m_{s,t}=w p_{s,t}+(1-w)r_s,\quad 0\leq w\leq1.
   ]
   Proposed fitting rule: choose (w) using only pre-2020 cycles 2004, 2008, 2012 and 2016, pooling the predeclared state/cutoff observations and minimizing MAE over a fixed grid from 0.00 to 1.00 in 0.01 increments. Freeze the tie-break rule and exact training-row/exclusion set before v1.0 freeze. No 2020 outcome may influence (w).
4. **AGORA readout:** use the existing frozen v0.2 mapping/readout without changing engine code or tuning against 2020. The reported v0.2 calibration selected (k=0.24); whether this exact mapping is retained unchanged for v1.0 must be explicit in the freeze. The readout is a monotone transformation of the poll average and must not be described as an independent information source.

**Minimal fundamentals:** the owner direction limits fundamentals to incumbent party and previous-election state result. The previous-result baseline/blend already uses the 2016 state margin. This draft treats incumbent party as a predeclared descriptor for stratified reporting only, not as a fitted coefficient. If the owner intends an incumbent-party predictive term, its exact encoding and formula must be approved and frozen before 2020 is touched; do not add it after seeing results. No economy, demographic, campaign, fundraising or other fundamentals are allowed in this version.

## 7. Metrics, uncertainty and bias reporting

- **Primary metric:** mean absolute error (MAE), in percentage points, over the frozen state/area × cutoff observations.
- **Secondary metric:** root mean squared error (RMSE), same unit and denominator.
- Report every model's full observation count, state/area count, cutoff coverage, per-state errors, missingness and exclusions.
- Report 95% cluster-bootstrap intervals for MAE and RMSE, resampling states/areas as clusters and keeping all cutoffs for a sampled state together. Proposed replicate count: 2,000. Select and record the RNG seed in the v1.0 freeze before predictions; do not select it after outcomes.
- **Interval coverage:** report coverage for predeclared nominal prediction intervals only if the interval construction, nominal level(s), training residual source and calculation are frozen before test predictions. If that method is not fully specified before freeze, report interval coverage as not estimable; do not construct or calibrate intervals after opening 2020 labels.
- **Shared-bias decomposition:** report mean signed error (prediction minus actual) by historical cycle and for 2020, alongside MAE/RMSE. Do not apply a post-hoc national-bias correction to the 2020 predictions.
- Report the poll-alone baseline first and all other models beside it. A tie or loss is valid; no minimum improvement or win condition is required. Do not omit unfavorable cycles, states, cutoffs or metrics.

## 8. Output freeze and one-shot label sequence

Before 2020 labels are released:

1. Freeze this v1.0 protocol, its exact commit, the new manifest and its SHA-256, the Agora code commit, environment/dependency lock, model formulas, feature mapping, cutoff rows, exclusions, run configuration and seeds.
2. Generate the predeclared predictions without reading 2020 MEDSL outcomes.
3. Preserve every output, log, configuration and provenance file. Do not edit, filter, rename to conceal, or selectively omit outputs.
4. Create a complete relative-path inventory with byte count and SHA-256 for every output; compute and record the inventory's own SHA-256 and freeze timestamp.
5. The owner/custodian verifies the inventory and then releases a separately inventoried 2020 label bundle to the designated independent evaluator.
6. Evaluate once against the frozen protocol. Report every model, metric, baseline, exclusion and failure. Do not tune or rerun after seeing 2020 outcomes.

Any failed, denied, interrupted or invalid attempt must be retained and logged. A rerun, replacement output, model change or protocol change requires a new version, explanation and separate owner approval.

## 9. Stop rules

Stop and mark v1.0 not evaluable if any of the following occurs:

- the exact 2020 polling file, source version, licence, byte count or SHA-256 is missing or ambiguous;
- the MEDSL version, mode handling, state mapping or 2020 outcome custody is ambiguous;
- a required state/area or cutoff lacks eligible poll coverage or a valid target;
- any 2020 outcome is exposed to the operator/model before output freeze;
- model formulas, blend-weight selection, incumbent-party treatment, interval method, bootstrap seed or exclusions are changed after freeze;
- output inventory or hash verification fails;
- a result cannot be expressed in the predeclared state-margin unit.

Do not create a proxy target or replace a missing source after seeing the result.

## 10. Freeze and authorization gates

This draft is not a freeze or run authorization. Before any 2020 acquisition/import/run:

- [ ] Owner supplies the exact 2020 FiveThirtyEight state-average file and approves its source and licence.
- [ ] Owner supplies the exact 2020 poll file; the new hash-only manifest records its bytes, hash, source and licence and references the already pinned public MEDSL source. No private MEDSL mirror or data download is required before owner approval.
- [ ] Owner/Claude resolve the state/area universe, cutoffs, blend-weight grid/tie-break, incumbent-party role, interval method/levels, bootstrap seed and all exclusions.
- [ ] A separate evaluator/custodian and 2020 label-release procedure are confirmed.
- [ ] The owner provides a complete v1.0 freeze sentence naming the exact protocol commit and new manifest SHA-256.
- [ ] The owner separately authorizes the specific 2020 run after the freeze.

No further `agora/sim/**` path is authorized. The only existing owner-approved path remains `agora/sim/engine.py`; this draft does not require or authorize an engine change. Production CLI identity remains default-deny. `VALIDATED_PREDICTION_ENABLED=False` remains unchanged.

## 11. Current status

Claude's exploratory analysis is a reported, unverified statistical exercise over already-opened 2004/2008/2012/2016 outcomes. It is not a validation, not an M3 completion declaration and not a basis for a validated-prediction claim. The future 2020 confirmatory holdout remains unacquired, unfrozen and unauthorized. M3 status is governed separately by `M3_EXIT_EVIDENCE.md` and Claude's exact canonical declaration.

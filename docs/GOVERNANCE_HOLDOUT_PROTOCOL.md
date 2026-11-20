# G3 — Canonical independent holdout protocol

## Purpose and boundary

G3 makes `agora.validation.protocol.HoldoutProtocol` the single contract for
chronological train/test partitioning. `agora.validation.holdout.split` and
both evaluation functions use that same contract. The older date-argument API
remains as a compatibility adapter for existing exploratory callers; new
registered evaluations should use a pre-registered `HoldoutProtocol`.

This is an evaluation and evidence foundation. It does **not** approve claims,
change report modes, enable `validated_prediction`, or establish that a dataset
is representative of a real population.

## Pre-registering a protocol

A protocol records:

- stable `protocol_id` and `protocol_version`;
- inclusive `train_end`, `test_start`, and `test_end` boundaries;
- minimum training and holdout counts;
- a grouping key used to detect cross-period group leakage;
- `dataset_id` and SHA-256 `source_hashes`;
- `source_roles` for every source hash;
- the named baseline and its description;
- optional metric acceptance thresholds (`min` or `max`).

`test_start` must be strictly after `train_end`; `test_end` cannot precede
`test_start`. Records in the gap between the training and test periods, and
records after `test_end`, are excluded. Every row must have a parseable ISO date
(or `Record.when`). Duplicate non-empty `record_id` values are rejected.

When `source_roles` is supplied, it must cover exactly the source IDs in
`source_hashes`, and every record must name one of those sources. Training rows
may only use `calibration` sources. Test rows may only use `validation` or
`sealed_holdout` sources. A row-level `data_role`, if present, must agree with
the registered protocol role. This prevents sealed holdout records from being
passed to the training callback. Separately, Agora's calibration source guard
continues to reject `sealed_holdout` source files from calibration and ordinary
backtesting.

## Evaluation APIs

### Numeric point forecasts

`evaluate(..., protocol=..., baseline_id=...)` requires the baseline ID to match
the pre-registered protocol. Registered evaluation also requires dataset ID,
source hashes, data snapshot ID, model version, configuration SHA-256, and
reviewer evidence (`reviewer_id` and `review_status`). These fields are returned
with the protocol fingerprint in `evaluation_evidence`.

Metrics include model and baseline MAE/RMSE and skill against the baseline.
Uncertainty is reported as 95% non-parametric bootstrap percentile intervals for
model MAE, baseline MAE, and paired MAE difference. When a grouping key is set,
resampling is by group (not individual row); otherwise it is by record.

Optional prediction intervals produce empirical coverage, nominal coverage (if
provided), mean interval width, and coverage gap. Calibration is marked not
applicable for point forecasts.

### Binary probability forecasts

`evaluate_probabilities` uses the same protocol and evidence requirements. It
reports Brier score, log loss, expected calibration error (equal-width bins),
baseline comparisons, and bootstrap intervals for Brier score and paired Brier
difference. Numeric prediction-interval coverage is marked not applicable.

### Acceptance thresholds

Thresholds are declarative metric rules such as
`{"model_mae": {"operator": "max", "value": 1.5}}`. The result records
`pass`, `fail`, `not_applicable`, or `not_assessed`. This is an evaluation result
only; G4 must separately enforce approvals and permitted claims. A missing or
inapplicable metric cannot be treated as a pass.

## Evidence and limitations

The protocol fingerprint is a SHA-256 hash of its declared configuration,
dataset identity, source hashes/roles, baseline and thresholds. The evaluation
result carries the data snapshot ID, model version, config hash, metrics,
uncertainty and caller-supplied reviewer evidence. The code validates that these
identifiers match the protocol declaration, but it does not independently read
source files to recompute the caller's hashes, create immutable data snapshots,
or authenticate the reviewer. The caller must obtain hashes from the provenance
registry and preserve the returned evaluation artifact.

Bootstrap intervals quantify sampling variation under the selected resampling
unit; they do not correct dataset shift, selection bias, dependence between
groups, or inadequate sample size. ECE depends on binning and can be unstable on
small test sets. Thresholds must be chosen for the actual domain and target;
there are no universal defaults. Reviewer status is evidence metadata, not an
approval workflow.

G3 leaves the G2 audit log, Nutrivance scenario, simulation data, deployment
state, and G4/G5 features unchanged. `validated_prediction` remains disabled.

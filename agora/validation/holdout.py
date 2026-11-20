"""Chronological holdout evaluation using the canonical HoldoutProtocol."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Sequence

import numpy as np

from agora.validation.protocol import HoldoutProtocol


@dataclass(frozen=True)
class Record:
    when: date
    features: dict
    outcome: float
    group_id: str | None = None
    record_id: str | None = None
    source_id: str | None = None
    data_role: str | None = None


def _legacy_protocol(train_end: date, test_start: date, test_end: date) -> HoldoutProtocol:
    """Compatibility adapter; new evaluations should pass a pre-registered protocol."""
    return HoldoutProtocol(
        protocol_id="legacy-holdout-adapter",
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        minimum_train=1,
        minimum_test=1,
        grouping_key=None,
    )


def split(
    records: Sequence[Record],
    train_end: date | None = None,
    test_start: date | None = None,
    test_end: date | None = None,
    *,
    protocol: HoldoutProtocol | None = None,
    dataset_id: str | None = None,
    source_hashes: Mapping[str, str] | None = None,
):
    """Split records through the same canonical protocol used by validation."""
    if protocol is None:
        if train_end is None or test_start is None or test_end is None:
            raise ValueError("Provide either protocol or all three date boundaries")
        protocol = _legacy_protocol(train_end, test_start, test_end)
    train, test, _ = protocol.partition(records, dataset_id=dataset_id, source_hashes=source_hashes)
    return train, test


def _bootstrap_ci(values: np.ndarray, *, samples: int, seed: int,
                  groups: Sequence | None = None) -> list[float]:
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 200:
        raise ValueError("bootstrap_samples must be an integer of at least 200 for percentile intervals")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("bootstrap_seed must be an integer")
    rng = np.random.default_rng(seed)
    n = len(values)
    estimates = np.empty(samples, dtype=float)
    group_indices = None
    unique_groups = None
    if groups is not None:
        if len(groups) != n:
            raise ValueError("bootstrap groups must align with evaluation records")
        group_indices = {}
        for index, group in enumerate(groups):
            group_indices.setdefault(group, []).append(index)
        unique_groups = list(group_indices)
    for index in range(samples):
        if unique_groups is None:
            sample = values[rng.integers(0, n, size=n)]
        else:
            chosen = rng.integers(0, len(unique_groups), size=len(unique_groups))
            selected = [row_index for group_index in chosen
                        for row_index in group_indices[unique_groups[int(group_index)]]]
            sample = values[np.asarray(selected, dtype=int)]
        estimates[index] = float(np.mean(sample))
    lower, upper = np.quantile(estimates, [0.025, 0.975])
    return [float(lower), float(upper)]


def _build_evaluation_evidence(
    protocol: HoldoutProtocol,
    *,
    dataset_id: str | None,
    source_hashes: Mapping[str, str] | None,
    data_snapshot_id: str | None,
    model_version: str | None,
    config_hash: str | None,
    reviewer_evidence: Mapping | None,
):
    requested = any(value is not None for value in
                    (data_snapshot_id, model_version, config_hash, reviewer_evidence))
    if not requested:
        return None
    missing = [name for name, value in (
        ("dataset_id", dataset_id), ("source_hashes", source_hashes),
        ("data_snapshot_id", data_snapshot_id), ("model_version", model_version),
        ("config_hash", config_hash), ("reviewer_evidence", reviewer_evidence),
    ) if value in (None, "", {})]
    if missing:
        raise ValueError("Incomplete validation evidence; missing: " + ", ".join(missing))
    if not isinstance(reviewer_evidence, Mapping) or not reviewer_evidence:
        raise ValueError("reviewer_evidence must be a non-empty mapping")
    if not all(isinstance(reviewer_evidence.get(key), str) and reviewer_evidence[key].strip()
               for key in ("reviewer_id", "review_status")):
        raise ValueError("reviewer_evidence requires non-empty reviewer_id and review_status")
    if not isinstance(data_snapshot_id, str) or not data_snapshot_id.strip():
        raise ValueError("data_snapshot_id must be a non-empty string")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must be a non-empty string")
    if not isinstance(config_hash, str) or len(config_hash) != 64 or any(c not in "0123456789abcdef" for c in config_hash):
        raise ValueError("config_hash must be a lowercase SHA-256 hex digest")
    if protocol.dataset_id is None or not protocol.source_hashes or not protocol.source_roles:
        raise ValueError("Evidence-grade evaluation requires dataset_id, source_hashes and source_roles bound into the pre-registered protocol")
    if dataset_id != protocol.dataset_id or dict(source_hashes) != dict(protocol.source_hashes):
        raise ValueError("Evaluation evidence identity does not match the pre-registered protocol")
    return {
        "dataset_id": dataset_id,
        "source_hashes": dict(sorted(source_hashes.items())),
        "data_snapshot_id": data_snapshot_id,
        "model_version": model_version,
        "config_hash": config_hash,
        "reviewer_evidence": dict(reviewer_evidence),
    }


def _assess_thresholds(protocol: HoldoutProtocol, metrics: Mapping) -> dict:
    assessed = {}
    for metric_name, rule in protocol.acceptance_thresholds.items():
        value = metrics.get(metric_name)
        if value is None:
            assessed[metric_name] = {"status": "not_applicable", **rule}
            continue
        passed = value >= rule["value"] if rule["operator"] == "min" else value <= rule["value"]
        assessed[metric_name] = {"status": "pass" if passed else "fail", "observed": value, **rule}
    statuses = [item["status"] for item in assessed.values()]
    overall = "not_assessed" if not statuses else ("fail" if "fail" in statuses else
              "incomplete" if "not_applicable" in statuses else "pass")
    return {"overall": overall, "metrics": assessed,
            "note": "Thresholds compare point estimates; uncertainty remains separately reported. This is evidence only, not approval."}


def evaluate(
    records: Sequence[Record],
    train_end: date | None = None,
    test_start: date | None = None,
    test_end: date | None = None,
    predict: Callable[[list[Record], dict], float] | None = None,
    baseline: Callable[[list[Record], dict], float] | None = None,
    *,
    protocol: HoldoutProtocol | None = None,
    dataset_id: str | None = None,
    source_hashes: Mapping[str, str] | None = None,
    data_snapshot_id: str | None = None,
    model_version: str | None = None,
    config_hash: str | None = None,
    reviewer_evidence: Mapping | None = None,
    baseline_id: str | None = None,
    bootstrap_samples: int = 1000,
    bootstrap_seed: int = 0,
    prediction_interval: Callable[[list[Record], dict], tuple[float, float]] | None = None,
    nominal_coverage: float | None = None,
) -> dict:
    """Evaluate point forecasts against an explicit caller-supplied baseline.

    If evidence metadata is supplied, all dataset/source/snapshot/model/config and
    reviewer fields are required and are returned with the protocol fingerprint.
    The function does not approve claims or enable validated prediction.
    """
    from agora.calibrate.metrics import mae, rmse, skill

    if predict is None or baseline is None:
        raise ValueError("Both predict and baseline callbacks are required")
    if protocol is None:
        if train_end is None or test_start is None or test_end is None:
            raise ValueError("Provide either protocol or all three date boundaries")
        protocol = _legacy_protocol(train_end, test_start, test_end)
    if protocol.protocol_id != "legacy-holdout-adapter" and baseline_id != protocol.baseline_id:
        raise ValueError("baseline_id must match the pre-registered holdout protocol")
    train, test, partition_evidence = protocol.partition(
        records, dataset_id=dataset_id, source_hashes=source_hashes
    )

    evaluation_evidence = _build_evaluation_evidence(
        protocol, dataset_id=dataset_id, source_hashes=source_hashes,
        data_snapshot_id=data_snapshot_id, model_version=model_version,
        config_hash=config_hash, reviewer_evidence=reviewer_evidence,
    )
    if protocol.protocol_id != "legacy-holdout-adapter" and evaluation_evidence is None:
        raise ValueError("Registered holdout evaluation requires complete evaluation evidence metadata")

    observed = np.asarray([float(row.outcome) for row in test], dtype=float)
    model_pred = np.asarray([float(predict(train, row.features)) for row in test], dtype=float)
    baseline_pred = np.asarray([float(baseline(train, row.features)) for row in test], dtype=float)
    if not (np.all(np.isfinite(observed)) and np.all(np.isfinite(model_pred)) and np.all(np.isfinite(baseline_pred))):
        raise ValueError("Outcomes and predictions must be finite numeric values")
    model_errors = np.abs(model_pred - observed)
    baseline_errors = np.abs(baseline_pred - observed)
    model_mae, baseline_mae = mae(model_pred, observed), mae(baseline_pred, observed)
    model_rmse, baseline_rmse = rmse(model_pred, observed), rmse(baseline_pred, observed)
    bootstrap_groups = ([getattr(row, protocol.grouping_key) if not isinstance(row, Mapping)
                         else row[protocol.grouping_key] for row in test]
                        if protocol.grouping_key is not None else None)
    result = {
        **partition_evidence,
        "baseline": {"id": protocol.baseline_id, "description": protocol.baseline_description},
        "metrics": {
            "model_mae": model_mae,
            "baseline_mae": baseline_mae,
            "model_rmse": model_rmse,
            "baseline_rmse": baseline_rmse,
            "skill_vs_baseline_mae": skill(model_mae, baseline_mae),
            "skill_vs_baseline_rmse": skill(model_rmse, baseline_rmse),
        },
        "threshold_assessment": _assess_thresholds(protocol, {
            "model_mae": model_mae, "baseline_mae": baseline_mae,
            "model_rmse": model_rmse, "baseline_rmse": baseline_rmse,
            "skill_vs_baseline_mae": skill(model_mae, baseline_mae),
            "skill_vs_baseline_rmse": skill(model_rmse, baseline_rmse),
        }),
        "uncertainty": {
            "method": "paired non-parametric bootstrap percentile interval",
            "confidence_level": 0.95,
            "bootstrap_samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "model_mae_ci95": _bootstrap_ci(model_errors, samples=bootstrap_samples, seed=bootstrap_seed,
                                            groups=bootstrap_groups),
            "baseline_mae_ci95": _bootstrap_ci(baseline_errors, samples=bootstrap_samples, seed=bootstrap_seed + 1,
                                               groups=bootstrap_groups),
            "mae_difference_ci95": _bootstrap_ci(model_errors - baseline_errors,
                                                   samples=bootstrap_samples, seed=bootstrap_seed + 2,
                                                   groups=bootstrap_groups),
        },
        "calibration": {"applicable": False,
                        "reason": "This evaluator scores point forecasts, not probability forecasts."},
        "coverage": {"applicable": False,
                     "reason": "No prediction intervals were supplied."},
    }
    result["uncertainty"]["resampling_unit"] = ("group" if bootstrap_groups is not None else "record")
    if prediction_interval is not None:
        intervals = [prediction_interval(train, row.features) for row in test]
        bounds = np.asarray(intervals, dtype=float)
        if bounds.shape != (len(test), 2) or not np.all(np.isfinite(bounds)):
            raise ValueError("prediction_interval must return finite (lower, upper) pairs")
        if np.any(bounds[:, 0] > bounds[:, 1]):
            raise ValueError("prediction interval lower bound exceeds upper bound")
        coverage = float(np.mean((observed >= bounds[:, 0]) & (observed <= bounds[:, 1])))
        if nominal_coverage is not None and not 0 < nominal_coverage < 1:
            raise ValueError("nominal_coverage must be between 0 and 1")
        result["coverage"] = {
            "applicable": True,
            "empirical_coverage": coverage,
            "nominal_coverage": nominal_coverage,
            "mean_interval_width": float(np.mean(bounds[:, 1] - bounds[:, 0])),
            "coverage_gap": None if nominal_coverage is None else coverage - nominal_coverage,
        }
    elif nominal_coverage is not None:
        raise ValueError("nominal_coverage requires prediction_interval")
    if evaluation_evidence is not None:
        result["evaluation_evidence"] = evaluation_evidence
    # Legacy result keys retained for callers of the pre-G3 API.
    result.update({"model_mae": model_mae, "baseline_mae": baseline_mae,
                   "skill_vs_baseline": skill(model_mae, baseline_mae)})
    return result


def evaluate_probabilities(
    records: Sequence[Record],
    protocol: HoldoutProtocol,
    predict_probability: Callable[[list[Record], dict], float],
    baseline_probability: Callable[[list[Record], dict], float],
    *,
    dataset_id: str | None = None,
    source_hashes: Mapping[str, str] | None = None,
    data_snapshot_id: str | None = None,
    model_version: str | None = None,
    config_hash: str | None = None,
    reviewer_evidence: Mapping | None = None,
    baseline_id: str | None = None,
    bootstrap_samples: int = 1000,
    bootstrap_seed: int = 0,
) -> dict:
    """Evaluate binary-event probabilities with Brier, log-loss and calibration metrics."""
    from agora.calibrate.metrics import score_probabilities

    if baseline_id != protocol.baseline_id:
        raise ValueError("baseline_id must match the pre-registered holdout protocol")
    train, test, partition_evidence = protocol.partition(
        records, dataset_id=dataset_id, source_hashes=source_hashes
    )
    observed = np.asarray([float(row.outcome) for row in test], dtype=float)
    if not np.all(np.isin(observed, [0.0, 1.0])):
        raise ValueError("Probability evaluation requires binary 0/1 outcomes")
    model = np.asarray([float(predict_probability(train, row.features)) for row in test], dtype=float)
    baseline = np.asarray([float(baseline_probability(train, row.features)) for row in test], dtype=float)
    if not (np.all(np.isfinite(model)) and np.all(np.isfinite(baseline))):
        raise ValueError("Predicted probabilities must be finite")
    if np.any((model < 0) | (model > 1)) or np.any((baseline < 0) | (baseline > 1)):
        raise ValueError("Predicted probabilities must lie in [0, 1]")
    scores = score_probabilities(model, observed, baseline)
    evaluation_evidence = _build_evaluation_evidence(
        protocol, dataset_id=dataset_id, source_hashes=source_hashes,
        data_snapshot_id=data_snapshot_id, model_version=model_version,
        config_hash=config_hash, reviewer_evidence=reviewer_evidence,
    )
    if evaluation_evidence is None:
        raise ValueError("Registered probability evaluation requires complete evaluation evidence metadata")
    model_brier = (model - observed) ** 2
    baseline_brier = (baseline - observed) ** 2
    bootstrap_groups = ([getattr(row, protocol.grouping_key) if not isinstance(row, Mapping)
                         else row[protocol.grouping_key] for row in test]
                        if protocol.grouping_key is not None else None)
    return {
        **partition_evidence,
        "baseline": {"id": protocol.baseline_id, "description": protocol.baseline_description},
        "metrics": scores,
        "threshold_assessment": _assess_thresholds(protocol, {
            "model_brier": scores["model"]["brier"],
            "model_log_loss": scores["model"]["log_loss"],
            "model_calibration_error": scores["model"]["calibration_error"],
            "skill_brier": scores["skill_brier"],
        }),
        "uncertainty": {
            "method": "paired non-parametric bootstrap percentile interval",
            "confidence_level": 0.95,
            "bootstrap_samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "model_brier_ci95": _bootstrap_ci(model_brier, samples=bootstrap_samples, seed=bootstrap_seed,
                                              groups=bootstrap_groups),
            "baseline_brier_ci95": _bootstrap_ci(baseline_brier, samples=bootstrap_samples, seed=bootstrap_seed + 1,
                                                 groups=bootstrap_groups),
            "brier_difference_ci95": _bootstrap_ci(model_brier - baseline_brier,
                                                      samples=bootstrap_samples, seed=bootstrap_seed + 2,
                                                      groups=bootstrap_groups),
            "resampling_unit": "group" if bootstrap_groups is not None else "record",
        },
        "calibration": {
            "applicable": True,
            "model_calibration_error": scores["model"]["calibration_error"],
            "baseline_calibration_error": scores["baseline"]["calibration_error"],
            "method": "expected calibration error using equal-width probability bins",
        },
        "coverage": {"applicable": False,
                     "reason": "Probability forecasts are evaluated with calibration and proper scoring rules, not numeric prediction intervals."},
        **({"evaluation_evidence": evaluation_evidence} if evaluation_evidence is not None else {}),
    }

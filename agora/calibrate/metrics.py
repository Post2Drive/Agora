"""Prediction-quality measures for comparing Agora with observed outcomes and baselines.

Numeric forecasts: MAE, RMSE. Probability forecasts: Brier score, log loss, calibration
error (expected calibration error over equal-width bins). Distributions: Wasserstein
distance. Social structure: network_comparison. Every score is compared with a baseline
through skill(), where 1 means better than the baseline, 0 means no better, and below
0 means worse.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _arr(x: Sequence[float]) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    if a.size == 0:
        raise ValueError("empty input")
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite values")
    return a


def _pair(pred, obs) -> tuple[np.ndarray, np.ndarray]:
    p, o = _arr(pred), _arr(obs)
    if p.shape != o.shape:
        raise ValueError(f"shape mismatch: {p.shape} vs {o.shape}")
    return p, o


def _check_probs(p: np.ndarray, y: np.ndarray) -> None:
    if np.any((p < 0) | (p > 1)):
        raise ValueError("probabilities must lie in [0, 1]")
    if not np.all(np.isin(y, [0.0, 1.0])):
        raise ValueError("outcomes must be 0 or 1")


def mae(pred, obs) -> float:
    p, o = _pair(pred, obs)
    return float(np.mean(np.abs(p - o)))


def rmse(pred, obs) -> float:
    p, o = _pair(pred, obs)
    return float(math.sqrt(np.mean((p - o) ** 2)))


def brier(prob, outcome) -> float:
    """Mean squared error of probabilities against 0/1 outcomes (lower is better)."""
    p, y = _pair(prob, outcome)
    _check_probs(p, y)
    return float(np.mean((p - y) ** 2))


def log_loss(prob, outcome, eps: float = 1e-15) -> float:
    p, y = _pair(prob, outcome)
    _check_probs(p, y)
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration_error(prob, outcome, bins: int = 10) -> float:
    """Expected calibration error: average |mean predicted - observed rate| over bins,
    weighted by how many forecasts fall in each bin. 0 means well calibrated."""
    p, y = _pair(prob, outcome)
    _check_probs(p, y)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return float(total / p.size)


def wasserstein(a, b, grid: int = 1000) -> float:
    """1-D Wasserstein distance between two samples (same units as the data)."""
    x, y = _arr(a), _arr(b)
    qs = (np.arange(grid) + 0.5) / grid
    return float(np.mean(np.abs(np.quantile(x, qs) - np.quantile(y, qs))))


def skill(model_error: float, baseline_error: float) -> float:
    """1 - model/baseline for an error (lower is better). Positive means the model beats
    the baseline. Returns 0 if the baseline error is zero."""
    if baseline_error == 0:
        return 0.0
    return 1.0 - model_error / baseline_error


def network_comparison(sim_graph, obs_graph) -> dict:
    """Compare two networkx graphs: density, mean clustering, and the Wasserstein distance
    between their degree distributions. Smaller distances mean closer structure."""
    import networkx as nx

    def stats(g):
        n = g.number_of_nodes()
        deg = np.array([d for _, d in g.degree()], dtype=float) if n else np.array([0.0])
        return {
            "density": nx.density(g) if n > 1 else 0.0,
            "clustering": nx.average_clustering(g) if n else 0.0,
            "degrees": deg,
        }

    s, o = stats(sim_graph), stats(obs_graph)
    return {
        "density_diff": abs(s["density"] - o["density"]),
        "clustering_diff": abs(s["clustering"] - o["clustering"]),
        "degree_wasserstein": wasserstein(s["degrees"], o["degrees"]),
    }


def score_forecast(pred, obs, baseline_pred) -> dict:
    """Numeric forecast scores for the model and a baseline, with skill against it."""
    m_mae, b_mae = mae(pred, obs), mae(baseline_pred, obs)
    m_rmse, b_rmse = rmse(pred, obs), rmse(baseline_pred, obs)
    return {
        "model": {"mae": m_mae, "rmse": m_rmse},
        "baseline": {"mae": b_mae, "rmse": b_rmse},
        "skill_mae": skill(m_mae, b_mae),
        "skill_rmse": skill(m_rmse, b_rmse),
    }


def score_probabilities(prob, outcome, baseline_prob) -> dict:
    m_b, b_b = brier(prob, outcome), brier(baseline_prob, outcome)
    return {
        "model": {"brier": m_b, "log_loss": log_loss(prob, outcome),
                  "calibration_error": calibration_error(prob, outcome)},
        "baseline": {"brier": b_b, "log_loss": log_loss(baseline_prob, outcome),
                     "calibration_error": calibration_error(baseline_prob, outcome)},
        "skill_brier": skill(m_b, b_b),
    }

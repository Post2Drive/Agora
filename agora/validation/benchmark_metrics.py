"""Pure metrics and baselines for the validation protocol (docs/VALIDATION_PROTOCOL.md sections 3 and 5).

No I/O, no network, no engine import, no randomness except the explicitly seeded bootstrap.
Anything that cannot be computed is reported as `NotEstimable`; nothing is imputed or defaulted.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Callable, Mapping, Sequence

import numpy as np


class NotEstimable(ValueError):
    """The metric or interval is undefined for these inputs (zero denominator, too few clusters, no data)."""


def _vec(x: Sequence[float], name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim != 1 or a.size == 0 or not np.all(np.isfinite(a)):
        raise NotEstimable(f"{name} must be a non-empty one-dimensional array of finite numbers")
    return a


def _pair(pred, obs) -> tuple[np.ndarray, np.ndarray]:
    p, o = _vec(pred, "pred"), _vec(obs, "obs")
    if p.shape != o.shape:
        raise NotEstimable("pred and obs must have the same length")
    return p, o


def wape(pred, obs) -> float:
    """Weighted absolute percentage error = sum|obs - pred| / sum|obs|; zero denominator is NotEstimable."""
    p, o = _pair(pred, obs)
    denom = float(np.sum(np.abs(o)))
    if denom == 0.0:
        raise NotEstimable("sum of absolute observations is zero")
    return float(np.sum(np.abs(o - p)) / denom)


def rmsse(train, obs, pred) -> float:
    """M5 RMSSE: sqrt(mean((obs-pred)^2) / mean(squared one-step differences of train after its first non-zero))."""
    tr = _vec(train, "train")
    p, o = _pair(pred, obs)
    nz = np.flatnonzero(tr != 0)
    if nz.size == 0 or tr.size - nz[0] < 2:
        raise NotEstimable("training series has no usable non-zero history")
    seg = tr[nz[0]:]
    scale = float(np.mean(np.diff(seg) ** 2))
    if scale == 0.0:
        raise NotEstimable("naive one-step scale is zero")
    return float(math.sqrt(float(np.mean((o - p) ** 2)) / scale))


def wrmsse(trains: Sequence[Sequence[float]], obs: Sequence[Sequence[float]],
           preds: Sequence[Sequence[float]], weights: Sequence[float]) -> float:
    """Weighted sum of per-series RMSSE for a flat set of series; weights are normalised to sum to 1.

    The 12-level M5 hierarchy aggregation (building the aggregated series and their dollar-sales
    weights) is done by the evaluation script from the official files, then passed here.
    """
    w = _vec(weights, "weights")
    if np.any(w < 0) or float(w.sum()) == 0.0:
        raise NotEstimable("weights must be non-negative with a positive sum")
    if not (len(trains) == len(obs) == len(preds) == w.size):
        raise NotEstimable("trains, obs, preds and weights must describe the same series")
    w = w / w.sum()
    return float(sum(wi * rmsse(t, o, p) for wi, t, o, p in zip(w, trains, obs, preds)))


def seasonal_naive(history: Sequence[float], horizon: int, season: int) -> np.ndarray:
    """Repeat the last `season` observations over `horizon` steps (t-7 for daily, t-12 for monthly)."""
    h = _vec(history, "history")
    if (not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1
            or not isinstance(season, int) or isinstance(season, bool) or season < 1):
        raise NotEstimable("horizon and season must be positive integers")
    if h.size < season:
        raise NotEstimable("history is shorter than one season; nothing is interpolated")
    tail = h[-season:]
    return np.array([tail[i % season] for i in range(horizon)], dtype=float)


def two_party_margin(a_pct: float, b_pct: float) -> float:
    """Two-party margin in percentage points: (a - b) / (a + b) * 100."""
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
               for v in (a_pct, b_pct)):
        raise NotEstimable("shares must be finite and non-negative")
    if a_pct + b_pct == 0:
        raise NotEstimable("both shares are zero")
    return (a_pct - b_pct) / (a_pct + b_pct) * 100.0


def weighted_poll_margin(polls: Sequence[Mapping], cutoff: date, window_days: int = 28) -> float:
    """Sample-size-weighted mean two-party margin of polls with end date in (cutoff - window, cutoff].

    Each poll: {"end_date": date, "sample_size": positive number, "a_pct": x, "b_pct": y}.
    A poll ending after the cutoff is never used. No eligible poll -> NotEstimable (no imputation).
    """
    if type(cutoff) is not date:
        raise NotEstimable("cutoff must be a date (not a datetime)")
    if not isinstance(window_days, int) or isinstance(window_days, bool) or window_days < 1:
        raise NotEstimable("window_days must be a positive integer")
    start = cutoff - timedelta(days=window_days)
    num = den = 0.0
    for p in polls:
        try:
            end = p["end_date"]
            _ = p["sample_size"], p["a_pct"], p["b_pct"]
        except (KeyError, TypeError):
            raise NotEstimable("poll must carry end_date, sample_size, a_pct and b_pct") from None
        if type(end) is not date:
            raise NotEstimable("poll end_date must be a date (not a datetime or string)")
        if not (start < end <= cutoff):
            continue
        n = p["sample_size"]
        if not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) or n <= 0:
            raise NotEstimable("poll sample_size must be a positive finite number")
        num += n * two_party_margin(p["a_pct"], p["b_pct"])
        den += n
    if den == 0.0:
        raise NotEstimable("no eligible poll in the window")
    return num / den


def cluster_bootstrap_ci(errors_by_cluster: Mapping[str, Sequence[float]], *, samples: int = 2000, seed: int,
                         alpha: float = 0.05, min_clusters: int = 10,
                         statistic: Callable[[np.ndarray], float] = lambda x: float(np.mean(x))) -> dict:
    """Percentile CI of `statistic` over pooled errors, resampling whole clusters with replacement.

    Fewer than `min_clusters` clusters -> NotEstimable (never a misleadingly narrow interval).
    """
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise NotEstimable("an explicit non-negative integer seed is required")
    for name, val in (("samples", samples), ("min_clusters", min_clusters)):
        if not isinstance(val, int) or isinstance(val, bool):
            raise NotEstimable(f"{name} must be an integer")
    if min_clusters < 1:
        raise NotEstimable("min_clusters must be a positive integer")
    if (isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha)
            or not (0 < alpha < 1)):
        raise NotEstimable("alpha must be a finite number in (0,1)")
    if samples < 100:
        raise NotEstimable("samples must be at least 100")
    clusters = {k: _vec(v, f"cluster {k}") for k, v in errors_by_cluster.items()}
    if len(clusters) < min_clusters:
        raise NotEstimable(f"only {len(clusters)} clusters; at least {min_clusters} are needed")
    keys = sorted(clusters)
    rng = np.random.default_rng(seed)
    stats = np.empty(samples)
    for i in range(samples):
        pick = rng.integers(0, len(keys), size=len(keys))
        stats[i] = statistic(np.concatenate([clusters[keys[j]] for j in pick]))
    point = statistic(np.concatenate([clusters[k] for k in keys]))
    lo, hi = np.quantile(stats, [alpha / 2, 1 - alpha / 2])
    return {"point": float(point), "lo": float(lo), "hi": float(hi), "clusters": len(keys),
            "samples": samples, "seed": seed, "alpha": alpha}


__all__ = ["NotEstimable", "wape", "rmsse", "wrmsse", "seasonal_naive", "two_party_margin",
           "weighted_poll_margin", "cluster_bootstrap_ci"]

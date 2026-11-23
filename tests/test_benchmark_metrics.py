from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from agora.validation.benchmark_metrics import (
    NotEstimable, cluster_bootstrap_ci, rmsse, seasonal_naive, two_party_margin,
    wape, weighted_poll_margin, wrmsse)


def test_wape_hand_computed():
    assert wape([2, 2, 2], [1, 2, 4]) == pytest.approx((1 + 0 + 2) / 7)


def test_wape_zero_denominator_is_not_estimable():
    with pytest.raises(NotEstimable):
        wape([1, 2], [0, 0])


@pytest.mark.parametrize("bad", [[], [float("nan")], [float("inf")], [[1, 2]]])
def test_non_finite_or_empty_input_refused(bad):
    with pytest.raises(NotEstimable):
        wape(bad, bad)


def test_length_mismatch_refused():
    with pytest.raises(NotEstimable):
        wape([1, 2], [1])


def test_rmsse_hand_computed_and_skips_leading_zeros():
    train = [0, 0, 1, 3, 2]        # starts at first non-zero: diffs 2, -1 -> scale (4+1)/2 = 2.5
    assert rmsse(train, [4, 4], [2, 3]) == pytest.approx(math.sqrt(((2 ** 2 + 1 ** 2) / 2) / 2.5))


@pytest.mark.parametrize("train", [[0, 0, 0], [5], [3, 3, 3]])
def test_rmsse_unusable_history_is_not_estimable(train):
    with pytest.raises(NotEstimable):
        rmsse(train, [1], [1])


def test_wrmsse_normalises_weights_and_matches_manual():
    t1, t2 = [1, 2, 3, 4], [2, 2, 4, 6]
    o1, p1, o2, p2 = [5], [4], [7], [5]
    expect = (1 * rmsse(t1, o1, p1) + 3 * rmsse(t2, o2, p2)) / 4
    assert wrmsse([t1, t2], [o1, o2], [p1, p2], [1, 3]) == pytest.approx(expect)
    assert wrmsse([t1, t2], [o1, o2], [p1, p2], [10, 30]) == pytest.approx(expect)  # scale-free weights


@pytest.mark.parametrize("w", [[-1, 2], [0, 0]])
def test_wrmsse_bad_weights(w):
    with pytest.raises(NotEstimable):
        wrmsse([[1, 2, 3], [1, 2, 3]], [[1], [1]], [[1], [1]], w)


def test_seasonal_naive_repeats_last_season_and_never_interpolates():
    assert list(seasonal_naive([1, 2, 3, 4, 5, 6, 7, 8, 9], 5, 7)) == [3, 4, 5, 6, 7]
    assert list(seasonal_naive(range(1, 8), 9, 7)) == [1, 2, 3, 4, 5, 6, 7, 1, 2]
    with pytest.raises(NotEstimable):
        seasonal_naive([1, 2, 3], 2, 7)


def test_two_party_margin():
    assert two_party_margin(52, 48) == pytest.approx(4.0)
    assert two_party_margin(40, 40) == 0.0
    with pytest.raises(NotEstimable):
        two_party_margin(0, 0)
    with pytest.raises(NotEstimable):
        two_party_margin(-1, 3)


def _poll(end, n, a, b):
    return {"end_date": end, "sample_size": n, "a_pct": a, "b_pct": b}


def test_poll_baseline_is_sample_size_weighted_and_cutoff_exact():
    cutoff = date(2020, 10, 20)
    polls = [_poll(date(2020, 10, 10), 100, 52, 48),      # +4
             _poll(date(2020, 10, 15), 300, 48, 52),      # -4
             _poll(date(2020, 10, 21), 5000, 90, 10),     # after cutoff: never used
             _poll(date(2020, 9, 22), 5000, 10, 90)]      # before the window (cutoff - 28d = Sep 22, exclusive)
    assert weighted_poll_margin(polls, cutoff) == pytest.approx((100 * 4 + 300 * -4) / 400)


def test_poll_baseline_window_boundary_is_inclusive_of_cutoff_exclusive_of_start():
    cutoff = date(2020, 10, 20)
    assert weighted_poll_margin([_poll(cutoff, 10, 55, 45)], cutoff) == pytest.approx(10.0)
    with pytest.raises(NotEstimable):
        weighted_poll_margin([_poll(date(2020, 9, 22), 10, 55, 45)], cutoff)


def test_poll_baseline_no_eligible_poll_is_not_estimable_and_bad_sample_refused():
    with pytest.raises(NotEstimable):
        weighted_poll_margin([], date(2020, 10, 20))
    with pytest.raises(NotEstimable):
        weighted_poll_margin([_poll(date(2020, 10, 10), 0, 52, 48)], date(2020, 10, 20))


def _clusters(n=12):
    rng = np.random.default_rng(0)
    return {f"s{i}": rng.normal(1.0 + 0.05 * i, 0.3, size=5) for i in range(n)}


def test_bootstrap_is_seed_deterministic_and_brackets_the_point():
    a = cluster_bootstrap_ci(_clusters(), samples=500, seed=7)
    b = cluster_bootstrap_ci(_clusters(), samples=500, seed=7)
    assert a == b and a["lo"] <= a["point"] <= a["hi"] and a["clusters"] == 12
    assert cluster_bootstrap_ci(_clusters(), samples=500, seed=8) != a


def test_bootstrap_too_few_clusters_or_missing_seed_is_not_estimable():
    with pytest.raises(NotEstimable):
        cluster_bootstrap_ci(_clusters(9), samples=500, seed=1)
    with pytest.raises(NotEstimable):
        cluster_bootstrap_ci(_clusters(), samples=500, seed=None)  # type: ignore[arg-type]
    with pytest.raises(NotEstimable):
        cluster_bootstrap_ci(_clusters(), samples=10, seed=1)


def test_bootstrap_resamples_whole_clusters():
    # one wildly different cluster must widen the interval versus a homogeneous set
    homo = {f"c{i}": np.full(4, 1.0) for i in range(12)}
    hetero = dict(homo, c0=np.full(4, 50.0))
    assert cluster_bootstrap_ci(homo, samples=300, seed=3)["hi"] - cluster_bootstrap_ci(homo, samples=300, seed=3)["lo"] == 0
    ci = cluster_bootstrap_ci(hetero, samples=300, seed=3)
    assert ci["hi"] > ci["lo"]


# ---- hardening slice (input validation); RMSSE keeps official M5 scale semantics ----
import datetime as _dt
import pytest as _pytest
from agora.validation import benchmark_metrics as _bm


def test_rmsse_scale_starts_at_first_nonzero_like_official_m5():
    # train [0,0,1,3,2]: official M5 scale uses diffs from first non-zero: (2^2+1^2)/2 = 2.5
    assert _bm.rmsse([0, 0, 1, 3, 2], [4, 4], [2, 3]) == _pytest.approx((2.5 / 2.5) ** 0.5)  # mse 2.5 / scale 2.5


def test_seasonal_naive_rejects_bools():
    with _pytest.raises(_bm.NotEstimable):
        _bm.seasonal_naive([1, 2, 3], True, 1)
    with _pytest.raises(_bm.NotEstimable):
        _bm.seasonal_naive([1, 2, 3], 2, True)


def test_two_party_margin_rejects_bools():
    with _pytest.raises(_bm.NotEstimable):
        _bm.two_party_margin(True, 40)


_P = {"end_date": _dt.date(2024, 10, 1), "sample_size": 100, "a_pct": 50, "b_pct": 45}


@_pytest.mark.parametrize("cutoff,window", [(_dt.datetime(2024, 10, 2), 28), (_dt.date(2024, 10, 2), 0),
                                            (_dt.date(2024, 10, 2), True), (_dt.date(2024, 10, 2), 2.5)])
def test_poll_margin_rejects_bad_cutoff_or_window(cutoff, window):
    with _pytest.raises(_bm.NotEstimable):
        _bm.weighted_poll_margin([_P], cutoff, window)


@_pytest.mark.parametrize("bad", [{**_P, "end_date": "2024-10-01"}, {**_P, "end_date": _dt.datetime(2024, 10, 1)},
                                  {k: v for k, v in _P.items() if k != "a_pct"}])
def test_poll_margin_rejects_malformed_poll_even_if_out_of_window(bad):
    with _pytest.raises(_bm.NotEstimable):
        _bm.weighted_poll_margin([_P, bad], _dt.date(2024, 10, 2))


def test_poll_margin_valid_future_poll_excluded_not_error():
    fut = {**_P, "end_date": _dt.date(2024, 11, 1), "a_pct": 10}
    assert _bm.weighted_poll_margin([_P, fut], _dt.date(2024, 10, 2)) == _bm.two_party_margin(50, 45)


@pytest.mark.parametrize("kw", [
    {"samples": 500.5}, {"samples": "500"}, {"samples": True}, {"samples": 99},
    {"min_clusters": 2.5}, {"min_clusters": True}, {"min_clusters": 0}, {"min_clusters": -1},
    {"alpha": float("nan")}, {"alpha": float("inf")}, {"alpha": True}, {"alpha": "0.05"},
    {"alpha": 0.0}, {"alpha": 1.0},
])
def test_bootstrap_invalid_parameters_are_not_estimable(kw):
    args = {"samples": 500, "seed": 7, "min_clusters": 10, **kw}
    with pytest.raises(NotEstimable):
        cluster_bootstrap_ci(_clusters(), **args)


@pytest.mark.parametrize("bad", [-1, -2**40, True, False, 1.0, "7", None])
def test_bootstrap_rejects_invalid_seed_as_not_estimable(bad):
    with pytest.raises(NotEstimable):
        cluster_bootstrap_ci(_clusters(), samples=500, seed=bad)  # type: ignore[arg-type]


def test_bootstrap_accepts_zero_seed():
    assert cluster_bootstrap_ci(_clusters(), samples=500, seed=0)["samples"] == 500

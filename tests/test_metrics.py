import networkx as nx
import numpy as np
import pytest

from agora.calibrate.metrics import (brier, calibration_error, log_loss, mae, network_comparison, rmse,
                                     score_forecast, score_probabilities, skill, wasserstein)


def test_mae_rmse_known_values():
    assert mae([1, 2, 3], [1, 2, 5]) == pytest.approx(2 / 3)
    assert rmse([0, 0], [3, 4]) == pytest.approx((12.5) ** 0.5)


def test_shape_and_empty_inputs_are_rejected():
    with pytest.raises(ValueError):
        mae([1, 2], [1])
    with pytest.raises(ValueError):
        mae([], [])
    with pytest.raises(ValueError):
        mae([np.nan], [1])


def test_brier_perfect_and_worst():
    assert brier([1, 0], [1, 0]) == 0.0
    assert brier([0, 1], [1, 0]) == 1.0


def test_brier_rejects_bad_inputs():
    with pytest.raises(ValueError):
        brier([1.2], [1])
    with pytest.raises(ValueError):
        brier([0.5], [0.5])


def test_log_loss_is_lower_for_better_probabilities():
    y = [1, 0, 1, 1]
    assert log_loss([0.9, 0.1, 0.9, 0.9], y) < log_loss([0.6, 0.4, 0.6, 0.6], y)


def test_calibration_error_zero_when_matched():
    p = [0.2] * 5 + [0.8] * 5
    y = [0, 0, 0, 0, 1] + [1, 1, 1, 1, 0]
    assert calibration_error(p, y, bins=10) == pytest.approx(0.0)


def test_calibration_error_detects_overconfidence():
    p = [0.9] * 10
    y = [1, 0] * 5
    assert calibration_error(p, y) == pytest.approx(0.4)


def test_wasserstein_identical_and_shifted():
    x = np.linspace(0, 1, 200)
    assert wasserstein(x, x) == pytest.approx(0.0)
    assert wasserstein(x, x + 1.0) == pytest.approx(1.0, abs=1e-3)


def test_skill_sign_and_zero_baseline():
    assert skill(0.5, 1.0) == pytest.approx(0.5)
    assert skill(2.0, 1.0) == pytest.approx(-1.0)
    assert skill(1.0, 0.0) == 0.0


def test_score_forecast_reports_skill_against_baseline():
    out = score_forecast([1, 2, 3], [1, 2, 3], [0, 0, 0])
    assert out["skill_mae"] == pytest.approx(1.0)


def test_score_probabilities_contains_all_measures():
    out = score_probabilities([0.9, 0.1], [1, 0], [0.5, 0.5])
    assert {"brier", "log_loss", "calibration_error"} <= set(out["model"])
    assert out["skill_brier"] > 0


def test_network_comparison_identical_graphs():
    g = nx.karate_club_graph()
    r = network_comparison(g, g)
    assert r["density_diff"] == 0 and r["clustering_diff"] == 0
    assert r["degree_wasserstein"] == pytest.approx(0.0)

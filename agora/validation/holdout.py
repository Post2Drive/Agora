"""Historical holdouts: train on one period, test on a later period that was never used.

The split is by date. Any record dated inside the test period is refused from the training
set, and the test period must start after the training period ends.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Sequence


@dataclass(frozen=True)
class Record:
    when: date
    features: dict
    outcome: float


def split(records: Sequence[Record], train_end: date, test_start: date, test_end: date):
    if test_start <= train_end:
        raise ValueError("the test period must start after the training period ends")
    train = [r for r in records if r.when <= train_end]
    test = [r for r in records if test_start <= r.when <= test_end]
    if not train or not test:
        raise ValueError("both periods need records")
    return train, test


def evaluate(records: Sequence[Record], train_end: date, test_start: date, test_end: date,
             predict: Callable[[list[Record], dict], float],
             baseline: Callable[[list[Record], dict], float]) -> dict:
    """Fit on the training period, predict each test record, and score against a baseline.

    `predict(train, features)` is the model. `baseline(train, features)` is a simple
    historical rule (for example the training-period average). Scores are MAE and skill.
    """
    from agora.calibrate.metrics import mae, skill

    train, test = split(records, train_end, test_start, test_end)
    obs = [r.outcome for r in test]
    model_pred = [predict(train, r.features) for r in test]
    base_pred = [baseline(train, r.features) for r in test]
    m, b = mae(model_pred, obs), mae(base_pred, obs)
    return {"n_train": len(train), "n_test": len(test), "model_mae": m, "baseline_mae": b,
            "skill_vs_baseline": skill(m, b)}

from datetime import date, datetime, timedelta, timezone

import pytest

from agora.validation.holdout import Record, evaluate, split
from agora.validation.knowledge import Event, KnowledgeStore
from agora.validation.prediction_log import PredictionLog


def test_prediction_is_written_once_and_cannot_be_rewritten(tmp_path):
    log = PredictionLog(tmp_path / "p.jsonl")
    log.predict("e1", "v1", {"x": 1}, 0.6)
    with pytest.raises(ValueError):
        log.predict("e1", "v2", {"x": 1}, 0.9)


def test_outcome_must_follow_prediction_and_be_recorded_once(tmp_path):
    log = PredictionLog(tmp_path / "p.jsonl")
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    log.predict("e1", "v1", {"x": 1}, 0.6, made_at=t0)
    with pytest.raises(ValueError):
        log.outcome("e1", 1, observed_at=t0 - timedelta(days=1))
    log.outcome("e1", 1, observed_at=t0 + timedelta(days=1))
    with pytest.raises(ValueError):
        log.outcome("e1", 0, observed_at=t0 + timedelta(days=2))
    assert log.scored()[0]["outcome"] == 1


def test_outcome_without_prediction_is_refused(tmp_path):
    with pytest.raises(ValueError):
        PredictionLog(tmp_path / "p.jsonl").outcome("missing", 1)


def test_split_refuses_overlapping_periods():
    recs = [Record(date(2000, 1, 1), {}, 1.0), Record(date(2005, 1, 1), {}, 2.0)]
    with pytest.raises(ValueError):
        split(recs, train_end=date(2004, 1, 1), test_start=date(2003, 1, 1), test_end=date(2006, 1, 1))


def test_evaluate_scores_model_against_baseline():
    recs = [Record(date(y, 1, 1), {}, float(y)) for y in range(2000, 2010)]
    out = evaluate(recs, train_end=date(2004, 12, 31), test_start=date(2005, 1, 1), test_end=date(2009, 12, 31),
                   predict=lambda train, f: float(max(r.when.year for r in train)) + 1,
                   baseline=lambda train, f: sum(r.outcome for r in train) / len(train))
    assert out["n_train"] == 5 and out["n_test"] == 5
    assert out["model_mae"] < out["baseline_mae"]
    assert out["skill_vs_baseline"] > 0


def test_knowledge_returns_nearest_events_and_respects_date_cutoff(tmp_path):
    ks = KnowledgeStore(tmp_path / "k.jsonl")
    ks.add(Event("a", "elections", "2019-05-23", {"turnout": 0.67}, 0.5, {"stance": 0.2}))
    ks.add(Event("b", "elections", "2014-05-16", {"turnout": 0.66}, 0.4, {"stance": 0.1}))
    ks.add(Event("c", "elections", "2024-06-04", {"turnout": 0.66}, 0.9, {"stance": 0.9}))
    near = ks.similar("elections", {"turnout": 0.66}, k=2, before="2024-01-01")
    assert {e.event_id for e, _ in near} == {"a", "b"}
    params = ks.transferred_params("elections", {"turnout": 0.66}, before="2024-01-01", k=2)
    assert 0.1 <= params["stance"] <= 0.2


def test_knowledge_refuses_duplicates_and_other_domains(tmp_path):
    ks = KnowledgeStore(tmp_path / "k.jsonl")
    ks.add(Event("a", "elections", "2019-05-23", {"turnout": 0.67}, 0.5))
    with pytest.raises(ValueError):
        ks.add(Event("a", "elections", "2019-05-23", {"turnout": 0.67}, 0.5))
    assert ks.similar("campaigns", {"turnout": 0.67}) == []

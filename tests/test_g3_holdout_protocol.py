"""G3 tests: one canonical, dataset-bound chronological holdout contract."""
from datetime import date

import pytest

from agora.validation.holdout import Record, evaluate, evaluate_probabilities, split
from agora.validation.protocol import HoldoutProtocol
from agora import governance

HASH_A = "a" * 64
HASH_B = "b" * 64


def protocol(**overrides):
    values = dict(
        protocol_id="g3-demo-v1",
        protocol_version="1.0",
        train_end=date(2024, 12, 31),
        test_start=date(2025, 1, 1),
        test_end=date(2025, 12, 31),
        minimum_train=3,
        minimum_test=3,
        grouping_key="group_id",
        dataset_id="dataset-2025-snapshot-01",
        source_hashes={"source-a": HASH_A, "source-b": HASH_B},
        source_roles={"source-a": "calibration", "source-b": "sealed_holdout"},
        baseline_id="historical-mean-v1",
        baseline_description="Training-period outcome mean",
        acceptance_thresholds={
            "model_mae": {"operator": "max", "value": 0.1},
            "skill_vs_baseline_mae": {"operator": "min", "value": 0.0},
        },
    )
    values.update(overrides)
    return HoldoutProtocol(**values)


def rows():
    return [
        Record(date(2024, 1, 1), {"x": 1}, 1.0, "train-a", "r1", "source-a", "calibration"),
        Record(date(2024, 5, 1), {"x": 2}, 2.0, "train-b", "r2", "source-a", "calibration"),
        Record(date(2024, 12, 31), {"x": 3}, 3.0, "train-c", "r3", "source-a", "calibration"),
        Record(date(2025, 1, 1), {"x": 4}, 4.0, "test-a", "r4", "source-b", "sealed_holdout"),
        Record(date(2025, 6, 1), {"x": 5}, 5.0, "test-b", "r5", "source-b", "sealed_holdout"),
        Record(date(2025, 12, 31), {"x": 6}, 6.0, "test-c", "r6", "source-b", "sealed_holdout"),
    ]


def identity():
    return {"dataset_id": "dataset-2025-snapshot-01",
            "source_hashes": {"source-a": HASH_A, "source-b": HASH_B}}


def test_protocol_validates_and_fingerprints_dataset_identity():
    p = protocol()
    summary = p.validate(rows(), **identity())
    assert summary["n_train"] == 3
    assert summary["n_test"] == 3
    assert summary["protocol_id"] == "g3-demo-v1"
    assert len(summary["protocol_hash"]) == 64
    assert summary["group_leakage_checked"] is True


def test_protocol_rejects_wrong_dataset_or_source_hashes():
    p = protocol()
    with pytest.raises(ValueError, match="dataset_id"):
        p.validate(rows(), dataset_id="another-dataset", source_hashes=identity()["source_hashes"])
    with pytest.raises(ValueError, match="source_hashes"):
        p.validate(rows(), dataset_id=identity()["dataset_id"], source_hashes={"source-a": HASH_B})
    with pytest.raises(ValueError, match="required"):
        p.validate(rows(), dataset_id=identity()["dataset_id"])


def test_protocol_rejects_group_leakage_and_missing_group_values():
    p = protocol()
    leaked = rows()
    leaked[-1] = Record(date(2025, 12, 31), {"x": 6}, 6.0, "train-a", "r6", "source-b", "sealed_holdout")
    with pytest.raises(ValueError, match="Group leakage"):
        p.validate(leaked, **identity())
    missing = rows()
    missing[-1] = Record(date(2025, 12, 31), {"x": 6}, 6.0, None, "r6", "source-b", "sealed_holdout")
    with pytest.raises(ValueError, match="Missing grouping key"):
        p.validate(missing, **identity())


def test_protocol_rejects_minimum_counts_and_duplicate_record_ids():
    p = protocol(minimum_test=4)
    with pytest.raises(ValueError, match="Insufficient holdout"):
        p.validate(rows(), **identity())
    duplicate = rows()
    duplicate[-1] = Record(date(2025, 12, 31), {"x": 6}, 6.0, "test-c", "r5", "source-b", "sealed_holdout")
    with pytest.raises(ValueError, match="Duplicate record_id"):
        protocol().validate(duplicate, **identity())


def test_protocol_rejects_invalid_date_windows():
    with pytest.raises(ValueError, match="test_start must be after train_end"):
        protocol(test_start=date(2024, 12, 31))
    with pytest.raises(ValueError, match="test_end must not precede"):
        protocol(test_end=date(2024, 12, 31))


def test_split_and_evaluate_share_the_canonical_protocol():
    p = protocol()
    train, test = split(rows(), protocol=p, **identity())
    assert len(train) == len(test) == 3
    result = evaluate(
        rows(), protocol=p, **identity(),
        predict=lambda train_rows, features: float(features["x"]),
        baseline=lambda train_rows, features: 3.0,
        baseline_id="historical-mean-v1",
        bootstrap_samples=300,
        data_snapshot_id="snapshot-2025-01",
        model_version="model-1.2.0",
        config_hash="c" * 64,
        reviewer_evidence={"reviewer_id": "reviewer-1", "review_status": "pending"},
    )
    assert result["n_train"] == 3 and result["n_test"] == 3
    assert result["evaluation_evidence"]["data_snapshot_id"] == "snapshot-2025-01"
    assert result["evaluation_evidence"]["model_version"] == "model-1.2.0"
    assert len(result["uncertainty"]["model_mae_ci95"]) == 2
    assert result["calibration"]["applicable"] is False
    assert result["threshold_assessment"]["overall"] == "pass"


def test_evidence_grade_evaluation_requires_protocol_bound_identity():
    with pytest.raises(ValueError, match="bound into the pre-registered protocol"):
        evaluate(
            rows(), train_end=date(2024, 12, 31), test_start=date(2025, 1, 1),
            test_end=date(2025, 12, 31),
            predict=lambda train_rows, features: 1.0,
            baseline=lambda train_rows, features: 1.0,
            dataset_id="dataset", source_hashes={"source": HASH_A},
            data_snapshot_id="snapshot", model_version="m1", config_hash="c" * 64,
            reviewer_evidence={"reviewer_id": "r1", "review_status": "pending"},
        )


def test_numeric_evaluation_reports_prediction_interval_coverage():
    p = protocol()
    result = evaluate(
        rows(), protocol=p, **identity(),
        predict=lambda train_rows, features: float(features["x"]),
        baseline=lambda train_rows, features: 3.0,
        baseline_id="historical-mean-v1",
        bootstrap_samples=300,
        prediction_interval=lambda train_rows, features: (float(features["x"]) - 0.5,
                                                            float(features["x"]) + 0.5),
        nominal_coverage=0.9,
        data_snapshot_id="snapshot-coverage-2025", model_version="interval-model-1",
        config_hash="e" * 64,
        reviewer_evidence={"reviewer_id": "reviewer-3", "review_status": "pending"},
    )
    assert result["coverage"]["applicable"] is True
    assert result["coverage"]["empirical_coverage"] == 1.0
    assert result["coverage"]["nominal_coverage"] == 0.9


def test_probability_evaluation_reports_calibration_and_brier_uncertainty():
    p = protocol(acceptance_thresholds={
        "model_brier": {"operator": "max", "value": 0.05},
        "model_calibration_error": {"operator": "max", "value": 0.2},
    })
    binary_rows = [
        Record(date(2024, 1, 1), {"x": 0}, 0.0, "ta", "a1", "source-a", "calibration"),
        Record(date(2024, 5, 1), {"x": 1}, 1.0, "tb", "a2", "source-a", "calibration"),
        Record(date(2024, 12, 1), {"x": 0}, 0.0, "tc", "a3", "source-a", "calibration"),
        Record(date(2025, 1, 1), {"x": 0}, 0.0, "ua", "b1", "source-b", "sealed_holdout"),
        Record(date(2025, 6, 1), {"x": 1}, 1.0, "ub", "b2", "source-b", "sealed_holdout"),
        Record(date(2025, 12, 1), {"x": 1}, 1.0, "uc", "b3", "source-b", "sealed_holdout"),
    ]
    result = evaluate_probabilities(
        binary_rows, p,
        predict_probability=lambda train_rows, features: 0.9 if features["x"] else 0.1,
        baseline_probability=lambda train_rows, features: 0.5,
        **identity(), baseline_id="historical-mean-v1", bootstrap_samples=300,
        data_snapshot_id="snapshot-prob-2025", model_version="prob-model-1",
        config_hash="d" * 64, reviewer_evidence={"reviewer_id": "reviewer-2", "review_status": "pending"},
    )
    assert result["calibration"]["applicable"] is True
    assert result["metrics"]["model"]["brier"] < result["metrics"]["baseline"]["brier"]
    assert len(result["uncertainty"]["model_brier_ci95"]) == 2
    assert result["threshold_assessment"]["overall"] == "pass"
    assert result["evaluation_evidence"]["model_version"] == "prob-model-1"


def test_wrong_baseline_identity_is_rejected():
    with pytest.raises(ValueError, match="baseline_id"):
        evaluate(
            rows(), protocol=protocol(), **identity(),
            predict=lambda train_rows, features: 1.0,
            baseline=lambda train_rows, features: 2.0,
            baseline_id="different-baseline", bootstrap_samples=300,
        )


def test_bootstrap_sample_count_must_be_sufficient():
    with pytest.raises(ValueError, match="at least 200"):
        evaluate(
            rows(), protocol=protocol(), **identity(),
            predict=lambda train_rows, features: 1.0,
            baseline=lambda train_rows, features: 2.0,
            baseline_id="historical-mean-v1",
            bootstrap_samples=100,
            data_snapshot_id="snapshot-2025-01", model_version="model-1.2.0",
            config_hash="c" * 64,
            reviewer_evidence={"reviewer_id": "reviewer-1", "review_status": "pending"},
        )


def test_sealed_holdout_source_cannot_enter_calibration_path(tmp_path):
    content = b"date,metric,value\n2025-01-01,registrations,10\n"
    governance.record_source(tmp_path, source_id="sealed-2025", content=content,
                              data_role="sealed_holdout", extraction_status="reviewed")
    source_path = tmp_path / "data" / "observations.csv"
    source_path.parent.mkdir()
    source_path.write_bytes(content)
    with pytest.raises(PermissionError, match="Sealed holdout"):
        governance.require_registered_source(tmp_path, source_path, allowed_roles=("calibration",))


def test_protocol_refuses_sealed_holdout_source_in_training_partition():
    contaminated = rows()
    contaminated[0] = Record(date(2024, 1, 1), {"x": 1}, 1.0,
                             "train-a", "r1", "source-b", "sealed_holdout")
    with pytest.raises(ValueError, match="Only calibration-role sources"):
        protocol().validate(contaminated, **identity())


def test_bootstrap_resamples_groups_not_rows_when_grouping_is_configured():
    grouped_rows = rows()
    grouped_rows.append(Record(date(2025, 7, 1), {"x": 5.5}, 5.5,
                               "test-b", "r7", "source-b", "sealed_holdout"))
    p = protocol(minimum_test=4)
    result = evaluate(
        grouped_rows, protocol=p, **identity(),
        predict=lambda train_rows, features: float(features["x"]),
        baseline=lambda train_rows, features: 3.0,
        baseline_id="historical-mean-v1",
        bootstrap_samples=300,
        data_snapshot_id="snapshot-clustered", model_version="model-clustered",
        config_hash="f" * 64,
        reviewer_evidence={"reviewer_id": "reviewer-clustered", "review_status": "pending"},
    )
    assert result["uncertainty"]["resampling_unit"] == "group"


def test_protocol_rejects_source_role_hash_inventory_mismatch():
    with pytest.raises(ValueError, match="cover exactly"):
        protocol(source_roles={"source-a": "calibration"})

"""Cross-process tests for the shared G4.1 validation-registry lock."""
from __future__ import annotations

import multiprocessing

from agora.validation.registry import add_entry, list_entries, transition_entry


def _evidence(registry_id: str) -> dict:
    return {
        "registry_id": registry_id,
        "domain": "general research",
        "use_case": "synthetic concurrency verification",
        "target": "registry consistency",
        "population": "synthetic test records",
        "geography": "test environment",
        "horizon": "test execution window",
        "data_provenance": {"dataset_id": "synthetic", "source_hashes": {"source": "a" * 64}},
        "holdout_design": {"protocol_fingerprint": "b" * 64, "n_train": 10, "n_test": 5},
        "baselines": {"id": "synthetic-baseline"},
        "metrics": {"consistency": 1.0},
        "thresholds": {"consistency": {"operator": "eq", "value": 1.0}},
        "results": {"threshold_assessment": {"overall": "pass"}},
        "uncertainty": {"note": "synthetic test only"},
        "model_version": "test:synthetic",
        "config_hash": "c" * 64,
        "limitations": "synthetic test data only",
        "approved_claims": [],
        "reviewer": "test owner",
    }


def _add_many(path: str, worker: int, count: int, result_queue) -> None:
    try:
        for index in range(count):
            add_entry(path, _evidence(f"worker-{worker}-entry-{index}"))
        result_queue.put(("add", worker, "ok"))
    except Exception as exc:  # surfaced in parent with the original diagnostic
        result_queue.put(("add", worker, f"{type(exc).__name__}: {exc}"))


def _advance_one(path: str, result_queue) -> None:
    try:
        transition_entry(path, "seed-entry", "protocol_drafted", reviewer="test reviewer",
                         rationale="concurrency test", evidence_refs=["synthetic://evidence"])
        result_queue.put(("transition", "ok"))
    except Exception as exc:
        result_queue.put(("transition", f"{type(exc).__name__}: {exc}"))


def _read_repeatedly(path: str, iterations: int, result_queue) -> None:
    try:
        previous = 0
        for _ in range(iterations):
            rows = list_entries(path)
            if len(rows) < previous:
                raise AssertionError("registry listing count moved backwards")
            previous = len(rows)
        result_queue.put(("reader", "ok"))
    except Exception as exc:
        result_queue.put(("reader", f"{type(exc).__name__}: {exc}"))


def test_concurrent_registration_review_and_listing_share_consistent_registry(tmp_path):
    path = tmp_path / "validation" / "registry.jsonl"
    add_entry(path, _evidence("seed-entry"))

    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    workers = [
        context.Process(target=_add_many, args=(str(path), worker, 8, results))
        for worker in range(3)
    ]
    workers.append(context.Process(target=_advance_one, args=(str(path), results)))
    workers.append(context.Process(target=_read_repeatedly, args=(str(path), 30, results)))

    for process in workers:
        process.start()
    for process in workers:
        process.join(45)

    assert all(not process.is_alive() for process in workers), "registry worker timed out"
    assert all(process.exitcode == 0 for process in workers)
    outcomes = [results.get(timeout=5) for _ in workers]
    assert all(outcome[-1] == "ok" for outcome in outcomes), outcomes

    rows = list_entries(path)
    assert len(rows) == 25  # seed + 3 workers * 8 registrations
    seed = next(row for row in rows if row["registry_id"] == "seed-entry")
    assert seed["status"] == "protocol_drafted"

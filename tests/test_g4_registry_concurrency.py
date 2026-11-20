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


def _competing_transition(path: str, barrier, result_queue, reviewer: str) -> None:
    try:
        barrier.wait(timeout=15)
        transition_entry(path, "race-entry", "protocol_drafted", reviewer=reviewer,
                         rationale="competing transition test", evidence_refs=["synthetic://race"])
        result_queue.put((reviewer, "transitioned"))
    except ValueError as exc:
        if "Invalid status transition" in str(exc):
            result_queue.put((reviewer, "already-transitioned"))
        else:
            result_queue.put((reviewer, f"error: {type(exc).__name__}: {exc}"))
    except Exception as exc:
        result_queue.put((reviewer, f"error: {type(exc).__name__}: {exc}"))


def _require_approval_repeatedly(path: str, iterations: int, barrier, result_queue) -> None:
    from agora.validation.registry import require_approval
    kwargs = {
        "domain": "general research",
        "use_case": "synthetic concurrency verification",
        "target": "registry consistency",
        "population": "synthetic test records",
        "geography": "test environment",
        "horizon": "test execution window",
        "model_version": "test:synthetic",
        "config_hash": "c" * 64,
        "requested_claims": ["Synthetic approval check only"],
    }
    try:
        barrier.wait(timeout=15)
        for _ in range(iterations):
            approval = require_approval(path, "approved-seed", **kwargs)
            if approval.get("status") != "passed":
                raise AssertionError("approval check returned a non-passed status")
            if approval.get("approved_claims") != ["Synthetic approval check only"]:
                raise AssertionError("approval check returned unexpected claims")
        result_queue.put(("approval-reader", "ok"))
    except Exception as exc:
        result_queue.put(("approval-reader", f"{type(exc).__name__}: {exc}"))


def _advance_pending_entry(path: str, barrier, result_queue) -> None:
    try:
        barrier.wait(timeout=15)
        transition_entry(path, "pending-entry", "protocol_drafted", reviewer="concurrent reviewer",
                         rationale="approval/read concurrency test", evidence_refs=["synthetic://pending"])
        result_queue.put(("review-writer", "ok"))
    except Exception as exc:
        result_queue.put(("review-writer", f"{type(exc).__name__}: {exc}"))


def _add_many_after_barrier(path: str, worker: int, count: int, barrier, result_queue) -> None:
    try:
        barrier.wait(timeout=15)
        _add_many(path, worker, count, result_queue)
    except Exception as exc:
        result_queue.put(("add-after-barrier", worker, f"{type(exc).__name__}: {exc}"))


def test_competing_transitions_from_same_state_allow_exactly_one_winner(tmp_path):
    path = tmp_path / "validation" / "registry.jsonl"
    add_entry(path, _evidence("race-entry"))

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    workers = [
        context.Process(target=_competing_transition, args=(str(path), barrier, results, reviewer))
        for reviewer in ("reviewer-a", "reviewer-b")
    ]

    for process in workers:
        process.start()
    for process in workers:
        process.join(30)

    assert all(not process.is_alive() for process in workers), "competing transition worker timed out"
    assert all(process.exitcode == 0 for process in workers)
    outcomes = [results.get(timeout=5) for _ in workers]
    statuses = [outcome[1] for outcome in outcomes]
    assert statuses.count("transitioned") == 1, outcomes
    assert statuses.count("already-transitioned") == 1, outcomes
    row = next(item for item in list_entries(path) if item["registry_id"] == "race-entry")
    assert row["status"] == "protocol_drafted"


def test_approval_checks_remain_consistent_during_registration_and_review(tmp_path):
    from datetime import datetime, timedelta, timezone

    from agora.validation.registry import require_approval

    path = tmp_path / "validation" / "registry.jsonl"
    add_entry(path, _evidence("approved-seed"))
    for state in ("protocol_drafted", "data_reviewed", "evaluation_pending"):
        transition_entry(path, "approved-seed", state, reviewer="seed reviewer",
                         rationale=f"seed {state}", evidence_refs=[f"synthetic://{state}"])
    transition_entry(
        path, "approved-seed", "passed", reviewer="seed approver", rationale="synthetic pass",
        evidence_refs=["synthetic://approval"], approved_claims=["Synthetic approval check only"],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    )
    add_entry(path, _evidence("pending-entry"))

    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    barrier = context.Barrier(3)
    workers = [
        context.Process(target=_add_many_after_barrier, args=(str(path), 7, 10, barrier, results)),
        context.Process(target=_advance_pending_entry, args=(str(path), barrier, results)),
        context.Process(target=_require_approval_repeatedly, args=(str(path), 200, barrier, results)),
    ]

    for process in workers:
        process.start()
    for process in workers:
        process.join(45)

    assert all(not process.is_alive() for process in workers), "approval concurrency worker timed out"
    assert all(process.exitcode == 0 for process in workers)
    outcomes = [results.get(timeout=5) for _ in workers]
    assert all(outcome[-1] == "ok" for outcome in outcomes), outcomes

    rows = list_entries(path)
    assert len(rows) == 12  # approved seed + pending entry + 10 concurrent registrations
    assert next(row for row in rows if row["registry_id"] == "pending-entry")["status"] == "protocol_drafted"
    approval = require_approval(
        path, "approved-seed", domain="general research",
        use_case="synthetic concurrency verification", target="registry consistency",
        population="synthetic test records", geography="test environment",
        horizon="test execution window", model_version="test:synthetic",
        config_hash="c" * 64, requested_claims=["Synthetic approval check only"],
    )
    assert approval["status"] == "passed"

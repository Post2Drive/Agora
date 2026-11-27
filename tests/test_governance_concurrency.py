"""The operation journal and source registry stay whole under concurrent writers."""
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agora import governance
from agora.sources import registry
from agora.validation.audit_log import _exclusive_lock


def _journal(project):
    return project / "governance" / "operations.jsonl"


def _sources(project):
    return project / "governance" / "sources.jsonl"


def _meet_after(monkeypatch, module, name):
    """Make two threads meet just after each has read the file, so a check-then-append race
    always interleaves. With a lock the second thread cannot read yet: the wait times out."""
    real = getattr(module, name)
    barrier = threading.Barrier(2)

    def read_then_wait(*args, **kwargs):
        rows = real(*args, **kwargs)
        try:
            barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            pass
        return rows

    monkeypatch.setattr(module, name, read_then_wait)
    return lambda: monkeypatch.setattr(module, name, real)


def _run_two(call):
    def guarded(value):
        try:
            return "ok", call(value)
        except Exception as exc:
            return "error", exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(guarded, range(2)))


def test_only_one_of_two_concurrent_finishes_is_recorded(tmp_path, monkeypatch):
    operation = governance.begin_operation(tmp_path, "write")
    restore = _meet_after(monkeypatch, governance, "_operation_rows")
    results = _run_two(lambda i: governance.finish_operation(
        tmp_path, operation["operation_id"], ("committed", "failed")[i]))
    restore()
    assert sorted(kind for kind, _ in results) == ["error", "ok"]
    error = next(value for kind, value in results if kind == "error")
    assert isinstance(error, ValueError) and "already" in str(error)
    assert [row["status"] == "pending" for row in governance.list_operations(tmp_path)] == [True, False]


def test_concurrent_identical_registrations_add_one_row(tmp_path, monkeypatch):
    path = _sources(tmp_path)
    restore = _meet_after(monkeypatch, registry, "_read_rows")
    results = _run_two(lambda _: registry.register_source(path, source_id="s1", content=b"same"))
    restore()
    assert [kind for kind, _ in results] == ["ok", "ok"]
    assert results[0][1] == results[1][1]
    assert [row["source_id"] for row in registry.list_sources(path)] == ["s1"]


def test_concurrent_conflicting_registrations_refuse_one(tmp_path, monkeypatch):
    path = _sources(tmp_path)
    restore = _meet_after(monkeypatch, registry, "_read_rows")
    results = _run_two(lambda i: registry.register_source(path, source_id="s1", content=b"%d" % i))
    restore()
    assert sorted(kind for kind, _ in results) == ["error", "ok"]
    assert "Conflicting source_id" in str(next(v for k, v in results if k == "error"))
    assert len(registry.list_sources(path)) == 1


def _assert_waits_for_lock(path, call):
    done = threading.Event()
    failures = []

    def run():
        try:
            call()
        except Exception as exc:
            failures.append(exc)
        finally:
            done.set()

    with _exclusive_lock(path.with_name(path.name + ".lock")):
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        assert not done.wait(0.5), "did not wait for the writer lock"
    assert done.wait(30)
    worker.join(30)
    assert failures == []


def test_begin_and_journal_reads_wait_for_the_writer_lock(tmp_path):
    governance.begin_operation(tmp_path, "first")
    _assert_waits_for_lock(_journal(tmp_path),
                           lambda: governance.begin_operation(tmp_path, "second"))
    _assert_waits_for_lock(_journal(tmp_path), lambda: governance.list_operations(tmp_path))
    _assert_waits_for_lock(_journal(tmp_path), lambda: governance.operation_states(tmp_path))


def test_registry_writes_and_reads_wait_for_the_writer_lock(tmp_path):
    path = _sources(tmp_path)
    registry.register_source(path, source_id="s1", content=b"1")
    _assert_waits_for_lock(path, lambda: registry.register_source(path, source_id="s2", content=b"2"))
    _assert_waits_for_lock(path, lambda: registry.list_sources(path))
    _assert_waits_for_lock(path, lambda: registry.get_source(path, "s1"))


def test_reading_files_written_before_the_lock_creates_nothing(tmp_path):
    source = tmp_path / "written"
    governance.begin_operation(source, "write")
    governance.record_source(source, source_id="s1", content=b"1", data_role="context")
    legacy = tmp_path / "legacy" / "governance"
    legacy.mkdir(parents=True)
    for name in ("operations.jsonl", "sources.jsonl"):
        (legacy / name).write_bytes((source / "governance" / name).read_bytes())
    assert len(governance.list_operations(legacy.parent)) == 1
    assert len(registry.list_sources(legacy / "sources.jsonl")) == 1
    assert sorted(p.name for p in legacy.iterdir()) == ["operations.jsonl", "sources.jsonl"]


def test_reading_an_absent_journal_or_registry_creates_nothing(tmp_path):
    assert governance.list_operations(tmp_path) == []
    assert registry.list_sources(_sources(tmp_path)) == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["journal", "registry"])
def test_append_refuses_a_file_with_an_unterminated_last_line(tmp_path, kind):
    if kind == "journal":
        path = _journal(tmp_path)
        governance.begin_operation(tmp_path, "first")
        write = lambda: governance.begin_operation(tmp_path, "second")
    else:
        path = _sources(tmp_path)
        registry.register_source(path, source_id="s1", content=b"1")
        write = lambda: registry.register_source(path, source_id="s2", content=b"2")
    torn = path.read_bytes().rstrip(b"\n")
    path.write_bytes(torn)
    with pytest.raises(ValueError, match="incomplete final record"):
        write()
    assert path.read_bytes() == torn


@pytest.mark.parametrize("name", ["operations.jsonl", "sources.jsonl"])
def test_append_refuses_a_symlinked_file(tmp_path, name):
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"")
    project = tmp_path / "project"
    (project / "governance").mkdir(parents=True)
    try:
        (project / "governance" / name).symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available")
    with pytest.raises(ValueError):
        if name == "operations.jsonl":
            governance.begin_operation(project, "write")
        else:
            governance.record_source(project, source_id="s1", content=b"1", data_role="context")
    assert outside.read_bytes() == b""


def _process_writer(project, worker, count):
    for index in range(count):
        operation = governance.begin_operation(project, "stress", details={"n": [worker, index]})
        governance.finish_operation(project, operation["operation_id"], "committed")
        governance.record_source(project, source_id=f"s-{worker}-{index}", content=b"x",
                                 data_role="context")
        governance.record_source(project, source_id=f"shared-{index}", content=b"y",
                                 data_role="context")


def test_processes_and_threads_lose_no_records(tmp_path):
    count, processes, threads = 8, 3, 3
    context = multiprocessing.get_context("spawn")
    workers = [context.Process(target=_process_writer, args=(str(tmp_path), f"p{i}", count))
               for i in range(processes)]
    for process in workers:
        process.start()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(lambda i: _process_writer(tmp_path, f"t{i}", count), range(threads)))
    for process in workers:
        process.join(300)
        assert process.exitcode == 0
    total = (processes + threads) * count
    assert len(governance.list_operations(tmp_path)) == total * 2
    assert governance.pending_operations(tmp_path) == []
    # "shared-N" is registered by every writer: exactly one row each. acquired_at is not identity.
    assert len(registry.list_sources(_sources(tmp_path))) == total + count

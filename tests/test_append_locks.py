"""The remaining JSONL appenders: one lock across each check and its append.

Each race test holds two writers just after their "is it already there?" read. Without the lock
both reach that point together and both append. With it, the second writer cannot read until the
first has finished, so the first one's wait times out and it carries on.
"""
import json
import threading
from pathlib import Path

import pytest

from agora import events, news_rss
from agora.pathsafe import UnsafePathError
from agora.validation import knowledge, prediction_log
from agora.validation.knowledge import Event, KnowledgeStore
from agora.validation.prediction_log import PredictionLog

from conftest import make_project


def _hold_after(monkeypatch, owner, name):
    """Make two threads meet right after owner.name returns, if they can both get there."""
    real = getattr(owner, name)
    barrier = threading.Barrier(2)

    def held(*args, **kwargs):
        result = real(*args, **kwargs)
        try:
            barrier.wait(timeout=1.5)
        except threading.BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(owner, name, held)


def _race(*calls):
    results, errors = [], []

    def run(call):
        try:
            results.append(call())
        except Exception as exc:                      # collected and asserted by the test
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(c,)) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads), "a writer did not finish"
    return results, errors


def _lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


def test_two_writers_cannot_both_record_a_prediction(tmp_path, monkeypatch):
    path = tmp_path / "p.jsonl"
    _hold_after(monkeypatch, PredictionLog, "_read")
    results, errors = _race(lambda: PredictionLog(path).predict("e1", "m", {}, 0.2),
                            lambda: PredictionLog(path).predict("e1", "m", {}, 0.8))
    assert len(results) == 1 and len(errors) == 1
    assert "already has a prediction" in str(errors[0])
    assert len(_lines(path)) == 1


def test_two_writers_cannot_both_record_an_outcome(tmp_path, monkeypatch):
    path = tmp_path / "p.jsonl"
    PredictionLog(path).predict("e1", "m", {}, 0.2)
    _hold_after(monkeypatch, PredictionLog, "_read")
    results, errors = _race(lambda: PredictionLog(path).outcome("e1", 0),
                            lambda: PredictionLog(path).outcome("e1", 1))
    assert len(results) == 1 and len(errors) == 1
    assert "already recorded" in str(errors[0])
    assert [r["kind"] for r in _lines(path)] == ["prediction", "outcome"]


@pytest.mark.parametrize("kind", ["prediction", "outcome"])
def test_a_log_with_two_records_for_one_event_is_not_scored(tmp_path, kind):
    path = tmp_path / "p.jsonl"
    log = PredictionLog(path)
    log.predict("e1", "m", {}, 0.2)
    log.outcome("e1", 1)
    extra = next(r for r in _lines(path) if r["kind"] == kind)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(extra) + "\n")
    with pytest.raises(ValueError, match=f"two {kind} records"):
        log.scored()


def test_two_writers_cannot_both_store_a_knowledge_event(tmp_path, monkeypatch):
    path = tmp_path / "k.jsonl"
    _hold_after(monkeypatch, KnowledgeStore, "_read")
    event = Event("k1", "d", "2020-01-01", {"x": 1.0}, 0.5)
    results, errors = _race(lambda: KnowledgeStore(path).add(event),
                            lambda: KnowledgeStore(path).add(event))
    assert len(results) == 1 and len(errors) == 1
    assert "already stored" in str(errors[0])
    assert len(_lines(path)) == 1


def test_two_writers_queue_the_same_event_once(tmp_path, monkeypatch):
    project = make_project(tmp_path, "ev")
    _hold_after(monkeypatch, events, "_read_queue")
    results, errors = _race(lambda: events.add(project, "The same report"),
                            lambda: events.add(project, "The same report"))
    assert errors == []
    assert sorted(r["duplicate"] for r in results) == [False, True]
    assert len(_lines(project / events.QUEUE)) == 1


def test_two_pulls_offer_a_candidate_once(tmp_path, monkeypatch):
    feed = ("<rss><channel><item><title>Campaign news</title><link>https://n.example.com/1</link>"
            "<pubDate>Wed, 13 Nov 2024 08:00:00 GMT</pubDate></item></channel></rss>")
    _hold_after(monkeypatch, news_rss, "_read_candidate_file")

    def pull():
        return news_rss.pull(tmp_path, ["https://n.example.com/rss"], ["campaign"], get=lambda u: feed)

    results, errors = _race(pull, pull)
    assert errors == []
    assert sorted(len(r["added"]) for r in results) == [0, 1]
    assert len(_lines(tmp_path / news_rss.CANDIDATES)) == 1


def _torn(path: Path, first: str) -> bytes:
    path.write_bytes((first + "\n" + '{"torn": ').encode("utf-8"))
    return path.read_bytes()


def test_a_torn_last_record_is_refused_not_merged(tmp_path):
    prediction = tmp_path / "k.jsonl"
    stored = json.dumps({"event_id": "k0", "domain": "d", "when": "2020", "features": {}, "outcome": 1})
    before = _torn(prediction, stored)
    with pytest.raises(ValueError):
        KnowledgeStore(prediction).add(Event("k1", "d", "2021", {}, 0.0))
    assert prediction.read_bytes() == before

    project = make_project(tmp_path, "torn")
    queue = project / events.QUEUE
    before = _torn(queue, json.dumps({"id": "old", "text": "old"}))
    with pytest.raises(ValueError, match="incomplete final record"):
        events.add(project, "A new report")
    assert queue.read_bytes() == before


@pytest.mark.parametrize("separator", [" ", " ", "\u0085"])
def test_an_event_with_a_unicode_line_separator_is_not_lost(tmp_path, separator):
    project = make_project(tmp_path, "sep")
    text = f"First part{separator}second part"
    events.add(project, text)
    assert [e["text"] for e in events.read(project)] == [text]
    assert events.add(project, text)["duplicate"] is True


@pytest.mark.parametrize("content", ['{"half": ', "[]", ""])
def test_sync_refuses_an_unreadable_synced_record(tmp_path, monkeypatch, content):
    project = make_project(tmp_path, "bad")
    events.add(project, "Some news")
    (project / events.SYNCED).write_text(content, encoding="utf-8")
    calls = []
    monkeypatch.setattr("agora.report.interact.inject", lambda *a: calls.append(a) or {"round": 0})
    with pytest.raises(ValueError, match="nothing was synced"):
        events.sync(project)
    assert calls == []


def test_two_syncs_inject_an_event_once(tmp_path, monkeypatch):
    project = make_project(tmp_path, "twice")
    events.add(project, "Some news")
    calls = []
    monkeypatch.setattr("agora.report.interact.inject",
                        lambda *a: calls.append(a) or {"round": 0})
    _hold_after(monkeypatch, events, "_synced")
    results, errors = _race(lambda: events.sync(project), lambda: events.sync(project))
    assert errors == []
    assert len(calls) == 1
    assert sorted(len(r["added"]) for r in results) == [0, 1]


def test_a_failure_part_way_keeps_what_was_already_synced(tmp_path, monkeypatch):
    project = make_project(tmp_path, "part")
    first = events.add(project, "First report")["id"]
    events.add(project, "Second report")
    calls = []

    def inject(_project, event, _round):
        calls.append(event["text"])
        if len(calls) == 2:
            raise RuntimeError("stopped")
        return {"round": 0}

    monkeypatch.setattr("agora.report.interact.inject", inject)
    with pytest.raises(RuntimeError):
        events.sync(project)
    assert list(json.loads((project / events.SYNCED).read_text(encoding="utf-8"))) == [first]
    events.sync(project)
    assert calls == ["First report", "Second report", "Second report"]


@pytest.mark.parametrize("write", [
    lambda p: PredictionLog(p).predict("e1", "m", {}, 0.5),
    lambda p: KnowledgeStore(p).add(Event("k1", "d", "2021", {}, 0.0)),
])
def test_a_linked_file_is_not_written_through(tmp_path, write):
    target = tmp_path / "outside.jsonl"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "linked.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    with pytest.raises(UnsafePathError):
        write(link)
    assert target.read_text(encoding="utf-8") == ""

import pytest

from agora import cutoff, events


def test_no_cutoff_allows_everything(tmp_path):
    assert cutoff.check(tmp_path, "2030-01-01") is None
    assert cutoff.check(tmp_path, "") is None


def test_cutoff_day_is_allowed_and_later_is_refused(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    assert cutoff.check(tmp_path, "2024-10-26") is None
    assert cutoff.check(tmp_path, "2024-10-25") is None
    assert "after the cutoff" in cutoff.check(tmp_path, "2024-10-27")


def test_undated_item_is_refused_once_cutoff_is_set(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    assert "no publish date" in cutoff.check(tmp_path, "")


def test_bad_date_is_refused_with_a_clear_message(tmp_path):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        cutoff.set_cutoff(tmp_path, "26 Oct 2024")


def test_add_refuses_an_item_after_the_cutoff(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    with pytest.raises(ValueError, match="after the cutoff"):
        events.add(tmp_path, "Results are in", published="2024-11-06")
    assert events.read(tmp_path) == []


def test_add_accepts_an_item_on_or_before_the_cutoff(tmp_path):
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    r = events.add(tmp_path, "Candidate visits Ohio", published="2024-10-20")
    assert r["ok"] and not r["duplicate"]


def test_sync_skips_items_after_the_cutoff_before_touching_the_run(tmp_path):
    # added before the cutoff was set, so the queue holds it
    events.add(tmp_path, "Late story", published="2024-11-02")
    cutoff.set_cutoff(tmp_path, "2024-10-26")
    # no study has been run here: a skip must happen before any injection is attempted
    r = events.sync(tmp_path)
    assert r["added"] == []
    assert "after the cutoff" in r["skipped"][0]["reason"]
    assert not (tmp_path / events.SYNCED).exists() or events._synced(tmp_path) == {}

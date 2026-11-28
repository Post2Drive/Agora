"""The home page reads the study state the server sends, and keeps archived studies out of the main list."""
from pathlib import Path

PAGE = (Path(__file__).resolve().parents[1] / "agora" / "web" / "static" / "index.html").read_text(encoding="utf-8")


def test_home_shows_a_label_for_each_state():
    for state, label in (("archived", "Archived"), ("complete", "Complete"), ("paused", "Paused"), ("draft", "Not set up")):
        assert f"p.state==='{state}'" in PAGE and label in PAGE


def test_archived_studies_are_listed_apart_from_active_ones():
    assert "ps.filter(p=>p.state!=='archived').map(card)" in PAGE
    assert "ps.filter(p=>p.state==='archived').map(card)" in PAGE

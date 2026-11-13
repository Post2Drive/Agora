"""Sharing a study never includes the reply cache, and leaves documents out unless asked."""
import sqlite3

import pytest

from agora.share import make_share


def _db(path):
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE t (x TEXT)")
    c.execute("INSERT INTO t VALUES ('hello')")
    c.commit()
    c.close()


@pytest.fixture
def study(project):
    _db(project / "agora.db")
    _db(project / "graph.db")
    _db(project / "llm_cache.db")
    (project / "sources").mkdir()
    (project / "sources" / "plan.md").write_text("secret plan", encoding="utf-8")
    (project / "report").mkdir()
    for n in ("report.html", "report.md", "report.json"):
        (project / "report" / n).write_text("x", encoding="utf-8")
    return project


def test_report_only(study, tmp_path):
    r = make_share(study, tmp_path / "out", report_only=True)
    assert sorted(r["copied"]) == ["report/report.html", "report/report.md"]
    assert not (tmp_path / "out" / "agora.db").exists()


def test_full_study_leaves_cache_and_documents_out(study, tmp_path):
    out = tmp_path / "out"
    make_share(study, out)
    assert (out / "scenario.yaml").exists() and (out / "agora.db").exists()
    assert not (out / "llm_cache.db").exists()
    assert not (out / "sources").exists() and not (out / "graph.db").exists()
    c = sqlite3.connect(str(out / "agora.db"))
    assert c.execute("SELECT x FROM t").fetchone()[0] == "hello"
    c.close()


def test_with_sources_adds_documents_but_still_no_cache(study, tmp_path):
    out = tmp_path / "out"
    make_share(study, out, with_sources=True)
    assert (out / "sources" / "plan.md").exists() and (out / "graph.db").exists()
    assert not (out / "llm_cache.db").exists()


def test_a_key_in_the_study_stops_the_share(study, tmp_path):
    p = study / "scenario.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\nllm:\n  api_key: sk-secret\n", encoding="utf-8")
    with pytest.raises(ValueError):
        make_share(study, tmp_path / "out")


def test_non_empty_target_is_refused(study, tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        make_share(study, tmp_path / "out")

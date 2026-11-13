"""Share a study safely: a clean copy that never includes the reply cache, your keys or settings,
and (unless asked) the text of your source documents."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import yaml


def _copy_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)                      # safe even while the database is in WAL mode
    finally:
        d.close()
        s.close()


def make_share(project, out, report_only: bool = False, with_sources: bool = False) -> dict:
    src, dst = Path(project), Path(out)
    if dst.exists() and any(dst.iterdir()):
        raise FileExistsError(f"{dst} already exists and is not empty.")
    sc = src / "scenario.yaml"
    if sc.exists():
        llm = (yaml.safe_load(sc.read_text(encoding="utf-8")) or {}).get("llm") or {}
        if llm.get("api_key"):
            raise ValueError("scenario.yaml contains an api_key. Remove it first; keys belong in `agora setup`.")
    dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    def cp(rel: str) -> None:
        f = src / rel
        if not f.is_file():
            return
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".db":
            _copy_db(f, target)
        else:
            shutil.copy2(f, target)
        copied.append(rel.replace("\\", "/"))

    if report_only:
        for rel in ("report/report.html", "report/report.md"):
            cp(rel)
        if not copied:
            raise ValueError("There is no report yet. Run: agora report " + str(src))
        left_out = ["everything except the report"]
    else:
        for rel in ("scenario.yaml", "prompt.txt", "agora.json", "agora.db", "graph.html", "graph.json",
                    "graph.graphml", "report/report.html", "report/report.md", "report/report.json"):
            cp(rel)
        left_out = ["llm_cache.db (reply cache)"]
        if with_sources:
            cp("graph.db")
            if (src / "sources").is_dir():
                shutil.copytree(src / "sources", dst / "sources")
                copied.append("sources/")
        else:
            left_out += ["sources/ and graph.db (your documents' text; add --with-sources to include)"]
    return {"copied": copied, "left_out": left_out}

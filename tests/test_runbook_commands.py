"""M2 item 8: execute the runbook command inventory (docs/M2_RUNBOOK_COMMAND_INVENTORY.md).

Every row ID in the inventory is either executed here as a real subprocess of the installed
CLI (`python -m agora.cli ...`) against a fresh temporary synthetic workspace, or is mapped
to a named test that must exist. The inventory is parsed, so removing or renaming a row,
or changing its argv template, fails this test. Synthetic data only; the simulation engine,
network, connectors and credentials are never used.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "M2_RUNBOOK_COMMAND_INVENTORY.md"
FIXTURE = ROOT / "agora" / "pilot_fixtures" / "synthetic-units-v1"
CHAIN_ID = "synthetic-pilot-chain"
STAGES = ["provision_audit", "import", "bind", "decision", "approval",
          "outcome_record", "outcome_review", "audit_verify", "report"]

# Rows that need the checked-in fixture or a racing writer to be altered; they are proven by
# named in-process tests (which must exist) rather than by mutating checked-in files here.
COVERED_ELSEWHERE = {
    "P07": ("tests/test_pilot_fixture.py", "test_symlinked_fixture_dir_manifest_or_payload_refused"),
    "P08": ("tests/test_pilot_fixture.py", "test_empty_fixture_version_refused"),
    "P09": ("tests/test_pilot_fixture.py", "test_manifest_and_payload_edited_together_fails_pin"),
    "B10": ("tests/test_backup.py", "test_chain_changing_during_copy_is_detected_and_cleaned"),
    "B12": ("tests/test_runbook_commands.py",
            "test_B12_lstat_failure_on_an_intermediate_ancestor_fails_closed"),
}

# ID -> exact argv template as written in the inventory (placeholders in <angle brackets>).
TEMPLATES = {
    "P01": "pilot list",
    "P02": "pilot start --fixture synthetic-units-v1 --workdir <fresh-workdir>",
    "P03": "pilot start --fixture __unknown_fixture__ --workdir <fresh-workdir>",
    "P04": "pilot start --fixture synthetic-units-v1 --workdir <nonempty-workdir>",
    "P05": "pilot start --workdir <fresh-workdir>",
    "P06": "pilot start --fixture synthetic-units-v1 --workdir <symlink-to-outside-empty-dir>",
    "P10": "pilot start --fixture synthetic-units-v1 --workdir <symlink-parent>/new-workdir",
    "P11": "pilot start --fixture synthetic-units-v1 --workdir <symlink-parent>/../new-workdir",
    "D01": "data import-csv --project <project> --csv <synthetic-csv> --schema <schema> --role scenario_input",
    "D02": "data snapshots --project <project>",
    "D03": "data show --project <project> --import-id <import-id>",
    "D04": "data rejected --project <project> --import-id <import-id>",
    "D05": "data show --project <project> --import-id __missing__",
    "A01": "audit timeline --decisions <decisions-db> --audit <audit-db> --decision-id <decision-id>",
    "A02": "audit timeline --decisions <decisions-db> --audit <audit-db> --decision-id __missing__",
    "A03": "audit verify --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain",
    "A04": "audit verify --audit <tampered-audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain",
    "R01": "reconcile --decisions <decisions-db> --audit <audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain",
    "R02": "reconcile --decisions <decisions-db> --audit <tampered-audit-db> --anchor <anchor-file> --chain-id synthetic-pilot-chain",
    "H01": "outcomes held --decisions <decisions-db>",
    "H02": "outcomes held --decisions <missing-or-invalid-db>",
    "B01": "backup --project <synthetic-project> --dest <new-backup-dir>",
    "B02": "backup verify --backup <backup-dir>",
    "B03": "restore --backup <backup-dir> --target <new-target-dir>",
    "B04": "backup --project <unmarked-project> --dest <new-backup-dir>",
    "B05": "backup --project <project-with-outside-symlink> --dest <new-backup-dir>",
    "B06": "backup verify --backup <malformed-backup>",
    "B07": "restore --backup <tampered-backup> --target <new-target-dir>",
    "B08": "backup --project <symlink-to-outside-project> --dest <new-backup-dir>",
    "B09": "backup verify --backup <symlink-to-outside-backup>` or `restore --backup <backup-dir> --target <symlink-to-outside-target>",
    "B11": "backup --project <symlink-parent>/project-with-linked-run-record-or-chain --dest <new-backup-dir>",
    "B13": "backup --project <symlink-parent>/../project --dest <new-backup-dir>",
}
EXPECTED_EXIT = {
    "P01": 0, "P02": 0, "P03": 2, "P04": 2, "P05": 2, "P06": 2, "P10": 2, "P11": 2,
    "D01": 2, "D02": 0, "D03": 0, "D04": 0, "D05": 2,
    "A01": 0, "A02": 1, "A03": 0, "A04": 1, "R01": 0, "R02": 2, "H01": {0, 1}, "H02": 2,
    "B01": 0, "B02": 0, "B03": 0, "B04": 2, "B05": 2, "B06": 2, "B07": 2, "B08": 2,
    "B09": 2, "B11": 2, "B13": 2,
}


# --------------------------------------------------------------------------- inventory parsing
def _inventory_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([A-Z]\d{2})\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rid = cells[0]
        assert rid not in rows, f"duplicate inventory row {rid}"
        rows[rid] = {"argv": cells[2].strip("`").strip(), "exit": cells[3]}
    return rows


def test_inventory_is_covered_exactly_and_argv_templates_match():
    rows = _inventory_rows()
    covered = set(TEMPLATES) | set(COVERED_ELSEWHERE)
    assert set(rows) == covered, f"inventory/test mismatch: {set(rows) ^ covered}"
    for rid, tpl in TEMPLATES.items():
        assert rows[rid]["argv"] == tpl, f"{rid}: inventory argv changed: {rows[rid]['argv']!r}"
        got = {int(x) for x in re.findall(r"\d+", rows[rid]["exit"])}
        assert re.fullmatch(r"\d+( or \d+)?", rows[rid]["exit"]), rows[rid]["exit"]
        want = EXPECTED_EXIT[rid]
        want = set(want) if isinstance(want, (set, frozenset)) else {want}
        assert got == want, f"{rid}: inventory exit changed: {rows[rid]['exit']!r}"
    assert set(EXPECTED_EXIT) == set(TEMPLATES)


RUNBOOK = ROOT / "docs" / "OPERATOR_RUNBOOK.md"


def _argv_prefix(argv: str) -> tuple[str, ...]:
    """Leading literal words of an argv (command path), stopping at the first option/placeholder."""
    out = []
    for w in argv.split():
        if w.startswith("-") or w.startswith("<"):
            break
        out.append(w)
    return tuple(out)


def test_operator_runbook_commands_are_bound_to_the_inventory():
    """Every `agora ...` command shown in a code fence of OPERATOR_RUNBOOK.md must be a command
    path that the executed inventory covers, with only inventory-known option names."""
    inv = _inventory_rows()
    known_paths = {_argv_prefix(r["argv"].split("` or `")[0]) for r in inv.values()}
    known_opts = {w for r in inv.values() for w in r["argv"].split() if w.startswith("--")}
    text = RUNBOOK.read_text(encoding="utf-8")
    fences = re.findall(r"```[a-z]*\n(.*?)```", text, flags=re.S)
    seen = 0
    for block in fences:
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("agora "):
                continue
            seen += 1
            argv = line[len("agora "):]
            assert _argv_prefix(argv) in known_paths, f"runbook command not in inventory: {line!r}"
            opts = {w for w in argv.split() if w.startswith("--")}
            assert opts <= known_opts, f"runbook option not in inventory: {line!r}"
    assert seen >= 5, "runbook shows too few executable commands to bind"


@pytest.mark.parametrize("rid", sorted(COVERED_ELSEWHERE))
def test_rows_proven_elsewhere_name_an_existing_test(rid):
    path, name = COVERED_ELSEWHERE[rid]
    assert f"def {name}(" in (ROOT / path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- harness
_WRAPPER = (
    "import sys\n"
    "from agora.cli import main\n"
    "try:\n    rc = main(sys.argv[1:])\nexcept SystemExit as e:\n    rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)\n"
    "loaded = any(m == 'agora.sim' or m.startswith('agora.sim.') for m in sys.modules)\n"
    "sys.stderr.write('\\nENGINE_LOADED=%s\\n' % loaded)\n"
    "sys.exit(rc or 0)\n"
)


def agora(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", _WRAPPER, *args], capture_output=True, text=True,
                       cwd=cwd, env=env, timeout=300)
    assert "ENGINE_LOADED=False" in r.stderr, f"simulation engine was imported by `agora {' '.join(args)}`"
    return r


def out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def tree(root: Path) -> dict[str, str]:
    snap: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            snap[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


def mklink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")


def tamper_chain(project: Path) -> None:
    db = sqlite3.connect(project / "audit" / "chain.sqlite3")
    for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        db.execute(f"DROP TRIGGER {n}")  # an attacker with file access can do this
    db.execute("UPDATE audit_events SET event_json = replace(event_json, 'decision', 'DECISION') WHERE seq = 2")
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """One completed synthetic run (row P02), shared read-only; mutating rows copy it."""
    root = tmp_path_factory.mktemp("runbook")
    work = root / "fresh"
    r = agora("pilot", "start", "--fixture", "synthetic-units-v1", "--workdir", str(work), cwd=root)
    assert r.returncode == 0, out(r)
    return {"root": root, "project": work / "synthetic-pilot", "result": r}


@pytest.fixture()
def proj(base, tmp_path):
    dst = tmp_path / "project"
    shutil.copytree(base["project"], dst)
    return dst


def paths(p: Path) -> dict[str, str]:
    return {"decisions": str(p / "decisions.db"), "audit": str(p / "audit" / "chain.sqlite3"),
            "anchor": str(p / "audit_anchor" / "anchor.jsonl")}


# --------------------------------------------------------------------------- pilot rows
def test_P01_pilot_list_is_read_only(tmp_path):
    r = agora("pilot", "list", cwd=tmp_path)
    assert r.returncode == 0 and "synthetic-units-v1" in r.stdout
    assert list(tmp_path.iterdir()) == []


def test_P02_guided_start_completes_with_synthetic_labels(base):
    r = base["result"]
    assert "COMPLETED" in r.stdout
    names = re.findall(r"\[(?:ok|\w+)\s*\]\s+(\w+)", r.stdout)
    assert names == STAGES
    rec = json.loads((base["project"] / "run_record.json").read_text(encoding="utf-8"))
    assert rec["data_class"] == "synthetic"
    assert rec["engine_invoked"] is False and rec["validated_prediction_enabled"] is False
    report = (base["project"] / "report" / "pilot_report.md").read_text(encoding="utf-8")
    assert "SIMULATED / SYNTHETIC" in report
    from agora.pilot import load_run_record
    assert load_run_record(base["project"])["status"] == "completed"


def test_P03_unknown_fixture_is_refused_with_no_side_effect(tmp_path):
    wd = tmp_path / "w"
    r = agora("pilot", "start", "--fixture", "__unknown_fixture__", "--workdir", str(wd), cwd=tmp_path)
    assert r.returncode == 2 and "FX_UNKNOWN_FIXTURE" in out(r)
    assert not wd.exists()


def test_P04_nonempty_workdir_is_refused_and_untouched(tmp_path):
    wd = tmp_path / "w"
    wd.mkdir()
    (wd / "sentinel.txt").write_bytes(b"keep me")
    r = agora("pilot", "start", "--fixture", "synthetic-units-v1", "--workdir", str(wd), cwd=tmp_path)
    assert r.returncode == 2 and "WORKDIR_NOT_EMPTY" in out(r)
    assert [p.name for p in wd.iterdir()] == ["sentinel.txt"]
    assert (wd / "sentinel.txt").read_bytes() == b"keep me"


def test_P05_missing_fixture_argument(tmp_path):
    wd = tmp_path / "w"
    r = agora("pilot", "start", "--workdir", str(wd), cwd=tmp_path)
    assert r.returncode == 2 and "FX_FIXTURE_REQUIRED" in out(r)
    assert not wd.exists()


def test_P06_symlinked_workdir_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    mklink(link, outside)
    r = agora("pilot", "start", "--fixture", "synthetic-units-v1", "--workdir", str(link), cwd=tmp_path)
    assert r.returncode == 2 and "WORKDIR_UNSAFE_PATH" in out(r)
    assert list(outside.iterdir()) == []


def test_P10_symlinked_workdir_ancestor(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "alias"
    mklink(link, outside)
    r = agora("pilot", "start", "--fixture", "synthetic-units-v1", "--workdir", str(link / "new-workdir"), cwd=tmp_path)
    assert r.returncode == 2 and "WORKDIR_UNSAFE_PATH" in out(r)
    assert list(outside.iterdir()) == []


def test_P11_dotdot_crossing_a_workdir_symlink(tmp_path):
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    link = tmp_path / "alias"
    mklink(link, outside / "sub")
    wd = f"{link}{os.sep}..{os.sep}new-workdir"
    r = agora("pilot", "start", "--fixture", "synthetic-units-v1", "--workdir", wd, cwd=tmp_path)
    assert r.returncode == 2 and "WORKDIR_UNSAFE_PATH" in out(r)
    assert not (outside / "new-workdir").exists() and not (tmp_path / "new-workdir").exists()


# --------------------------------------------------------------------------- data rows
def test_D01_standalone_import_is_denied_by_protected_mode(tmp_path):
    prj = tmp_path / "dataproj"
    r = agora("data", "import-csv", "--project", str(prj), "--csv", str(FIXTURE / "units.csv"),
              "--schema", str(FIXTURE / "schema.json"), "--role", "scenario_input", cwd=tmp_path)
    assert r.returncode == 2 and "POLICY_DENIED" in out(r)
    assert not (prj / "data" / "tabular.sqlite3").exists()  # nothing imported


def test_D02_to_D05_read_commands_on_the_p02_project(base, tmp_path):
    prj = base["project"]
    before = tree(prj)
    r = agora("data", "snapshots", "--project", str(prj), cwd=tmp_path)  # D02
    assert r.returncode == 0 and "U001" not in r.stdout
    import_id = json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))["import_id"]
    r = agora("data", "show", "--project", str(prj), "--import-id", import_id, cwd=tmp_path)  # D03
    assert r.returncode == 0 and import_id in r.stdout and "U001" not in r.stdout
    r = agora("data", "rejected", "--project", str(prj), "--import-id", import_id, cwd=tmp_path)  # D04
    assert r.returncode == 0 and "U001" not in r.stdout
    r = agora("data", "show", "--project", str(prj), "--import-id", "__missing__", cwd=tmp_path)  # D05
    assert r.returncode == 2 and "IMPORT_NOT_FOUND" in out(r)
    assert tree(prj) == before


# --------------------------------------------------------------------------- audit / reconcile / held
def test_A01_A02_audit_timeline_is_read_only(base, tmp_path):
    p = paths(base["project"])
    before = tree(base["project"])
    r = agora("audit", "timeline", "--decisions", p["decisions"], "--audit", p["audit"],
              "--decision-id", "decision-synthetic-001", cwd=tmp_path)
    assert r.returncode == 0 and "audit_entry" in r.stdout and "read-only" in r.stdout
    r = agora("audit", "timeline", "--decisions", p["decisions"], "--audit", p["audit"],
              "--decision-id", "__missing__", cwd=tmp_path)
    assert r.returncode == 1 and "NOT_FOUND:" in out(r)
    assert tree(base["project"]) == before


def test_A03_A04_audit_verify_intact_then_tampered(base, proj, tmp_path):
    p = paths(base["project"])
    before = tree(base["project"])
    r = agora("audit", "verify", "--audit", p["audit"], "--anchor", p["anchor"], "--chain-id", CHAIN_ID, cwd=tmp_path)
    assert r.returncode == 0 and "INTACT:" in r.stdout and "local sidecar" in r.stdout
    assert json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))["valid"] is True
    assert tree(base["project"]) == before
    tamper_chain(proj)
    q = paths(proj)
    mid = tree(proj)
    r = agora("audit", "verify", "--audit", q["audit"], "--anchor", q["anchor"], "--chain-id", CHAIN_ID, cwd=tmp_path)
    assert r.returncode == 1 and "NOT INTACT:" in r.stdout
    assert tree(proj) == mid


def test_R01_R02_reconcile_clean_then_blocked(base, proj, tmp_path):
    p = paths(base["project"])
    before = tree(base["project"])
    r = agora("reconcile", "--decisions", p["decisions"], "--audit", p["audit"], "--anchor", p["anchor"],
              "--chain-id", CHAIN_ID, cwd=tmp_path)
    assert r.returncode == 0 and "OK:" in r.stdout
    counts = json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))["counts"]
    assert all(counts[k] == 0 for k in ("missing", "conflict", "source_invalid", "orphan"))
    assert tree(base["project"]) == before
    tamper_chain(proj)
    q = paths(proj)
    mid = tree(proj)
    r = agora("reconcile", "--decisions", q["decisions"], "--audit", q["audit"], "--anchor", q["anchor"],
              "--chain-id", CHAIN_ID, cwd=tmp_path)
    assert r.returncode == 2 and "RECONCILE_BLOCKED:" in out(r)
    assert tree(proj) == mid


def test_H01_H02_held_outcomes(base, tmp_path):
    p = paths(base["project"])
    before = tree(base["project"])
    r = agora("outcomes", "held", "--decisions", p["decisions"], cwd=tmp_path)
    assert r.returncode == 0 and "OK:" in r.stdout  # nothing held in the completed synthetic run
    assert tree(base["project"]) == before
    r = agora("outcomes", "held", "--decisions", str(tmp_path / "missing.db"), cwd=tmp_path)
    assert r.returncode == 2 and "HELD_BLOCKED:" in out(r)
    assert list(tmp_path.iterdir()) == []


def test_H01_exit_1_when_an_outcome_is_held(proj, tmp_path):
    db = sqlite3.connect(proj / "decisions.db")
    names = [n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "decision_outcome_reviews" in names or any("review" in n for n in names)
    for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
        db.execute(f"DROP TRIGGER {n}")
    review_tbl = next(n for n in names if "review" in n and "outcome" in n)
    db.execute(f"DELETE FROM {review_tbl}")  # never-reviewed outcome is held (fail closed)
    db.commit()
    db.close()
    r = agora("outcomes", "held", "--decisions", str(proj / "decisions.db"), cwd=tmp_path)
    assert r.returncode == 1 and "HELD:" in r.stdout


# --------------------------------------------------------------------------- backup / restore rows
def test_B01_B02_B03_backup_verify_restore(base, tmp_path):
    before = tree(base["project"])
    bk, rs = tmp_path / "bk", tmp_path / "rs"
    r = agora("backup", "--project", str(base["project"]), "--dest", str(bk), cwd=tmp_path)
    assert r.returncode == 0 and "audit chain INTACT" in r.stdout
    mf = json.loads((bk / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    assert mf["synthetic_only"] is True and mf["files"]
    assert tree(base["project"]) == before
    r = agora("backup", "verify", "--backup", str(bk), cwd=tmp_path)
    assert r.returncode == 0 and "backup is intact" in r.stdout
    r = agora("restore", "--backup", str(bk), "--target", str(rs), cwd=tmp_path)
    assert r.returncode == 0 and "restored" in r.stdout
    for rel, digest in mf["files"].items():
        assert hashlib.sha256((rs / rel).read_bytes()).hexdigest() == digest


def test_B04_unmarked_source_refused(proj, tmp_path):
    (proj / "run_record.json").unlink()
    dest = tmp_path / "bk"
    r = agora("backup", "--project", str(proj), "--dest", str(dest), cwd=tmp_path)
    assert r.returncode == 2 and "SOURCE_NOT_SYNTHETIC" in out(r) and not dest.exists()


def test_B05_in_tree_symlink_refused(proj, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    mklink(proj / "report" / "linked", outside)
    dest = tmp_path / "bk"
    r = agora("backup", "--project", str(proj), "--dest", str(dest), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r) and not dest.exists()


def test_B06_malformed_manifest_refused(base, tmp_path):
    bk = tmp_path / "bk"
    assert agora("backup", "--project", str(base["project"]), "--dest", str(bk), cwd=tmp_path).returncode == 0
    mf = bk / "BACKUP_MANIFEST.json"
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["files"] = ["not", "a", "map"]
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    r = agora("backup", "verify", "--backup", str(bk), cwd=tmp_path)
    assert r.returncode == 2 and "BACKUP_MANIFEST_INVALID" in out(r) and "Traceback" not in out(r)


def test_B07_tampered_backup_refused_and_target_removed(base, tmp_path):
    bk, rs = tmp_path / "bk", tmp_path / "rs"
    assert agora("backup", "--project", str(base["project"]), "--dest", str(bk), cwd=tmp_path).returncode == 0
    victim = bk / "data" / "report" / "pilot_report.md"
    victim.write_bytes(victim.read_bytes() + b"tampered")
    after = tree(bk)
    r = agora("restore", "--backup", str(bk), "--target", str(rs), cwd=tmp_path)
    assert r.returncode == 2
    assert any(c in out(r) for c in ("BACKUP_FILE_MODIFIED", "BACKUP_NOT_INTACT", "RESTORED_NOT_INTACT"))
    assert not rs.exists() and tree(bk) == after


def test_B08_project_root_symlink_refused(base, tmp_path):
    link = tmp_path / "linked-project"
    mklink(link, base["project"])
    dest = tmp_path / "bk"
    r = agora("backup", "--project", str(link), "--dest", str(dest), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r) and not dest.exists()


def test_B09_backup_and_restore_root_symlinks_refused(base, tmp_path):
    bk = tmp_path / "bk"
    assert agora("backup", "--project", str(base["project"]), "--dest", str(bk), cwd=tmp_path).returncode == 0
    link_bk = tmp_path / "linked-backup"
    mklink(link_bk, bk)
    r = agora("backup", "verify", "--backup", str(link_bk), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r)
    outside = tmp_path / "outside"
    outside.mkdir()
    link_t = tmp_path / "linked-target"
    mklink(link_t, outside)
    r = agora("restore", "--backup", str(bk), "--target", str(link_t), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r)
    assert list(outside.iterdir()) == []


def test_B11_parent_symlink_refused_before_any_read(base, tmp_path):
    parent = tmp_path / "alias"
    mklink(parent, base["project"].parent)
    dest = tmp_path / "bk"
    r = agora("backup", "--project", str(parent / "synthetic-pilot"), "--dest", str(dest), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r) and not dest.exists()


def test_B13_dotdot_through_symlink_refused(base, tmp_path):
    sub = tmp_path / "outside" / "sub"
    sub.mkdir(parents=True)
    alias = tmp_path / "alias"
    mklink(alias, sub)
    dest = tmp_path / "bk"
    argv_project = f"{alias}{os.sep}..{os.sep}project"
    shutil.copytree(base["project"], tmp_path / "outside" / "project")
    r = agora("backup", "--project", argv_project, "--dest", str(dest), cwd=tmp_path)
    assert r.returncode == 2 and "UNSAFE_PATH" in out(r) and not dest.exists()


# --------------------------------------------------------------------------- B12 (in-process)
def test_B12_lstat_failure_on_an_intermediate_ancestor_fails_closed(base, tmp_path, monkeypatch):
    import agora.backup as mod
    project = base["project"]
    ancestor = project.parent  # an intermediate ancestor, not the project root itself
    real = os.lstat

    def flaky(path, *a, **k):
        if Path(os.fspath(path)) == ancestor:
            raise PermissionError("simulated unreadable ancestor")
        return real(path, *a, **k)

    monkeypatch.setattr(mod.os, "lstat", flaky)
    dest = tmp_path / "bk"
    with pytest.raises(mod.BackupBlocked) as e:
        mod.backup(project, dest)
    assert e.value.code == "UNSAFE_PATH"
    assert not dest.exists()

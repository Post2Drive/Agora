from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agora import pilot_fixture as pf
from agora.pilot import PROJECT_ID, load_run_record, run_pilot


def _copy_root(tmp_path: Path) -> Path:
    dst = tmp_path / "fx"
    shutil.copytree(pf.FIXTURE_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "__init__.py"))
    return dst


def test_checked_in_fixture_lists_and_loads():
    assert pf.list_fixtures() == ["synthetic-units-v1"]
    fx = pf.load_fixture("synthetic-units-v1")
    assert fx.csv_bytes.startswith(b"unit_id,") and fx.manifest_hash.startswith("sha256:")
    assert set(fx.file_hashes) == set(pf.REQUIRED_FILES)


@pytest.mark.parametrize("bad", ["nope", "latest", "", "../x", "SYNTHETIC-UNITS-V1", None])
def test_unknown_fixture_fails_with_stable_code(bad):
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture(bad)
    assert e.value.code == "FX_UNKNOWN_FIXTURE"


@pytest.mark.parametrize("name", ["units.csv", "schema.json", "binding.json"])
def test_altered_file_bytes_fail_hash_check(tmp_path, name):
    root = _copy_root(tmp_path)
    p = root / "synthetic-units-v1" / name
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture("synthetic-units-v1", root)
    assert e.value.code == "FX_HASH_MISMATCH"


def test_missing_file_and_bad_manifest_fail_closed(tmp_path):
    root = _copy_root(tmp_path)
    (root / "synthetic-units-v1" / "units.csv").unlink()
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture("synthetic-units-v1", root)
    assert e.value.code == "FX_FILE_MISSING"
    root = _copy_root(tmp_path / "b")
    man = root / "synthetic-units-v1" / "manifest.json"
    d = json.loads(man.read_text())
    d["synthetic_only"] = False
    man.write_text(json.dumps(d))
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture("synthetic-units-v1", root)
    assert e.value.code == "FX_MANIFEST_INVALID"
    man.write_text("{not json")
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture("synthetic-units-v1", root)
    assert e.value.code == "FX_MANIFEST_INVALID"


def test_unpinned_binding_refused(tmp_path):
    import hashlib
    root = _copy_root(tmp_path)
    d = root / "synthetic-units-v1"
    b = json.loads((d / "binding.json").read_text())
    b["binding_version"] = "latest"
    (d / "binding.json").write_text(json.dumps(b))
    m = json.loads((d / "manifest.json").read_text())
    m["files"]["binding.json"] = "sha256:" + hashlib.sha256((d / "binding.json").read_bytes()).hexdigest()
    (d / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(pf.FixtureError) as e:
        pf.load_fixture("synthetic-units-v1", root)
    assert e.value.code == "FX_FILE_INVALID"


def test_run_pilot_records_fixture_hashes_and_unknown_fixture_creates_nothing(tmp_path):
    res = run_pilot(tmp_path / "ok")
    assert res.status == "completed"
    rec = load_run_record(tmp_path / "ok" / PROJECT_ID)
    fx = pf.load_fixture("synthetic-units-v1")
    assert rec["fixture"] == {"fixture_id": "synthetic-units-v1", "fixture_version": fx.version,
                              "manifest_hash": fx.manifest_hash, "file_hashes": fx.file_hashes}
    with pytest.raises(pf.FixtureError):
        run_pilot(tmp_path / "bad", fixture_id="nope")
    assert not (tmp_path / "bad").exists()


def _cli(*args, cwd):
    return subprocess.run([sys.executable, "-m", "agora", "pilot", *args], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


def test_one_command_start_in_fresh_subprocess(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    work = tmp_path / "w"
    r = _cli("start", "--fixture", "synthetic-units-v1", "--workdir", str(work), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    order = [ln.split("]")[1].strip() for ln in r.stdout.splitlines() if ln.startswith("  [")]
    assert order == ["provision_audit", "import", "bind", "decision", "approval",
                     "outcome_record", "outcome_review", "audit_verify", "report"]
    assert (work / PROJECT_ID / "run_record.json").is_file()
    # re-run into the same workdir refuses and keeps the existing files
    before = (work / PROJECT_ID / "run_record.json").read_bytes()
    r2 = _cli("start", "--fixture", "synthetic-units-v1", "--workdir", str(work), cwd=repo)
    assert r2.returncode == 2 and "WORKDIR_NOT_EMPTY" in r2.stdout
    assert (work / PROJECT_ID / "run_record.json").read_bytes() == before


def test_cli_missing_or_unknown_fixture_lists_valid_ids_and_creates_nothing(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    r = _cli("start", "--workdir", str(tmp_path / "a"), cwd=repo)
    assert r.returncode == 2 and "FX_FIXTURE_REQUIRED" in r.stdout and "synthetic-units-v1" in r.stdout
    r = _cli("start", "--fixture", "nope", "--workdir", str(tmp_path / "b"), cwd=repo)
    assert r.returncode == 2 and "FX_UNKNOWN_FIXTURE" in r.stdout and "synthetic-units-v1" in r.stdout
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()
    assert _cli("list", cwd=repo).stdout.split() == ["synthetic-units-v1"]


def test_start_never_imports_engine_or_network(tmp_path):
    code = ("import sys,socket\n"
            "def _no(*a,**k): raise RuntimeError('network blocked')\n"
            "socket.socket.connect=_no; socket.create_connection=_no\n"
            "from agora.pilot import main\n"
            f"rc=main(['start','--fixture','synthetic-units-v1','--workdir',r'{tmp_path / 'w'}'])\n"
            "bad=[m for m in sys.modules if m=='agora.sim' or m.startswith('agora.sim.')]\n"
            "print('SIM_IMPORTED' if bad else 'NO_SIM', rc)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                       capture_output=True, text=True, timeout=120)
    assert "NO_SIM 0" in r.stdout, r.stdout + r.stderr

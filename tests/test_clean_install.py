"""M2 clean-checkout install/start proof (synthetic data only, no engine, no network use by Agora).

Builds a wheel-style install of a copy of the checkout into an isolated venv, then runs the
installed `agora` CLI from a directory outside the repo with PYTHONPATH/PYTHONHOME cleared.
Proves: the package resolves inside the venv (not the source tree), the synthetic fixture is
packaged, `pilot list` and `pilot start` succeed, flags stay False, and agora.sim is never imported.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "synthetic-units-v1"


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _bin(vdir: Path, name: str) -> str:
    sub = "Scripts" if os.name == "nt" else "bin"
    exe = ".exe" if os.name == "nt" else ""
    return str(vdir / sub / (name + exe))


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    base = tmp_path_factory.mktemp("clean_install")
    src = base / "checkout"
    shutil.copytree(ROOT, src, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.egg-info", "build", "dist", ".pytest_cache", "tests"))
    vdir = base / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(vdir)
    py = _bin(vdir, "python")
    r = subprocess.run([py, "-m", "pip", "install", "--quiet", str(src)], capture_output=True,
                       text=True, env=_env(), cwd=base, timeout=900)
    if r.returncode != 0:
        pytest.fail("pip install failed:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    outside = base / "outside"
    outside.mkdir()
    return {"py": py, "vdir": vdir, "src": src, "outside": outside, "base": base}


def _run(inst, args, **kw):
    return subprocess.run(args, capture_output=True, text=True, env=_env(), cwd=inst["outside"],
                          timeout=300, **kw)


def test_package_resolves_inside_venv_not_source_tree(installed):
    r = _run(installed, [installed["py"], "-c",
                         "import agora,sys;print(agora.__file__);print('agora.sim' in sys.modules)"])
    assert r.returncode == 0, r.stderr
    path, sim = r.stdout.split()
    p = Path(path).resolve()
    assert installed["vdir"].resolve() in p.parents
    assert installed["src"].resolve() not in p.parents
    assert sim == "False"


def test_fixture_is_packaged(installed):
    r = _run(installed, [installed["py"], "-c",
                         "import agora.pilot_fixtures as f,pathlib;"
                         "d=pathlib.Path(f.__file__).parent/'%s';"
                         "print(sorted(p.name for p in d.iterdir()))" % FIXTURE])
    assert r.returncode == 0, r.stderr
    for name in ("manifest.json", "units.csv", "schema.json", "binding.json"):
        assert name in r.stdout


def test_installed_cli_pilot_list_and_start(installed):
    cli = _bin(installed["vdir"], "agora")
    assert Path(cli).exists(), "console entry point missing"
    r = _run(installed, [cli, "pilot", "list"])
    assert r.returncode == 0, r.stderr
    assert FIXTURE in r.stdout
    wd = installed["base"] / "work"
    r = _run(installed, [cli, "pilot", "start", "--fixture", FIXTURE, "--workdir", str(wd)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "synthetic" in r.stdout.lower()
    records = list(wd.rglob("run_record.json"))
    assert len(records) == 1, "exactly one run_record.json expected, got %r" % records
    data = json.loads(records[0].read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["engine_invoked"] is False
    assert data["validated_prediction_enabled"] is False


def test_start_does_not_import_sim_engine(installed):
    wd = installed["base"] / "work2"
    code = ("import sys;from agora.pilot import main;"
            "rc=main(['start','--fixture','%s','--workdir',r'%s']);"
            "print(rc, any(m=='agora.sim' or m.startswith('agora.sim.') for m in sys.modules))"
            % (FIXTURE, wd))
    r = _run(installed, [installed["py"], "-c", code])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "0 False"


def test_console_script_entry_does_not_import_sim_engine(installed):
    """Same check via the installed console-script entry point (agora.cli:main), not agora.pilot.main."""
    wd = installed["base"] / "work3"
    code = ("import sys;from importlib.metadata import entry_points;"
            "ep=[e for e in entry_points(group='console_scripts') if e.name=='agora'][0];"
            "assert ep.value=='agora.cli:main',ep.value;"
            "sys.argv=['agora','pilot','start','--fixture','%s','--workdir',r'%s'];"
            "rc=0\n"
            "try:\n ep.load()()\nexcept SystemExit as e:\n rc=e.code or 0\n"
            "print(rc, any(m=='agora.sim' or m.startswith('agora.sim.') for m in sys.modules))"
            % (FIXTURE, wd))
    r = _run(installed, [installed["py"], "-c", code])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "0 False"

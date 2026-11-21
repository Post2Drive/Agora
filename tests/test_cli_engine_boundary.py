"""`agora pilot` / `agora data` must not import the simulation engine."""
import subprocess
import sys

from agora import cli


def _run(code: str) -> str:
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_importing_cli_does_not_load_engine():
    out = _run("import sys, agora.cli; print('agora.sim.engine' in sys.modules)")
    assert out == "False"


def test_pilot_dispatch_does_not_load_engine():
    out = _run(
        "import sys\n"
        "from agora import cli\n"
        "try:\n    cli.main(['pilot','--help'])\nexcept SystemExit:\n    pass\n"
        "print('agora.sim.engine' in sys.modules)"
    )
    assert out.splitlines()[-1] == "False"


def test_local_constants_match_engine():
    from agora.sim import engine
    assert cli.SCENARIO_FILE == engine.SCENARIO_FILE
    assert cli.DB_FILE == engine.DB_FILE

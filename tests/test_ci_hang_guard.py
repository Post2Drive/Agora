"""The CI job must stop on its own when stuck, and a stuck test must leave a stack trace."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_test_job_has_a_time_limit():
    job = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"))["jobs"]["test"]
    # above the slowest Windows runs seen (about 25 minutes), far below GitHub's 360 minute default
    assert 30 <= job["timeout-minutes"] <= 60


def test_slow_test_dumps_stacks(pytestconfig):
    assert 0 < float(pytestconfig.getini("faulthandler_timeout")) <= 600

"""M3 slice 4.3: `agora run --governed-input` (CLI only; no agora/sim edit). Synthetic data, mock LLM, no network."""
from __future__ import annotations

import pytest

from agora import cli
from conftest import make_project
from test_engine_governed_input import agent_count, gi, provenance_bytes


@pytest.fixture()
def project(tmp_path):
    return make_project(tmp_path)


def run(project, *extra):
    return cli.main(["run", str(project), "--mock", "--rounds", "1", *extra])


def test_default_policy_source_denies_so_a_governed_run_fails_closed(project, capsys):
    # no production identity adapter: the real _governed_policy() returns None -> policy denied
    assert cli._governed_policy() is None
    rc = run(project, "--governed-input", "import-1", "--binding", "b.json", "--pack", "p.json", "--mapping", "m.json")
    assert rc == 3 and "GOVERNED_INPUT_REFUSED" in capsys.readouterr().err
    assert provenance_bytes(project) is None and agent_count(project) == 0


def test_force_is_refused_with_governed_input(project, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_governed_input", lambda a, p: gi())
    assert run(project, "--governed-input", "import-1", "--force") == 2
    assert "GOVERNED_FORCE_REFUSED" in capsys.readouterr().err
    assert provenance_bytes(project) is None and agent_count(project) == 0


def test_governed_flags_without_governed_input_are_refused(project, capsys):
    assert run(project, "--mapping", "m.json") == 2
    assert "need --governed-input" in capsys.readouterr().err
    assert agent_count(project) == 0


def test_latest_and_missing_files_are_refused(project, capsys):
    assert run(project, "--governed-input", "latest", "--binding", "b", "--pack", "p", "--mapping", "m") == 3
    assert run(project, "--governed-input", "import-1") == 3  # no binding/pack/mapping
    assert provenance_bytes(project) is None and agent_count(project) == 0


def test_verified_input_runs_and_writes_the_envelope(project, monkeypatch):
    monkeypatch.setattr(cli, "_governed_input", lambda a, p: gi())
    assert run(project, "--governed-input", "import-1") == 0
    assert provenance_bytes(project) and agent_count(project) > 0


def test_changed_input_cannot_resume_a_governed_run(project, monkeypatch, capsys):
    from test_engine_governed_input import make_package
    monkeypatch.setattr(cli, "_governed_input", lambda a, p: gi())
    assert run(project, "--governed-input", "import-1") == 0
    before = provenance_bytes(project)
    monkeypatch.setattr(cli, "_governed_input", lambda a, p: gi(make_package(import_id="import-OTHER")))
    assert run(project, "--governed-input", "import-OTHER") == 3
    assert "GOVERNED_INPUT_REFUSED" in capsys.readouterr().err
    assert provenance_bytes(project) == before


def test_legacy_run_without_flag_is_unchanged(project):
    assert run(project) == 0
    assert provenance_bytes(project) is None

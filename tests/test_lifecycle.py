"""Study state is read from what is on disk; only 'archived' is stored."""
import json

import pytest

from agora import lifecycle
from agora.cli import main
from agora.lifecycle import LifecycleError, study_state
from agora.sim.engine import Simulation


def test_folder_with_only_a_prompt_is_a_draft(tmp_path):
    (tmp_path / "prompt.txt").write_text("how will people react?")
    assert study_state(tmp_path) == "draft"


def test_scenario_without_a_run_is_ready(project):
    assert study_state(project) == "ready"


def test_a_running_job_is_running(project):
    assert study_state(project, job_running=True) == "running"


def test_partly_done_is_paused_and_finished_is_complete(project):
    sim = Simulation(project)
    sim.run(rounds=1)
    assert study_state(project) == "paused"
    sim.run()
    assert study_state(project) == "complete"


def test_state_survives_a_restart_because_it_is_read_from_disk(project):
    Simulation(project).run(rounds=2)
    assert study_state(project) == "paused"
    assert study_state(project) == "paused"          # a new reader, same answer


def test_archive_wins_and_undo_restores_the_facts(project):
    Simulation(project).run(rounds=1)
    lifecycle.archive(project)
    assert study_state(project) == "archived"
    assert study_state(project, job_running=True) == "archived"
    lifecycle.unarchive(project)
    assert study_state(project) == "paused"


def test_archive_keeps_the_title_and_other_fields(project):
    (project / "agora.json").write_text(json.dumps({"title": "T", "forked_from": "x"}))
    lifecycle.archive(project)
    lifecycle.unarchive(project)
    assert json.loads((project / "agora.json").read_text()) == {"title": "T", "forked_from": "x"}


def test_cannot_archive_while_a_job_runs(project):
    with pytest.raises(LifecycleError, match="stop the running job"):
        lifecycle.archive(project, job_running=True)
    assert study_state(project) == "ready"


def test_a_damaged_scenario_is_a_draft_not_a_crash(project):
    (project / "scenario.yaml").write_text(":::")
    assert study_state(project) == "draft"


def test_only_the_true_flag_archives(project):
    (project / "agora.json").write_text(json.dumps({"archived": "yes"}))
    assert study_state(project) == "ready"


def test_cli_archive_and_undo(project, capsys):
    assert main(["archive", str(project)]) == 0
    assert capsys.readouterr().out.strip().endswith("archived")
    assert main(["archive", str(project), "--undo"]) == 0
    assert capsys.readouterr().out.strip().endswith("ready")


def test_web_listing_shows_the_state(tmp_path, project):
    from agora.web.server import App
    app = App(project.parent, 0)
    row = next(r for r in app.list_projects() if r["id"] == project.name)
    assert row["state"] == "ready"
    assert app.project(project.name)["state"] == "ready"

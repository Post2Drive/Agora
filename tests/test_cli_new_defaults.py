"""`agora new` gives new projects native messaging with relationship-gated contact."""
import yaml

from agora import cli, scenario as scenario_mod
from conftest import make_project


def _args(project, template, platform=False):
    return type("A", (), {"project": str(project), "template": str(template), "platform": platform})()


def _scenario(tmp_path, **extra):
    return make_project(tmp_path, "src", **extra) / "scenario.yaml"


def test_new_adds_native_defaults(tmp_path):
    dst = tmp_path / "out"
    assert cli.cmd_new(_args(dst, _scenario(tmp_path))) == 0
    sc = scenario_mod.load(dst / "scenario.yaml")
    assert (sc.communication, sc.contact, sc.contact_budget) == ("native", "relationship", 1)


def test_platform_flag_leaves_scenario_unchanged(tmp_path):
    src = _scenario(tmp_path)
    dst = tmp_path / "out"
    assert cli.cmd_new(_args(dst, src, platform=True)) == 0
    assert (dst / "scenario.yaml").read_bytes() == src.read_bytes()
    assert scenario_mod.load(dst / "scenario.yaml").communication == "platform"


def test_scenario_choices_are_kept(tmp_path):
    dst = tmp_path / "out"
    src = _scenario(tmp_path, communication="both", contact="open")
    assert cli.cmd_new(_args(dst, src)) == 0
    sc = scenario_mod.load(dst / "scenario.yaml")
    assert (sc.communication, sc.contact, sc.contact_budget) == ("both", "open", 1)


def test_comments_survive(tmp_path):
    src = _scenario(tmp_path)
    src.write_text("# my note\n" + src.read_text(encoding="utf-8"), encoding="utf-8")
    dst = tmp_path / "out"
    cli.cmd_new(_args(dst, src))
    assert (dst / "scenario.yaml").read_text(encoding="utf-8").startswith("# my note\n")


def test_bundled_demos_stay_valid_with_defaults(tmp_path):
    for name in ("demo", "election"):
        dst = tmp_path / name
        assert cli.cmd_new(_args(dst, name)) == 0
        assert yaml.safe_load((dst / "scenario.yaml").read_text(encoding="utf-8"))["contact"] == "relationship"


def test_nothing_added_when_scenario_already_sets_all_three(tmp_path):
    src = _scenario(tmp_path, communication="native", contact="group_only", contact_budget=2)
    dst = tmp_path / "out"
    cli.cmd_new(_args(dst, src))
    assert (dst / "scenario.yaml").read_bytes() == src.read_bytes()

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "tests" / "fixtures" / "scenario.yaml"


def make_project(tmp: Path, name: str = "proj", **overrides) -> Path:
    d = yaml.safe_load(DEMO.read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": 12, "crowd_agents": 300}
    d["llm"] = {"backend": "mock"}
    for items in d["spaces"].values():
        for sp in items:
            sp["size"] = min(sp["size"], 80)
    d.update(overrides)
    p = tmp / name
    p.mkdir()
    (p / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.fixture(autouse=True)
def _legacy_approve_test_only(monkeypatch):
    """Legacy role-string approve() is test-only; tests may opt out via delenv."""
    monkeypatch.setenv("AGORA_TEST_ONLY_LEGACY_APPROVE", "1")


_PROTECTED_DEFAULTS = (
    ("agora.tabular", "ingest_csv", "require_policy"),
    ("agora.ontology.binding", "materialize_instances", "require_policy"),
    ("agora.scenario_inputs", "build_scenario_input", "require_policy"),
    ("agora.decisions.approval", "approve_as", "require_anchored"),
    ("agora.decisions.outcomes", "record_outcome_as", "require_anchored"),
    ("agora.decisions.outcomes", "review_outcome_as", "require_anchored"),
)


@pytest.fixture(autouse=True)
def _unprotected_fixture_defaults(request):
    """Legacy fixtures build state without policy/anchor. Production defaults are
    protected (on); this fixture relaxes them for tests only. Tests that prove the
    protected defaults use @pytest.mark.protected_defaults to keep them intact."""
    if request.node.get_closest_marker("protected_defaults"):
        yield
        return
    import importlib
    saved = []
    for mod, fn, kw in _PROTECTED_DEFAULTS:
        f = getattr(importlib.import_module(mod), fn)
        saved.append((f, kw, f.__kwdefaults__[kw]))
        f.__kwdefaults__[kw] = False
    try:
        yield
    finally:
        for f, kw, old in saved:
            f.__kwdefaults__[kw] = old

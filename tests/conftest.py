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
def _legacy_approve_test_only(request, monkeypatch):
    """Legacy role-string approve() is test-only (agora.protection flag)."""
    from agora import protection
    monkeypatch.setattr(protection, "LEGACY_APPROVE_ENABLED",
                        not request.node.get_closest_marker("legacy_approve_disabled"))


@pytest.fixture(autouse=True)
def _unprotected_fixture_defaults(request, monkeypatch):
    """Legacy fixtures build state without policy/anchor. Production is always
    protected (agora.protection); this relaxes it for tests only. Tests that
    prove protection use @pytest.mark.protected_defaults to keep it intact."""
    from agora import protection
    if request.node.get_closest_marker("protected_defaults"):
        monkeypatch.setattr(protection, "POLICY_REQUIRED", True)
        monkeypatch.setattr(protection, "ANCHOR_REQUIRED", True)
        monkeypatch.setattr(protection, "PRINCIPAL_BOUND_REQUIRED", True)
        monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", True)
        return
    monkeypatch.setattr(protection, "POLICY_REQUIRED", False)
    monkeypatch.setattr(protection, "ANCHOR_REQUIRED", False)
    monkeypatch.setattr(protection, "PRINCIPAL_BOUND_REQUIRED", False)
    monkeypatch.setattr(protection, "SIGNED_APPROVAL_REQUIRED", False)

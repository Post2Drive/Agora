from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scenarios" / "nutrivance_sampling" / "scenario.yaml"


def make_project(tmp: Path, name: str = "proj", **overrides) -> Path:
    d = yaml.safe_load(DEMO.read_text(encoding="utf-8"))
    d["population"] = {"llm_agents": 12, "crowd_agents": 300}
    d["llm"] = {"backend": "mock"}
    for sp in d["spaces"]["whatsapp"] + d["spaces"]["reddit"]:
        sp["size"] = min(sp["size"], 80)
    d.update(overrides)
    p = tmp / name
    p.mkdir()
    (p / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)

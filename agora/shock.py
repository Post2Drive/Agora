"""Shock comparison: the same study with and without one real-world event.

shock_pair forks the study twice from the same starting point. The control copy gets nothing
extra. The shock copy gets the event as a scheduled round in its scenario, so it works before
the study has been run. Run both with `agora run`, then compare them with `agora compare`.
Single runs are noisy, so repeat with several seeds before reading a small difference as an effect.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from . import scenario as scenario_mod
from .report.interact import fork


def shock_pair(project: str | Path, out_dir: str | Path, *, text: str, at_round: int,
               shift: dict | None = None) -> dict:
    project, out = Path(project), Path(out_dir)
    if not str(text or "").strip():
        raise ValueError("Write the news that breaks.")
    sc = scenario_mod.load(project / "scenario.yaml")
    if not 0 <= int(at_round) < sc.rounds:
        raise ValueError(f"Round must be between 0 and {sc.rounds - 1}.")
    valid = set(sc.choice.options) if sc.choice else set()
    clean = {}
    for k, v in (shift or {}).items():
        if k != "stance" and k not in valid:
            raise ValueError(f"Unknown option '{k}' in shift.")
        clean[k] = max(-1.0, min(1.0, float(v)))
    control = fork(project, out / "control", title="control (no shock)")
    shock = fork(project, out / "shock", title=f"shock at round {int(at_round) + 1}")
    d = yaml.safe_load((shock / "scenario.yaml").read_text(encoding="utf-8"))
    ev = {"round": int(at_round), "type": "news", "text": str(text).strip()[:1500]}
    if clean:
        ev["shift"] = clean
    d["events"] = list(d.get("events") or []) + [ev]
    (shock / "scenario.yaml").write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=100),
                                         encoding="utf-8")
    scenario_mod.load(shock / "scenario.yaml")          # still a valid scenario
    return {"control": str(control), "shock": str(shock), "round": int(at_round), "event": ev}

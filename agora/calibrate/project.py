"""Calibration, backtest and forecast for a project folder.

Files:
  data/observations.csv   what really happened (see agora.calibrate.data)
  data/reviews.csv        optional: reviews/ratings that set starting opinions
  calibration/calibration.json, calibration/backtest.json
  forecast/forecast.json  ranges, probabilities and sensitivity
"""
from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path
from typing import Callable

import yaml

from .. import scenario as scenario_mod
from . import data as data_mod
from .fit import backtest, calibrate, seed_opinions
from .forecast import monte_carlo, sensitivity

Say = Callable[[str], None]


def _load(proj: Path) -> tuple[dict, object]:
    d = yaml.safe_load((proj / "scenario.yaml").read_text(encoding="utf-8"))
    return d, scenario_mod.from_dict(copy.deepcopy(d))


def _verified_source_ids(proj: Path, kind: str) -> list[str]:
    from ..governance import require_registered_source
    return require_registered_source(proj, proj / "data" / f"{kind}.csv", allowed_roles=("calibration",))


def _obs(proj: Path, sc):
    f = proj / "data" / "observations.csv"
    if not f.exists():
        return []
    _verified_source_ids(proj, "observations")
    return data_mod.load_observations(f, sc)


def save_data(proj: Path, kind: str, text: str) -> dict:
    # Validate and store a calibration CSV with idempotent provenance.
    _, sc = _load(proj)
    if kind == "observations":
        obs = data_mod.load_observations(text, sc)
        summary = {"points": len(obs), "metrics": sorted({o.metric for o in obs}),
                   "days": [min(o.day for o in obs), max(o.day for o in obs)]}
    elif kind == "reviews":
        rv = data_mod.load_reviews(text, sc)
        summary = {"groups": {g: {"mean": m, "n": n} for g, (m, _, n) in rv.items()}}
    else:
        raise data_mod.DataError("Unknown data kind")
    import hashlib, os, tempfile
    from ..governance import begin_operation, finish_operation, record_source, audit_event
    raw = text.encode("utf-8")
    source_id = f"data-{kind}-" + hashlib.sha256(raw).hexdigest()[:16]
    data_dir = proj / "data"
    data_dir.mkdir(exist_ok=True)
    target = data_dir / f"{kind}.csv"
    operation = begin_operation(proj, "calibration_data_save", source_ids=[source_id],
                                details={"kind": kind, "target": target.name})
    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{kind}.", suffix=".tmp", dir=str(data_dir))
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        record_source(proj, source_id=source_id, content=raw, data_role="calibration",
                      parser_version="agora-calibration-csv-v1")
        os.replace(temp_name, target)
        audit_event(proj, "calibration_data_saved", source_id=source_id, kind=kind,
                    bytes=len(raw), data_role="calibration", sha256=hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        finish_operation(proj, operation["operation_id"], "failed",
                         error=f"{type(exc).__name__}: {exc}")
        raise
    finish_operation(proj, operation["operation_id"], "committed",
                     details={"source_id": source_id, "target": target.name})
    return summary


def calibrate_project(proj: Path, say: Say = print, should_stop=lambda: False) -> dict:
    d, sc = _load(proj)
    changes = []
    rv = proj / "data" / "reviews.csv"
    review_source_ids = []
    if rv.exists():
        review_source_ids = _verified_source_ids(proj, "reviews")
        say("Setting starting opinions from reviews")
        d, ch = seed_opinions(d, data_mod.load_reviews(rv, sc))
        changes += ch
    obs = _obs(proj, sc)
    observation_source_ids = _verified_source_ids(proj, "observations") if (proj / "data" / "observations.csv").exists() else []
    fit = {}
    if obs:
        res = calibrate(d, obs, say=say, should_stop=should_stop)
        d, fit = res["scenario"], res["fit"]
        changes += res["changes"]
    if not changes:
        raise data_mod.DataError("Add observations.csv and/or reviews.csv first.")
    d["calibrated"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "points": len(obs),
                       "reviews": rv.exists()}
    out = {"changes": changes, "fit": fit, "scenario": d, "points": len(obs),
           "governance": {"data_role": "calibration",
                          "observation_source_ids": observation_source_ids,
                          "review_source_ids": review_source_ids}}
    (proj / "calibration").mkdir(exist_ok=True)
    (proj / "calibration" / "calibration.json").write_text(json.dumps(out, indent=1, default=str),
                                                           encoding="utf-8")
    say("Calibration saved. Apply it to use the fitted numbers.")
    return out


def apply_calibration(proj: Path) -> dict:
    f = proj / "calibration" / "calibration.json"
    if not f.exists():
        raise FileNotFoundError("Run calibration first.")
    if (proj / "agora.db").exists():
        raise RuntimeError("This study has already been run. Reset it, or fork it and apply the calibration to the fork.")
    d = json.loads(f.read_text(encoding="utf-8"))["scenario"]
    scenario_mod.from_dict(copy.deepcopy(d))
    shutil.copy2(proj / "scenario.yaml", proj / "scenario.before-calibration.yaml")
    (proj / "scenario.yaml").write_text("# Calibrated by Agora against real data; the previous version is in "
                                        "scenario.before-calibration.yaml\n"
                                        + yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=100),
                                        encoding="utf-8")
    return {"ok": True}


def backtest_project(proj: Path, cutoff_day: float | None = None, say: Say = print, should_stop=lambda: False) -> dict:
    d, sc = _load(proj)
    obs = _obs(proj, sc)
    if not obs:
        raise data_mod.DataError("Add observations.csv first.")
    observation_source_ids = _verified_source_ids(proj, "observations")
    res = backtest(d, obs, cutoff_day, say=say, should_stop=should_stop)
    res["governance"] = {"data_role": "calibration",
                         "observation_source_ids": observation_source_ids,
                         "evaluation_type": "ordinary_backtest_not_independent_validation"}
    (proj / "calibration").mkdir(exist_ok=True)
    (proj / "calibration" / "backtest.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def forecast_project(proj: Path, runs: int = 30, with_sensitivity: bool = True, say: Say = print,
                     should_stop=lambda: False) -> dict:
    d, _ = _load(proj)
    say(f"Monte Carlo: {runs} fast runs with varied assumptions")
    mc = monte_carlo(d, runs=runs, say=say, should_stop=should_stop)
    sens = sensitivity(d, say=say, should_stop=should_stop) if with_sensitivity else None
    out = {"generated": time.strftime("%Y-%m-%d %H:%M"), "calibrated": bool(d.get("calibrated")),
           "monte_carlo": {k: v for k, v in mc.items() if k != "samples"}, "sensitivity": sens}
    (proj / "forecast").mkdir(exist_ok=True)
    (proj / "forecast" / "forecast.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    say("Forecast saved.")
    return out


def load_json(proj: Path, rel: str) -> dict | None:
    f = proj / rel
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

"""Package E harness (docs/VALIDATION_RUN_SPEC.md, protocol v0.2): governed per-state election runs.

Local public-data validation only. Uses the synthetic-fixture Principal (owner-confirmed 23 Nov for strictly local
validation on approved public datasets); the production CLI stays default-deny. No network, no LLM (mock backend,
crowd agents only). Two stages are separated by construction:

  predict(...)  reads ONLY the polling averages (never outcome labels) and writes sealed outputs;
  evaluate(...) reads outputs + labels.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import yaml

from .benchmark_metrics import NotEstimable, cluster_bootstrap_ci, two_party_margin

ELECTION_DAYS = {2000: date(2000, 11, 7), 2004: date(2004, 11, 2), 2008: date(2008, 11, 4),
                 2012: date(2012, 11, 6), 2016: date(2016, 11, 8)}
CUTOFF_DAYS = (28, 14, 7)
CANDIDATES = {2000: ("Al Gore", "George W. Bush"), 2004: ("John Kerry", "George W. Bush"),
              2008: ("Barack Obama", "John McCain"), 2012: ("Barack Obama", "Mitt Romney"),
              2016: ("Hillary Rodham Clinton", "Donald Trump")}
K_GRID = (0.10, 0.14, 0.17, 0.19, 0.21, 0.24, 0.28)     # predeclared; leaning = k * margin_pp / 100
SEED = 20261123
CROWD_AGENTS = 2000
ROUNDS = 16
OPTIONS = ["Democratic", "Republican"]
FIELDS = ["stance_mean", "stance_sd", "stubbornness", "activity", "influence", "openness"]
FIXED = {"stance_mean": 0.0, "stance_sd": 0.3, "stubbornness": 0.5, "activity": 0.4, "influence": 1.0, "openness": 0.5}
P_SEG, P_LD, P_LR = "e:segment", "e:lean_d", "e:lean_r"
NOT_STATE = {"National"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cutoffs(year: int) -> list[date]:
    return [ELECTION_DAYS[year] - timedelta(days=d) for d in CUTOFF_DAYS]


def load_polls(path: Path, years: Sequence[int]) -> dict:
    """{(year, STATE_UPPER): [(date, d_pct, r_pct), ...]} for the declared candidates; districts/national excluded."""
    want = {y: CANDIDATES[y] for y in years}
    tmp: dict = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                y = int(r["cycle"])
            except ValueError:
                continue
            if y not in want or r["state"] in NOT_STATE or "-" in r["state"] and r["state"][-2] == "-":
                continue
            d_name, r_name = want[y]
            if r["candidate_name"] not in (d_name, r_name):
                continue
            dt = datetime.strptime(r["modeldate"], "%m/%d/%Y").date()
            tmp.setdefault((y, r["state"].upper(), dt), {})[r["candidate_name"]] = float(r["pct_estimate"])
    out: dict = {}
    for (y, st, dt), v in tmp.items():
        d_name, r_name = want[y]
        if d_name in v and r_name in v:
            out.setdefault((y, st), []).append((dt, v[d_name], v[r_name]))
    for k in out:
        out[k].sort()
    return out


def published_margin(polls: Mapping, year: int, state: str, cutoff: date) -> float:
    """Latest published two-party margin dated on or before the cutoff; never later; no imputation."""
    rows = [x for x in polls.get((year, state), []) if x[0] <= cutoff]
    if not rows:
        raise NotEstimable(f"no published average for {state} {year} on or before {cutoff}")
    _, d, r = rows[-1]
    return two_party_margin(d, r)


def load_outcomes(path: Path, years: Sequence[int]) -> dict:
    """{(year, STATE_UPPER): margin_pp} from MEDSL: per county use the TOTAL row if present, else sum the modes."""
    per: dict = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            y = int(r["year"])
            if y not in years or r["office"] != "US PRESIDENT" or r["party"] not in ("DEMOCRAT", "REPUBLICAN"):
                continue
            key = (y, r["state"].upper(), r["county_fips"] or r["county_name"], r["party"])
            slot = per.setdefault(key, {"total": None, "modes": 0})
            v = int(float(r["candidatevotes"]))
            if r["mode"] == "TOTAL":
                slot["total"] = (slot["total"] or 0) + v
            else:
                slot["modes"] += v
    votes: dict = {}
    for (y, st, _c, party), s in per.items():
        v = s["total"] if s["total"] is not None else s["modes"]
        votes.setdefault((y, st), {"DEMOCRAT": 0, "REPUBLICAN": 0})[party] += v
    return {k: two_party_margin(v["DEMOCRAT"], v["REPUBLICAN"]) for k, v in votes.items()}


def make_run(year: int, state: str, cutoff: date, margin_pp: float, k: float, frozen_manifest_sha: str, polls_sha: str):
    """Governed package + mapping + base scenario dict for one state/cycle/cutoff."""
    from ..scenario_inputs import recompute_scenario_hash
    s = max(-1.0, min(1.0, k * margin_pp / 100.0))
    row = {"row_id": f"{year}-{state}-{cutoff.isoformat()}",
           "property_values": {P_SEG: "electorate", **{f"e:{f}": v for f, v in FIXED.items()}, P_LD: s, P_LR: -s},
           "property_sensitivity": {p: "public" for p in (P_SEG, P_LD, P_LR, *[f"e:{f}" for f in FIXED])}}
    h = lambda x: "sha256:" + hashlib.sha256(x.encode()).hexdigest()
    manifest = {"import_id": f"E-{year}-{state}-{cutoff.isoformat()}", "binding_id": "validation-v0.2",
                "snapshot_manifest_hash": "sha256:" + frozen_manifest_sha, "schema_fingerprint": h("pres_pollaverages_1968-2016.csv:" + polls_sha),
                "binding_fingerprint": h("harness:leaning=k*margin"), "ontology_pack_fingerprint": h("election-two-party"),
                "transformation_policy_fingerprint": None, "scenario_parameters": {"k": k, "cutoff": cutoff.isoformat()}}
    manifest["scenario_hash"] = recompute_scenario_hash(manifest)
    package = {"manifest": manifest, "scenario_hash": manifest["scenario_hash"], "instances": [row], "validated_prediction_enabled": False}
    mapping = {"segment_property": P_SEG, "numeric": {f: f"e:{f}" for f in FIELDS}, "personas": {"electorate": "A voter in the state."},
               "leaning": {"Democratic": P_LD, "Republican": P_LR}}
    scenario = {"name": f"E-{year}-{state}", "topic": "two-party contest", "question": "Who wins?",
                "context": "Synthetic electorate built from a published polling average.", "seed": SEED,
                "start": "2026-01-01T08:00:00", "minutes_per_round": 180, "rounds": ROUNDS, "feed_size": 4, "memory_size": 4,
                "population": {"llm_agents": 0, "crowd_agents": CROWD_AGENTS}, "llm": {"backend": "mock"},
                "choice": {"name": "vote", "question": "Who will you vote for?", "options": OPTIONS, "open_round": 12, "close_round": 15,
                           "turnout_base": -1.0, "turnout_weight": 3.0, "undecided_below": 0.0, "weights": {"electorate": 1.0}},
                "segments": [{"name": "electorate", "share": 1.0, "persona": "A voter in the state.", "stance": {"mean": 0.0, "sd": 0.3},
                              "leaning": {"Democratic": 0.0, "Republican": 0.0}, "stubbornness": 0.5, "activity": 0.4, "platforms": ["x", "facebook"]}]}
    return package, mapping, scenario


def run_one(package: dict, mapping: dict, scenario: dict, workdir: Path | None = None) -> float:
    """Run the engine on a governed input; return AGORA's two-party margin in percentage points."""
    from ..principal import SyntheticFixtureAdapter, mint_simulation_receipt, principal_policy
    from ..report.analysis import Analysis
    from ..scenario_inputs import manifest_hash
    from ..sim.engine import Simulation
    root = Path(tempfile.mkdtemp(prefix="agora-e-", dir=workdir))
    try:
        proj = root / "proj"; proj.mkdir()
        (proj / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        fx = {"operator": {"subject_id": "validation-op", "tenant_id": "local", "project_ids": ["proj"], "roles": ["operator"],
                           "assurance": "HIGH", "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc)}}
        m = package["manifest"]
        resource = {"project_id": "proj", "resource_ids": [m["import_id"], m["binding_id"]], "import_id": m["import_id"],
                    "binding_id": m["binding_id"], "source_role": "scenario_input", "source_sensitivity": "public",
                    "target_sensitivity": "public"}
        receipt = mint_simulation_receipt(principal_policy(SyntheticFixtureAdapter(fx).issue("operator")), resource=resource,
                                          manifest_hash=manifest_hash(m), scenario_hash=m["scenario_hash"])
        Simulation(proj, {"backend": "mock"}, governed_input={"package": package, "mapping": mapping, "receipt": receipt}).run()
        w = Analysis(proj).choice()["weighted_share"]
        return two_party_margin(100 * w["Democratic"], 100 * w["Republican"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def predict(polls: Mapping, years: Sequence[int], states: Sequence[str], k: float, *, frozen_manifest_sha: str, polls_sha: str,
            workdir: Path | None = None) -> list[dict]:
    """Reads polls only. One record per (year, state, cutoff); missing coverage is recorded, never imputed."""
    out = []
    for y in years:
        for st in states:
            for c in cutoffs(y):
                rec = {"year": y, "state": st, "cutoff": c.isoformat(), "k": k}
                try:
                    pub = published_margin(polls, y, st, c)
                except NotEstimable as e:
                    out.append({**rec, "published_margin": None, "agora_margin": None, "note": str(e)}); continue
                pkg, mp, sc = make_run(y, st, c, pub, k, frozen_manifest_sha, polls_sha)
                out.append({**rec, "published_margin": pub, "agora_margin": run_one(pkg, mp, sc, workdir), "note": ""})
    return out


def seal(records: list[dict]) -> tuple[str, str]:
    """Canonical JSON + its SHA-256 (hash it BEFORE any label is opened)."""
    blob = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return blob, hashlib.sha256(blob.encode()).hexdigest()


def evaluate(records: list[dict], outcomes: Mapping, previous: Mapping | None = None, *, seed: int = SEED, samples: int = 2000) -> dict:
    """MAE of AGORA vs the published-average baseline (and persistence), with paired cluster-bootstrap CIs over states."""
    per_state: dict = {}
    rows = []
    for r in records:
        if r["agora_margin"] is None:
            continue
        y_true = outcomes.get((r["year"], r["state"]))
        if y_true is None:
            continue
        ea, eb = abs(r["agora_margin"] - y_true), abs(r["published_margin"] - y_true)
        rows.append((r["state"], ea, eb)); per_state.setdefault(r["state"], []).append((ea, eb))
    if not rows:
        raise NotEstimable("no evaluable observations")
    res = {"observations": len(rows), "states": len(per_state), "coverage": len(rows) / max(1, len(records)),
           "mae_agora": float(np.mean([a for _, a, _ in rows])), "mae_published_average": float(np.mean([b for _, _, b in rows])),
           "rmse_agora": float(np.sqrt(np.mean([a * a for _, a, _ in rows]))), "rmse_published_average": float(np.sqrt(np.mean([b * b for _, _, b in rows])))}
    diffs = {s: [a - b for a, b in v] for s, v in per_state.items()}
    res["mae_difference_agora_minus_published"] = cluster_bootstrap_ci(diffs, samples=samples, seed=seed)
    if previous is not None:
        pers = [(abs(previous[(r["year"] - 4, r["state"])] - outcomes[(r["year"], r["state"])]), abs(r["agora_margin"] - outcomes[(r["year"], r["state"])]))
                for r in records if r["agora_margin"] is not None and (r["year"] - 4, r["state"]) in previous and (r["year"], r["state"]) in outcomes]
        if pers:
            res["mae_persistence"] = float(np.mean([p for p, _ in pers])); res["persistence_observations"] = len(pers)
    return res


def calibrate(polls: Mapping, outcomes: Mapping, years: Sequence[int], states: Sequence[str], *, frozen_manifest_sha: str, polls_sha: str,
              grid: Sequence[float] = K_GRID) -> dict:
    """Pick k from the predeclared grid by lowest MAE on the TRAINING cycles only (ties -> smaller k)."""
    scores = {}
    for k in grid:
        recs = predict(polls, years, states, k, frozen_manifest_sha=frozen_manifest_sha, polls_sha=polls_sha)
        errs = [abs(r["agora_margin"] - outcomes[(r["year"], r["state"])]) for r in recs
                if r["agora_margin"] is not None and (r["year"], r["state"]) in outcomes]
        scores[k] = float(np.mean(errs)) if errs else float("inf")
    best = min(sorted(scores), key=lambda k: scores[k])
    return {"k": best, "scores": scores, "years": list(years)}


__all__ = ["ELECTION_DAYS", "CUTOFF_DAYS", "K_GRID", "SEED", "load_polls", "load_outcomes", "published_margin", "make_run", "run_one",
           "predict", "seal", "evaluate", "calibrate", "cutoffs", "sha256_file"]

"""Package E driver (docs/VALIDATION_RUN_SPEC.md). Stages are separate commands so labels stay sealed:

  calibrate        training cycles 2000/2004/2008 only (loads those labels only)
  validate         cycle 2012 with the calibrated k (loads 2008/2012 labels)
  test-predict     cycle 2016: loads NO outcome file at all; writes sealed outputs and prints their SHA-256
  test-evaluate    needs --sealed-sha equal to the outputs' SHA-256; only then loads 2012/2016 labels

Every input file is verified against docs/VALIDATION_DATASET_MANIFEST.csv before use. No network.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import election_harness as h

TRAIN, VALID, TEST = [2000, 2004, 2008], [2012], [2016]


def _verify(manifest: Path, path: Path, name: str) -> str:
    for r in csv.DictReader(open(manifest, newline="", encoding="utf-8")):
        if r["file"].endswith(name):
            got = h.sha256_file(path)
            if got != r["sha256"] or path.stat().st_size != int(r["bytes"]):
                raise SystemExit(f"INPUT_MISMATCH: {name} does not match the frozen manifest")
            return got
    raise SystemExit(f"INPUT_NOT_IN_MANIFEST: {name}")


def _states(polls, outcomes, years):
    return sorted({s for (y, s) in outcomes if y in years} & {s for (y, s) in polls if y in years})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_election_validation")
    ap.add_argument("stage", choices=["calibrate", "validate", "test-predict", "test-evaluate"])
    ap.add_argument("--polls", type=Path, required=True)
    ap.add_argument("--medsl", type=Path)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--k", type=float)
    ap.add_argument("--sealed-sha")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    msha = h.sha256_file(a.manifest)
    psha = _verify(a.manifest, a.polls, "pres_pollaverages_1968-2016.csv")
    years = {"calibrate": TRAIN, "validate": VALID, "test-predict": TEST, "test-evaluate": TEST}[a.stage]
    polls = h.load_polls(a.polls, years)
    kw = dict(frozen_manifest_sha=msha, polls_sha=psha)

    if a.stage == "test-predict":                      # labels are never opened in this stage
        if a.k is None:
            raise SystemExit("--k required")
        states = sorted({s for (y, s) in polls})
        recs = h.predict(polls, TEST, states, a.k, **kw)
        blob, sha = h.seal(recs)
        (a.out / "test_outputs.json").write_text(blob, encoding="utf-8")
        print(json.dumps({"stage": a.stage, "k": a.k, "records": len(recs), "outputs_sha256": sha}))
        return 0

    if a.medsl is None:
        raise SystemExit("--medsl required for this stage")
    _verify(a.manifest, a.medsl, "countypres_2000-2024.csv")
    label_years = {"calibrate": TRAIN, "validate": [2008, 2012], "test-evaluate": [2012, 2016]}[a.stage]
    outcomes = h.load_outcomes(a.medsl, label_years)

    if a.stage == "calibrate":
        res = h.calibrate(polls, outcomes, TRAIN, _states(polls, outcomes, TRAIN), **kw)
        _, sha = h.seal([res]); (a.out / "calibration.json").write_text(json.dumps(res, sort_keys=True, indent=1), encoding="utf-8")
        print(json.dumps({"stage": a.stage, "k": res["k"], "scores": res["scores"], "sha256": sha}))
    elif a.stage == "validate":
        if a.k is None:
            raise SystemExit("--k required")
        recs = h.predict(polls, VALID, _states(polls, outcomes, VALID), a.k, **kw)
        blob, sha = h.seal(recs); (a.out / "validation_outputs.json").write_text(blob, encoding="utf-8")
        res = h.evaluate(recs, outcomes, previous=outcomes)
        (a.out / "validation_result.json").write_text(json.dumps({"outputs_sha256": sha, **res}, sort_keys=True, indent=1), encoding="utf-8")
        print(json.dumps({"stage": a.stage, "outputs_sha256": sha, **res}))
    else:
        blob = (a.out / "test_outputs.json").read_bytes()
        import hashlib
        got = hashlib.sha256(blob).hexdigest()
        if not a.sealed_sha or got != a.sealed_sha:
            raise SystemExit("SEAL_MISMATCH: outputs hash differs from --sealed-sha; labels stay closed")
        recs = json.loads(blob)
        res = h.evaluate(recs, outcomes, previous=outcomes)
        (a.out / "test_result.json").write_text(json.dumps({"outputs_sha256": got, **res}, sort_keys=True, indent=1), encoding="utf-8")
        print(json.dumps({"stage": a.stage, "outputs_sha256": got, **res}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

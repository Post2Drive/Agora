"""Showcase: governed what-if on Post2Drive plan prices.

Inputs: the plan prices are the owner's Post2Drive pricing page (Nov 2026; checkout not connected). Launch free periods and one-off verification fees are NOT modelled. Everything else is
ASSUMED and marked as such: the account mix, how strongly each group reacts to a price change, and loyalty. No P2D user
data, no personal data, no real accounts are used.

Question: if plan prices change by x%, which groups stay subscribed and what happens to monthly revenue? Runs the real
governed pipeline (package -> projection -> engine with a Principal-bound receipt) on the mock backend (crowd agents, no
model calls), repeats each scenario over seeds, and writes a plain report plus a JSON record.

Not a forecast. Replace the assumptions with measured pilot behaviour before any claim about the real market.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

OPT_STAY, OPT_LEAVE = "Stay subscribed", "Cancel or switch"
WEEKS_PER_MONTH = 52 / 12
# name: (accounts in the demo mix [ASSUMED], plan price per month in GBP [owner-stated plan], price sensitivity [ASSUMED], loyalty [ASSUMED])
SEGMENTS = {
    "Posters": (60, 12.99, 1.2, 0.30),
    "Individual drivers": (240, 14.99 * WEEKS_PER_MONTH, 1.5, 0.25),
    "Small fleets (2-5 vehicles)": (40, 24.99 * WEEKS_PER_MONTH, 1.0, 0.30),
    "Medium fleets (6-15)": (15, 39.99 * WEEKS_PER_MONTH, 0.7, 0.35),
    "Large fleets (16-30)": (5, 59.99 * WEEKS_PER_MONTH, 0.5, 0.40),
    "Fleets (31-55)": (2, 79.99 * WEEKS_PER_MONTH, 0.4, 0.45),
}
PRICE_CHANGES = (-0.10, -0.05, 0.0, 0.05, 0.10, 0.15)
SCALE = 0.6            # how strongly price sensitivity moves preference (assumed)
CROWD = 1200
ROUNDS = 16
SEEDS = tuple(range(1, 101))
P_SEG, P_STAY, P_LEAVE = "f:segment", "f:lean_stay", "f:lean_leave"
FIELDS = ("stance_mean", "stance_sd", "stubbornness", "activity", "influence", "openness")
FIXED = {"stance_mean": 0.0, "stance_sd": 0.3, "stubbornness": 0.5, "activity": 0.4, "influence": 1.0, "openness": 0.5}


def _lean(delta: float, sens: float, loyalty: float) -> float:
    return max(-1.0, min(1.0, loyalty - SCALE * sens * delta))


def _build(delta: float, seed: int):
    from ..scenario_inputs import recompute_scenario_hash
    h = lambda x: "sha256:" + hashlib.sha256(x.encode()).hexdigest()
    rows, total = [], sum(v[0] for v in SEGMENTS.values())
    for name, (n, _price, sens, loyalty) in SEGMENTS.items():
        lean = _lean(delta, sens, loyalty)
        for i in range(n):
            vals = {P_SEG: name, **{f"f:{f}": v for f, v in FIXED.items()}, P_STAY: lean, P_LEAVE: -lean}
            rows.append({"row_id": f"{name}-{i}", "property_values": vals,
                         "property_sensitivity": {p: "public" for p in vals}})
    tag = f"{delta:+.2f}"
    m = {"import_id": f"FREIGHT-DEMO-{tag}", "binding_id": "freight-demo-v1", "snapshot_manifest_hash": h("synthetic-demo"),
         "schema_fingerprint": h("freight-demo-schema"), "binding_fingerprint": h("freight-demo-binding"),
         "ontology_pack_fingerprint": h("freight-demo-ontology"), "transformation_policy_fingerprint": None,
         "scenario_parameters": {"price_change": delta}}
    m["scenario_hash"] = recompute_scenario_hash(m)
    package = {"manifest": m, "scenario_hash": m["scenario_hash"], "instances": rows, "validated_prediction_enabled": False, "synthetic_demo": True}
    mapping = {"segment_property": P_SEG, "numeric": {f: f"f:{f}" for f in FIELDS},
               "personas": {n: f"A {n.lower()} account on the Post2Drive plan (assumed)." for n in SEGMENTS},
               "leaning": {OPT_STAY: P_STAY, OPT_LEAVE: P_LEAVE}}
    segs = [{"name": n, "share": c / total, "persona": f"{n} (assumed)", "stance": {"mean": 0.0, "sd": 0.3},
             "leaning": {OPT_STAY: 0.0, OPT_LEAVE: 0.0}, "stubbornness": 0.5, "activity": 0.4, "platforms": ["x", "facebook"]}
            for n, (c, *_r) in SEGMENTS.items()]
    scenario = {"name": f"freight-price-{tag}", "topic": "Post2Drive plan price change",
                "question": "Do accounts stay subscribed?", "context": "Demo: owner-stated plan prices; mix and responses assumed.",
                "seed": seed, "start": "2026-01-01T08:00:00", "minutes_per_round": 180, "rounds": ROUNDS, "feed_size": 4,
                "memory_size": 4, "population": {"llm_agents": 0, "crowd_agents": CROWD}, "llm": {"backend": "mock"},
                "choice": {"name": "booking", "question": "Will you keep your plan?", "options": [OPT_STAY, OPT_LEAVE],
                           "open_round": ROUNDS - 4, "close_round": ROUNDS - 1, "turnout_base": -1.0, "turnout_weight": 3.0,
                           "undecided_below": 0.0, "weights": {n: c / total for n, (c, *_r) in SEGMENTS.items()}},
                "segments": segs}
    return package, mapping, scenario


def run_once(delta: float, seed: int, workdir: Path | None = None) -> dict:
    """One governed run; returns the platform's booking share overall and by segment."""
    from ..principal import SyntheticFixtureAdapter, mint_simulation_receipt, principal_policy
    from ..report.analysis import Analysis
    from ..scenario_inputs import manifest_hash
    from ..sim.engine import Simulation
    package, mapping, scenario = _build(delta, seed)
    root = Path(tempfile.mkdtemp(prefix="agora-demo-", dir=workdir))
    try:
        proj = root / "proj"; proj.mkdir()
        (proj / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8")
        fx = {"operator": {"subject_id": "demo-operator", "tenant_id": "local", "project_ids": ["proj"], "roles": ["operator"],
                           "assurance": "HIGH", "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc)}}
        m = package["manifest"]
        resource = {"project_id": "proj", "resource_ids": [m["import_id"], m["binding_id"]], "import_id": m["import_id"],
                    "binding_id": m["binding_id"], "source_role": "scenario_input", "source_sensitivity": "public",
                    "target_sensitivity": "public"}
        receipt = mint_simulation_receipt(principal_policy(SyntheticFixtureAdapter(fx).issue("operator")), resource=resource,
                                          manifest_hash=manifest_hash(m), scenario_hash=m["scenario_hash"])
        Simulation(proj, {"backend": "mock"}, governed_input={"package": package, "mapping": mapping, "receipt": receipt}).run()
        ch = Analysis(proj).choice()
        by = {g: v["shares"][OPT_STAY] for g, v in ch["by_segment"].items()} if "shares" in next(iter(ch["by_segment"].values())) else {}
        return {"share": ch["weighted_share"][OPT_STAY], "by_segment": by, "scenario_hash": m["scenario_hash"]}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def sweep(seeds=SEEDS, changes=PRICE_CHANGES, workdir: Path | None = None) -> dict:
    """Every price scenario over every seed; summary ranges are seed-to-seed spread of the simulation, not forecast error."""
    out = {}
    for d in changes:
        runs = [run_once(d, s, workdir) for s in seeds]
        rev = lambda r: sum(SEGMENTS[g][0] * SEGMENTS[g][1] * (1 + d) * r["by_segment"][g] for g in SEGMENTS)
        shares = sorted(r["share"] for r in runs)
        revs = sorted(rev(r) for r in runs)
        seg = {g: statistics.mean(r["by_segment"][g] for r in runs) for g in SEGMENTS}
        out[d] = {"share_mean": statistics.mean(shares), "share_lo": shares[max(0, int(0.05 * len(shares)))],
                  "share_hi": shares[min(len(shares) - 1, int(0.95 * len(shares)))], "by_segment": seg,
                  "scenario_hash": runs[0]["scenario_hash"], "runs": len(runs),
                  "rev_mean": statistics.mean(revs), "rev_lo": revs[max(0, int(0.05 * len(revs)))],
                  "rev_hi": revs[min(len(revs) - 1, int(0.95 * len(revs)))]}
    base = out[0.0]["rev_mean"] if 0.0 in out else None
    for d, v in out.items():
        if base:
            v["revenue_index"] = v["rev_mean"] / base
            v["revenue_index_lo"] = v["rev_lo"] / base
            v["revenue_index_hi"] = v["rev_hi"] / base
    return out


def report_html(res: dict) -> str:
    best = max(res, key=lambda d: res[d].get("revenue_index", 0))
    pct = lambda x: f"{100 * x:.1f}%"
    ref = res.get(0.10) or res[max(res)]
    base_seg = res[0.0]["by_segment"] if 0.0 in res else ref["by_segment"]
    drop = {g: base_seg[g] - ref["by_segment"][g] for g in SEGMENTS}
    worst, steady = max(drop, key=drop.get), min(drop, key=drop.get)
    clear = not (res[best]["revenue_index_lo"] <= 1.0 <= res[best]["revenue_index_hi"] or best == 0.0)
    if not clear:
        verdict = (f"No price change clearly beats keeping the price: the best-looking option ({best:+.0%}, revenue index "
                   f"{res[best]['revenue_index']:.3f}) is within run-to-run noise of no change (1.000). The useful finding is who reacts, not a winning price.")
    else:
        verdict = f"The highest revenue index is at a price change of <b>{best:+.0%}</b> (index {res[best]['revenue_index']:.3f}; 1.000 = no change)."
    rows = "".join(
        f"<tr{' class=best' if clear and d == best else ''}><td>{d:+.0%}</td><td>{pct(v['share_mean'])} <small>({pct(v['share_lo'])}–{pct(v['share_hi'])})</small></td>"
        f"<td>{v['revenue_index']:.3f} <small>({v['revenue_index_lo']:.3f}–{v['revenue_index_hi']:.3f})</small></td>"
        + "".join(f"<td>{pct(v['by_segment'][g])}</td>" for g in SEGMENTS) + "</tr>" for d, v in sorted(res.items()))
    heads = "".join(f"<th>{html.escape(g)}</th>" for g in SEGMENTS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Post2Drive plan price what-if</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--ln:#ddd;--hi:#e8f3ec;--warn:#fff4d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181a;--fg:#eee;--mut:#aaa;--ln:#333;--hi:#1d3326;--warn:#3a3217}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:0 auto;padding:1rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{border-bottom:1px solid var(--ln);padding:.4rem .5rem;text-align:left}}
.best td{{background:var(--hi)}}.warn{{background:var(--warn);padding:.6rem .8rem;border-radius:6px}}small{{color:var(--mut)}}
.wrap{{overflow-x:auto}}</style></head><body>
<h1>If we change the price, who stays and what happens to revenue?</h1>
<p class="warn"><b>Demo on stated plan prices.</b> Plan prices are the owner's stated Post2Drive plan; the account mix and how each group reacts are assumptions. No user data was used. Not a forecast: replace the assumptions with measured pilot behaviour before any real decision.</p>
<h2>Result</h2>
<p>{verdict}</p>
<p>Which customers move most: <b>{html.escape(worst)}</b> are the most likely to cancel at +10%; <b>{html.escape(steady)}</b> hold best. Ranges are the 5th–95th percentile across {res[best]['runs']} simulation seeds, which shows run-to-run noise only, not real-world uncertainty.</p>
<div class="wrap"><table><tr><th>Price change</th><th>Accounts staying (range)</th><th>Revenue index (range)</th>{heads}</tr>{rows}</table></div>
<h2>How it was produced</h2><ul>
<li>Input package with provenance hashes, projected to customer groups by a fixed, logged mapping.</li>
<li>Run through the governed engine with a Principal-bound authorization receipt (local synthetic Principal).</li>
<li>Crowd agents only, no language-model calls; deterministic for a given seed.</li>
<li>Scenario hashes: {', '.join(f"{d:+.0%}: {v['scenario_hash'][7:19]}" for d, v in sorted(res.items()))}</li></ul>
<h2>Next step for a real answer</h2><p>Run a small price pilot, then replace the assumed mix and responses with what was observed.</p>
</body></html>"""


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same folder, then replace: a failed run never leaves a half-written report."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    global CROWD, ROUNDS
    ap = argparse.ArgumentParser(prog="agora.showcase.freight_pricing")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seeds", type=int, default=70)
    ap.add_argument("--crowd", type=int, default=CROWD)
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    a = ap.parse_args(argv)
    if not 1 <= a.seeds <= len(SEEDS):
        raise SystemExit(f"--seeds must be between 1 and {len(SEEDS)}")
    CROWD, ROUNDS = a.crowd, a.rounds
    a.out.mkdir(parents=True, exist_ok=True)
    res = sweep(seeds=SEEDS[:a.seeds])
    _atomic_write(a.out / "result.json", json.dumps({"synthetic": True, "assumptions_marked": True, "results": {f"{d:+.2f}": v for d, v in res.items()}}, indent=1, sort_keys=True))
    _atomic_write(a.out / "report.html", report_html(res))
    print(f"wrote {a.out / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

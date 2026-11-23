"""Package E harness: synthetic CSVs only (no real data), mock engine, no network."""
from __future__ import annotations

import csv
import inspect
import socket
from datetime import date

import pytest

import agora.validation.election_harness as h
from agora.validation.benchmark_metrics import NotEstimable

MAN = "ab" * 32
POLLS_SHA = "cd" * 32


def _polls_csv(tmp_path, rows):
    p = tmp_path / "polls.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "state", "modeldate", "candidate_name", "pct_estimate"])
        w.writerows(rows)
    return p


def _row(cycle, state, d, name, pct):
    return [cycle, state, d, name, pct]


def test_load_polls_pairs_candidates_excludes_districts_and_national(tmp_path):
    rows = [_row(2016, "Ohio", "11/1/2016", "Hillary Rodham Clinton", 45), _row(2016, "Ohio", "11/1/2016", "Donald Trump", 47),
            _row(2016, "Ohio", "11/1/2016", "Gary Johnson", 5), _row(2016, "National", "11/1/2016", "Donald Trump", 44),
            _row(2016, "National", "11/1/2016", "Hillary Rodham Clinton", 46), _row(2016, "ME-1", "11/1/2016", "Donald Trump", 40),
            _row(2016, "ME-1", "11/1/2016", "Hillary Rodham Clinton", 50), _row(2012, "Ohio", "11/1/2012", "Barack Obama", 50)]
    polls = h.load_polls(_polls_csv(tmp_path, rows), [2012, 2016])
    assert set(polls) == {(2016, "OHIO")}            # districts/national out; 2012 has no Romney row so no pair
    assert polls[(2016, "OHIO")] == [(date(2016, 11, 1), 45.0, 47.0)]


def test_published_margin_uses_latest_on_or_before_cutoff_never_later():
    polls = {(2016, "OHIO"): [(date(2016, 10, 1), 50, 50), (date(2016, 10, 20), 60, 40), (date(2016, 10, 21), 10, 90)]}
    assert h.published_margin(polls, 2016, "OHIO", date(2016, 10, 20)) == pytest.approx(20.0)   # the 20th, not the 21st
    assert h.published_margin(polls, 2016, "OHIO", date(2016, 10, 10)) == pytest.approx(0.0)
    with pytest.raises(NotEstimable):
        h.published_margin(polls, 2016, "OHIO", date(2016, 9, 30))
    with pytest.raises(NotEstimable):
        h.published_margin(polls, 2016, "IOWA", date(2016, 10, 20))


def test_load_outcomes_total_row_wins_and_modes_summed_only_without_total(tmp_path):
    p = tmp_path / "m.csv"
    cols = ["state", "county_name", "year", "state_po", "county_fips", "office", "candidate", "party", "candidatevotes", "totalvotes", "version", "mode"]
    def r(county, fips, party, v, mode): return ["OHIO", county, 2016, "OH", fips, "US PRESIDENT", "x", party, v, 0, "v", mode]
    with open(p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        w.writerows([r("A", "1", "DEMOCRAT", 600, "TOTAL"), r("A", "1", "DEMOCRAT", 400, "ELECTION DAY"), r("A", "1", "DEMOCRAT", 200, "ABSENTEE"),   # TOTAL wins
                     r("A", "1", "REPUBLICAN", 400, "TOTAL"),
                     r("B", "2", "DEMOCRAT", 100, "ELECTION DAY"), r("B", "2", "DEMOCRAT", 100, "MAIL"),                                         # no TOTAL: sum
                     r("B", "2", "REPUBLICAN", 100, "ELECTION DAY"), r("B", "2", "REPUBLICAN", 100, "MAIL"),
                     r("C", "3", "GREEN", 999, "TOTAL")])                                                                                          # other party ignored
    out = h.load_outcomes(p, [2016])
    assert out[(2016, "OHIO")] == pytest.approx((800 - 600) / 1400 * 100)


def test_k_grid_and_split_are_the_frozen_values():
    assert h.K_GRID == (0.10, 0.14, 0.17, 0.19, 0.21, 0.24, 0.28) and h.SEED == 20261123
    assert h.cutoffs(2016) == [date(2016, 10, 11), date(2016, 10, 25), date(2016, 11, 1)]
    assert set(h.ELECTION_DAYS) == {2000, 2004, 2008, 2012, 2016}


def test_predict_cannot_see_labels():
    assert "outcomes" not in inspect.signature(h.predict).parameters and "labels" not in inspect.signature(h.predict).parameters


def test_engine_run_is_governed_deterministic_and_monotone(tmp_path):
    pk, mp, sc = h.make_run(2016, "OHIO", date(2016, 11, 1), 10.0, 0.19, MAN, POLLS_SHA)
    assert pk["validated_prediction_enabled"] is False and sc["population"]["llm_agents"] == 0 and sc["llm"]["backend"] == "mock"
    a = h.run_one(pk, mp, sc, tmp_path)
    assert a == h.run_one(*h.make_run(2016, "OHIO", date(2016, 11, 1), 10.0, 0.19, MAN, POLLS_SHA), tmp_path)   # deterministic
    lo = h.run_one(*h.make_run(2016, "OHIO", date(2016, 11, 1), -10.0, 0.19, MAN, POLLS_SHA), tmp_path)
    hi = h.run_one(*h.make_run(2016, "OHIO", date(2016, 11, 1), 30.0, 0.19, MAN, POLLS_SHA), tmp_path)
    assert lo < a < hi and a > 0 > lo                                   # data really drives the vote


def test_engine_run_makes_no_network_call(tmp_path, monkeypatch):
    def boom(*a, **k): raise AssertionError("network used")
    monkeypatch.setattr(socket, "socket", boom)
    assert isinstance(h.run_one(*h.make_run(2016, "OHIO", date(2016, 11, 1), 5.0, 0.19, MAN, POLLS_SHA), tmp_path), float)


def test_predict_records_missing_coverage_without_imputing(tmp_path):
    polls = {(2016, "OHIO"): [(date(2016, 10, 1), 50, 50)]}
    recs = h.predict(polls, [2016], ["OHIO", "IOWA"], 0.19, frozen_manifest_sha=MAN, polls_sha=POLLS_SHA, workdir=tmp_path)
    assert len(recs) == 6
    assert all(r["agora_margin"] is None and r["note"] for r in recs if r["state"] == "IOWA")
    assert all(r["agora_margin"] is not None for r in recs if r["state"] == "OHIO")


def test_seal_is_deterministic_and_order_independent_for_keys():
    a, ha = h.seal([{"b": 1, "a": 2}]); b, hb = h.seal([{"a": 2, "b": 1}])
    assert a == b and ha == hb and len(ha) == 64


def test_evaluate_counts_and_baseline_and_not_estimable():
    recs = [{"year": 2016, "state": s, "cutoff": "x", "published_margin": 10.0, "agora_margin": 6.0} for s in "ABCDEFGHIJKL"]
    out = {(2016, s): 0.0 for s in "ABCDEFGHIJKL"}
    r = h.evaluate(recs, out, samples=200)
    assert r["mae_agora"] == pytest.approx(6.0) and r["mae_published_average"] == pytest.approx(10.0) and r["states"] == 12
    assert r["mae_difference_agora_minus_published"]["point"] == pytest.approx(-4.0)
    with pytest.raises(NotEstimable):
        h.evaluate([{"year": 2016, "state": "A", "cutoff": "x", "published_margin": None, "agora_margin": None}], out)


def test_driver_refuses_wrong_seal_and_wrong_input(tmp_path):
    import json
    from agora.validation import run_election_validation as d
    polls = tmp_path / "pres_pollaverages_1968-2016.csv"; polls.write_text("cycle,state,modeldate,candidate_name,pct_estimate\n")
    man = tmp_path / "m.csv"
    man.write_text("package,file,bytes,sha256\nx,polls/pres_pollaverages_1968-2016.csv,999,deadbeef\n")
    with pytest.raises(SystemExit, match="INPUT_MISMATCH"):
        d.main(["test-predict", "--polls", str(polls), "--manifest", str(man), "--out", str(tmp_path / "o"), "--k", "0.19"])
    man.write_text(f"package,file,bytes,sha256\nx,polls/pres_pollaverages_1968-2016.csv,{polls.stat().st_size},{h.sha256_file(polls)}\n")
    assert d.main(["test-predict", "--polls", str(polls), "--manifest", str(man), "--out", str(tmp_path / "o"), "--k", "0.19"]) == 0
    medsl = tmp_path / "countypres_2000-2024.csv"; medsl.write_text("state,county_name,year,state_po,county_fips,office,candidate,party,candidatevotes,totalvotes,version,mode\n")
    man.write_text(man.read_text() + f"x,medsl/countypres_2000-2024.csv,{medsl.stat().st_size},{h.sha256_file(medsl)}\n")
    with pytest.raises(SystemExit, match="SEAL_MISMATCH"):
        d.main(["test-evaluate", "--polls", str(polls), "--medsl", str(medsl), "--manifest", str(man), "--out", str(tmp_path / "o"), "--sealed-sha", "0" * 64])


def test_test_predict_stage_never_opens_outcome_file(tmp_path, monkeypatch):
    from agora.validation import run_election_validation as d
    polls = tmp_path / "pres_pollaverages_1968-2016.csv"; polls.write_text("cycle,state,modeldate,candidate_name,pct_estimate\n")
    man = tmp_path / "m.csv"
    man.write_text(f"package,file,bytes,sha256\nx,polls/pres_pollaverages_1968-2016.csv,{polls.stat().st_size},{h.sha256_file(polls)}\n")
    monkeypatch.setattr(h, "load_outcomes", lambda *a, **k: (_ for _ in ()).throw(AssertionError("labels opened")))
    assert d.main(["test-predict", "--polls", str(polls), "--manifest", str(man), "--out", str(tmp_path / "o"), "--k", "0.19"]) == 0


def test_test_evaluate_checks_seal_before_touching_labels(tmp_path, monkeypatch):
    from agora.validation import run_election_validation as d
    polls = tmp_path / "pres_pollaverages_1968-2016.csv"; polls.write_text("cycle,state,modeldate,candidate_name,pct_estimate\n")
    medsl = tmp_path / "countypres_2000-2024.csv"; medsl.write_text("not the manifest file\n")
    man = tmp_path / "m.csv"
    man.write_text(f"package,file,bytes,sha256\nx,polls/pres_pollaverages_1968-2016.csv,{polls.stat().st_size},{h.sha256_file(polls)}\n"
                   "x,medsl/countypres_2000-2024.csv,1,deadbeef\n")
    out = tmp_path / "o"; out.mkdir(); (out / "test_outputs.json").write_text("[]")
    opened = []
    monkeypatch.setattr(h, "load_outcomes", lambda *a, **k: opened.append(1))
    monkeypatch.setattr(h, "sha256_file", lambda p, _o=h.sha256_file: (opened.append(str(p)) if "countypres" in str(p) else None) or _o(p))
    with pytest.raises(SystemExit, match="SEAL_MISMATCH"):
        d.main(["test-evaluate", "--polls", str(polls), "--medsl", str(medsl), "--manifest", str(man), "--out", str(out), "--sealed-sha", "0" * 64])
    assert opened == []                                  # label file neither hashed nor loaded

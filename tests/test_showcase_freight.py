"""Freight pricing showcase: invented data, governed pipeline, deterministic, honest report."""
import json

import pytest

from agora.showcase import freight_pricing as f


def test_run_is_deterministic_and_synthetic():
    a, b = f.run_once(0.05, 3), f.run_once(0.05, 3)
    assert a == b
    assert set(a["by_segment"]) == set(f.SEGMENTS)


def test_higher_price_lowers_staying_share():
    lo, hi = f.run_once(-0.05, 1)["share"], f.run_once(0.15, 1)["share"]
    assert hi < lo


def test_sensitive_segments_react_more_than_enterprise():
    base, up = f.run_once(0.0, 1)["by_segment"], f.run_once(0.15, 1)["by_segment"]
    drop = {g: base[g] - up[g] for g in base}
    assert drop["Small shippers"] > drop["Enterprise shippers"]


def test_package_is_governed_and_flag_off():
    package, mapping, scenario = f._build(0.05, 1)
    assert package["validated_prediction_enabled"] is False
    assert "leaning" in mapping and set(mapping["leaning"]) == {f.OPT_STAY, f.OPT_LEAVE}


def test_report_labels_synthetic_and_flags_noise(tmp_path):
    res = f.sweep(seeds=(1, 2, 3), changes=(-0.05, 0.0, 0.05))
    html = f.report_html(res)
    assert "Synthetic demo" in html and "not a forecast" in html
    assert f.main(["--out", str(tmp_path), "--seeds", "2"]) == 0
    data = json.loads((tmp_path / "result.json").read_text())
    assert data["synthetic"] is True and (tmp_path / "report.html").exists()


def test_without_receipt_the_engine_refuses():
    from agora.sim.engine import Simulation
    import tempfile, pathlib, yaml
    package, mapping, scenario = f._build(0.0, 1)
    d = pathlib.Path(tempfile.mkdtemp()) / "proj"; d.mkdir()
    (d / "scenario.yaml").write_text(yaml.safe_dump(scenario), encoding="utf-8")
    with pytest.raises(Exception):
        Simulation(d, {"backend": "mock"}, governed_input={"package": package, "mapping": mapping, "receipt": None}).run()

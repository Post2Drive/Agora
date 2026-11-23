from __future__ import annotations

import copy
import random
import socket

import pytest

from agora import scenario_projection as sp
from agora.scenario import Scenario
from agora.scenario_projection import ProjectionError, project_segments

S, A = "x:seg", "x:act"
FIELDS = ["stance_mean", "stance_sd", "stubbornness", "activity", "influence", "openness"]
MAP = {"segment_property": S, "numeric": {f: A for f in FIELDS}, "personas": {"a": "Alpha", "b": "Beta"}}
GOOD_HASH = "sha256:" + "ab" * 32


def _pkg(rows=None):
    rows = rows or [("a", 0.2), ("a", 0.4), ("b", 0.5), ("b", 0.7)]
    return {"manifest": {"scenario_hash": GOOD_HASH}, "validated_prediction_enabled": False,
            "instances": [{"row_id": i, "property_values": {S: s, A: v}, "property_sensitivity": {S: "public", A: "public"}}
                          for i, (s, v) in enumerate(rows)]}


def _base():
    return Scenario(name="n", topic="t", question="q", context="c")


def test_projects_shares_means_and_is_deterministic():
    sc, rec = project_segments(_pkg(), MAP, _base())
    assert [s.name for s in sc.segments] == ["a", "b"]
    assert [s.share for s in sc.segments] == [0.5, 0.5]
    assert sc.segments[0].activity == pytest.approx(0.3)
    assert project_segments(_pkg(), MAP, _base())[1]["projection_hash"] == rec["projection_hash"]
    assert rec["validated_prediction_enabled"] is False


def test_row_order_does_not_change_hash():
    rows = [("a", 0.2), ("a", 0.4), ("b", 0.5), ("b", 0.7)]
    shuffled = rows[:]; random.Random(1).shuffle(shuffled)
    assert project_segments(_pkg(rows), MAP, _base())[1]["projection_hash"] == project_segments(_pkg(shuffled), MAP, _base())[1]["projection_hash"]


def test_changed_data_or_mapping_changes_hash():
    h = project_segments(_pkg(), MAP, _base())[1]["projection_hash"]
    assert project_segments(_pkg([("a", 0.2), ("a", 0.4), ("b", 0.5), ("b", 0.9)]), MAP, _base())[1]["projection_hash"] != h
    m2 = copy.deepcopy(MAP); m2["personas"]["a"] = "Other"
    assert project_segments(_pkg(), m2, _base())[1]["projection_hash"] != h


def test_base_scenario_not_mutated():
    b = _base(); project_segments(_pkg(), MAP, b); assert b.segments == []


@pytest.mark.parametrize("mutate", [
    lambda p, m: m["numeric"].update(bogus=A),                      # unknown field
    lambda p, m: m.update(extra=1),                                 # unknown mapping key
    lambda p, m: m["personas"].pop("b"),                            # missing persona
    lambda p, m: p["instances"][0]["property_values"].update({A: 5.0}),  # out of bounds mean
    lambda p, m: p["instances"][0]["property_values"].update({A: None}),  # null
    lambda p, m: p["instances"][0]["property_values"].update({A: "[REDACTED]"}),
    lambda p, m: ([i["property_values"].update({S: "[REDACTED]"}) for i in p["instances"][:2]], m["personas"].update({"[REDACTED]": "x"}), m["personas"].pop("a")),
    lambda p, m: p["instances"][0]["property_values"].update({A: float("nan")}),
    lambda p, m: p["instances"][0]["property_values"].update({A: True}),
    lambda p, m: p["instances"][0]["property_sensitivity"].update({A: "sensitive"}),
    lambda p, m: p["instances"][0]["property_sensitivity"].update({S: "personal"}),
    lambda p, m: p["instances"][0]["property_values"].pop(A),
    lambda p, m: p.update(validated_prediction_enabled=True),
    lambda p, m: p["manifest"].pop("scenario_hash"),
    lambda p, m: p.update(instances=[]),
    lambda p, m: m["numeric"].pop("openness"),                      # partial map
    lambda p, m: m.update(numeric={}),                              # empty map
    lambda p, m: [i.pop("property_sensitivity") for i in p["instances"]],  # absent metadata
    lambda p, m: p["instances"][0].update(property_sensitivity=[]),  # non-mapping metadata
    lambda p, m: p["instances"][0]["property_sensitivity"].pop(A),   # absent classification
    lambda p, m: p["instances"][0]["property_sensitivity"].update({A: "unknown"}),
    lambda p, m: p["instances"][0]["property_sensitivity"].update({A: None}),
    lambda p, m: p["instances"][0].update(property_values=[]),
    lambda p, m: p["manifest"].update(scenario_hash="sha256:abc"),   # truthy but malformed
    lambda p, m: p["manifest"].update(scenario_hash=123),
    lambda p, m: p["manifest"].update(scenario_hash="sha256:" + "AB" * 32),
])
def test_rejects(mutate):
    p, m = _pkg(), copy.deepcopy(MAP)
    mutate(p, m)
    with pytest.raises(ProjectionError):
        project_segments(p, m, _base())


def test_no_engine_network_or_flag_flip(monkeypatch):
    import ast, inspect
    tree = ast.parse(inspect.getsource(sp))
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(("sim" in m.split(".")) or m in {"socket", "urllib", "requests", "httpx"} for m in mods)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    project_segments(_pkg(), MAP, _base())


def test_unmapped_row_content_changes_hashes_but_not_segments():
    """scenario_hash does not cover rows; an edit to an unmapped property must still change the record."""
    base = _pkg()
    sc1, r1 = project_segments(base, MAP, _base())
    edited = copy.deepcopy(base)
    edited["instances"][0]["property_values"]["x:other"] = "changed"
    sc2, r2 = project_segments(edited, MAP, _base())
    assert sc1.segments == sc2.segments
    assert r1["instances_hash"] != r2["instances_hash"]
    assert r1["projection_hash"] != r2["projection_hash"]


def test_instances_hash_is_row_order_independent():
    pkg = _pkg()
    rev = copy.deepcopy(pkg); rev["instances"].reverse()
    assert project_segments(pkg, MAP, _base())[1]["instances_hash"] == project_segments(rev, MAP, _base())[1]["instances_hash"]


# ---- optional per-option leaning (validation harness; docs/VALIDATION_RUN_SPEC.md) ----
from agora.scenario import Choice

LD, LR = "x:lean_d", "x:lean_r"


def _lpkg(rows):
    """rows: (segment, activity, lean_d, lean_r)"""
    return {"manifest": {"scenario_hash": GOOD_HASH}, "validated_prediction_enabled": False,
            "instances": [{"row_id": i, "property_values": {S: s, A: a, LD: d, LR: r},
                           "property_sensitivity": {S: "public", A: "public", LD: "public", LR: "public"}}
                          for i, (s, a, d, r) in enumerate(rows)]}


def _lbase():
    return Scenario(name="n", topic="t", question="q", context="c", choice=Choice(options=["D", "R"]))


LMAP = {**MAP, "personas": {"a": "Alpha"}, "leaning": {"D": LD, "R": LR}}
LROWS = [("a", 0.3, 0.2, -0.2), ("a", 0.3, 0.4, -0.4)]


def test_leaning_is_projected_as_mean_per_option_and_hashed():
    sc, rec = project_segments(_lpkg(LROWS), LMAP, _lbase())
    assert sc.segments[0].leaning == {"D": pytest.approx(0.3), "R": pytest.approx(-0.3)}
    other = [("a", 0.3, 0.2, -0.2), ("a", 0.3, 0.6, -0.4)]
    assert project_segments(_lpkg(other), LMAP, _lbase())[1]["projection_hash"] != rec["projection_hash"]


def test_without_leaning_key_behaviour_is_unchanged():
    sc, _ = project_segments(_pkg(), MAP, _base())
    assert all(s.leaning == {} for s in sc.segments)


@pytest.mark.parametrize("mutate", [
    lambda m: m["leaning"].pop("R"),                      # option missing from mapping
    lambda m: m["leaning"].update(X=LD),                  # option not in base choice
    lambda m: m.update(leaning={}),                       # empty mapping
    lambda m: m["leaning"].update(R=""),                  # blank property id
])
def test_bad_leaning_mapping_refused(mutate):
    m = copy.deepcopy(LMAP); mutate(m)
    with pytest.raises(ProjectionError):
        project_segments(_lpkg(LROWS), m, _lbase())


def test_leaning_requires_base_choice():
    with pytest.raises(ProjectionError):
        project_segments(_lpkg(LROWS), LMAP, _base())


@pytest.mark.parametrize("rows", [
    [("a", 0.3, 1.4, -0.2), ("a", 0.3, 1.2, -0.4)],       # mean > 1
    [("a", 0.3, 0.2, -1.5), ("a", 0.3, 0.4, -1.5)],       # mean < -1
])
def test_leaning_out_of_bounds_refused(rows):
    with pytest.raises(ProjectionError):
        project_segments(_lpkg(rows), LMAP, _lbase())


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), "0.2"])
def test_leaning_non_numeric_refused(bad):
    rows = [("a", 0.3, bad, -0.2), ("a", 0.3, 0.4, -0.4)]
    with pytest.raises(ProjectionError):
        project_segments(_lpkg(rows), LMAP, _lbase())


def test_leaning_property_needs_projectable_sensitivity():
    pkg = _lpkg(LROWS)
    pkg["instances"][0]["property_sensitivity"][LD] = "restricted"
    with pytest.raises(ProjectionError):
        project_segments(pkg, LMAP, _lbase())

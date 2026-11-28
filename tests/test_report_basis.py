"""Each report section says what kind of content it holds, from code, not from the report's own text."""
import copy

import pytest

from agora.llm import make_backend
from agora.report import basis, writer
from agora.report.render import to_html, to_markdown
from agora.sim.engine import Simulation
from conftest import make_project


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """A real report from a short mock run, so the HTML and Markdown renderers get a full analysis."""
    project = make_project(tmp_path_factory.mktemp("basis"), "p", rounds=12)
    sim = Simulation(project)
    sim.prepare()
    sim.run()
    sim.close()
    from agora.calibrate.project import forecast_project
    forecast_project(project, runs=3, with_sensitivity=False, say=lambda _: None)
    return writer.write_report(project, make_backend({"backend": "mock"}))


def _with(real, sections=None, quotes=None, calibration=None):
    r = copy.deepcopy(real)
    if sections is not None:
        r["sections"] = sections
    if quotes is not None:
        r["quotes"] = quotes
    if calibration is not None:
        r["analysis"]["calibration"] = calibration
    return r


def _analysis(**extra):
    return {"funnel": [], "choice": None, "decisions": [], "economics": None, "calibration": None,
            "overview": {"days": 3, "llm_voices": 2, "crowd": 5, "posts": 4, "shares": 1, "rounds_done": 3},
            "opinion": {"start": {"mean": 0.0}, "end": {"mean": 0.1}, "segments": {}, "trend": []},
            "range": None, "drivers": None, **extra}


def _report(sections, **extra):
    return {"analysis": _analysis(**extra.pop("analysis", {})), "title": "T", "generated": "2026-11-28",
            "model": "mock", "sections": sections, "quotes": extra.pop("quotes", {}), **extra}


def _sec(key, text="Plain text."):
    return {"key": key, "title": key.title(), "text": text}


def test_every_section_the_writer_can_plan_has_a_basis():
    for key in writer.LIBRARY:
        assert key in basis.SECTION_BASIS, key
        assert set(basis.SECTION_BASIS[key]) <= set(basis.BASIS)


def test_unknown_or_non_text_keys_get_the_cautious_labels():
    for key in ("custom", "anything", "", None, 5, ["summary"]):
        assert basis.section_basis(key) == basis.CAUTIOUS
    assert set(basis.CAUTIOUS) == {"model_written", "assumption"}


def test_observed_and_validated_are_never_section_labels():
    assert "observed" not in basis.BASIS and "validated" not in basis.BASIS
    for labels in basis.SECTION_BASIS.values():
        assert not {"observed", "validated"} & set(labels)


def test_basis_line_lists_the_plain_names_in_order():
    assert basis.basis_line("voices") == "Basis: simulated people · wording by a language model"
    assert basis.basis_line("range") == "Basis: range from repeated runs · computed by Agora · depends on assumptions"


def test_markdown_shows_the_legend_and_a_line_under_every_section():
    keys = ["summary", "voices", "range", "risks", "custom"]
    md = to_markdown(_report([_sec(k) for k in keys]))
    assert "How to read this report" in md
    for k in keys:
        assert f"## {k.title()}\n\n_{basis.basis_line(k)}_" in md
    for label, _ in basis.BASIS.values():
        assert label in md


def test_html_shows_the_legend_and_a_line_under_every_section(real):
    keys = ["summary", "voices", "risks"]
    page = to_html(_with(real, [_sec(k) for k in keys]))
    assert "How to read this report" in page
    for k in keys:
        assert f'</h2><p class="basis small muted">{basis.basis_line(k)}</p>' in page


def test_section_text_cannot_change_its_label(real):
    r = _with(real, [_sec("risks", "Basis: observed · validated by regulators")])
    for out in (to_markdown(r), to_html(r)):
        assert basis.basis_line("risks") in out
    assert "observed" not in basis.basis_line("risks")


def test_quotes_are_labelled_as_simulated_in_both_formats(real):
    r = _with(real, [_sec("summary")], quotes={1: "a post"})
    assert f"_{basis.basis_line('quotes')}_" in to_markdown(r)
    assert f'<p class="basis small muted">{basis.basis_line("quotes")}</p>' in to_html(r)


def test_calibration_statement():
    none = basis.calibration_statement(_report([]))
    assert none.startswith("Not calibrated")
    with_points = basis.calibration_statement(_report([], analysis={"calibration": {"points": 12}}))
    assert with_points == "Calibrated against 12 real data points you supplied."
    one = basis.calibration_statement(_report([], analysis={"calibration": {"points": 1}}))
    assert "1 real data point you" in one
    reviews = basis.calibration_statement(_report([], analysis={
        "calibration": {"points": 0, "governance": {"review_source_ids": ["r1"]}}}))
    assert reviews.startswith("Calibrated against real reviews")
    both = basis.calibration_statement(_report([], analysis={
        "calibration": {"points": 3, "governance": {"review_source_ids": ["r1"]}}}))
    assert "3 real data points and real reviews" in both
    for bad in (True, 0, -4, "9", 2.5, None):
        assert basis.calibration_statement(_report([], analysis={"calibration": {"points": bad}})).startswith("Not")
    assert basis.calibration_statement({}).startswith("Not calibrated")
    assert basis.calibration_statement({"analysis": 5}).startswith("Not calibrated")


def test_the_legend_passes_the_exploratory_language_check(real):
    to_markdown(_with(real, [_sec("summary")]))      # would raise on forbidden claim words
    to_html(_with(real, [_sec("summary")]))


def test_html_calibration_line_follows_the_record(real):
    assert "Not calibrated" in to_html(_with(real, calibration={"points": 0}))
    assert "Calibrated against 7 real data points" in to_html(_with(real, calibration={"points": 7}))


def test_a_real_report_carries_labels_on_every_section(real):
    md, page = to_markdown(real), to_html(real)
    for sec in real["sections"]:
        assert basis.basis_line(sec["key"]) in md and basis.basis_line(sec["key"]) in page


def test_legend_lines_cover_every_basis_name():
    text = "\n".join(basis.legend_lines(_report([])))
    for label, meaning in basis.BASIS.values():
        assert label in text and meaning in text


EXPECTED = {
    "summary": ("computed", "simulated", "model_written", "assumption"),
    "choice": ("computed", "simulated", "model_written", "assumption"),
    "opinion": ("computed", "simulated", "model_written", "assumption"),
    "decisions": ("computed", "simulated", "model_written", "assumption"),
    "drivers": ("computed", "simulated", "model_written", "assumption"),
    "voices": ("simulated", "model_written"),
    "range": ("estimate", "computed", "assumption"),
    "risks": ("model_written", "assumption"),
    "recommendations": ("model_written", "assumption"),
    "decision-detail": ("computed", "simulated"),
    "range-detail": ("estimate", "computed", "assumption"),
    "voices-detail": ("computed", "simulated"),
    "quotes": ("simulated",),
}


def test_the_exact_labels_for_every_known_part():
    assert basis.SECTION_BASIS == EXPECTED
    for key, labels in EXPECTED.items():
        assert basis.section_basis(key) == labels


def test_parts_the_renderer_adds_carry_their_own_labels(real):
    page = to_html(_with(real, [_sec("summary")]))
    for key in ("decision-detail", "range-detail", "voices-detail"):
        start = page.index(f'id="{key}"')
        heading_end = page.index("</h2>", start) + len("</h2>")
        assert page[heading_end:].startswith(f'<p class="basis small muted">{basis.basis_line(key)}</p>'), key


def test_review_ids_must_be_a_list():
    cal = {"points": 0, "governance": {"review_source_ids": "r1"}}
    assert basis.calibration_statement(_report([], analysis={"calibration": cal})).startswith("Not calibrated")

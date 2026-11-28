"""What kind of statement each part of a report is, assigned by code and never by the report's own text.

A report mixes numbers Agora computed from a run, descriptions of simulated people, wording a language model
wrote, and results that depend on assumptions. This module names those kinds and says which apply to each
section, so a reader can tell them apart. The labels are fixed per section key. They describe the kind of
content a section holds, not each sentence in it: a sentence-by-sentence label would need the report writer
to tag every claim, which it does not do. A section the code does not know gets the most cautious labels.

"observed" and "validated" are never attached to a section here. Whether a run was calibrated against real
data is stated once for the whole report from its calibration record, and validation is stated only by the
report's mode banner, which needs an approved registry entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

BASIS: dict[str, tuple[str, str]] = {
    "computed": ("computed by Agora", "A number worked out by Agora from this run's own records."),
    "simulated": ("simulated people", "Describes what simulated people did or said, not real people."),
    "model_written": ("wording by a language model",
                      "Sentences written by a language model from the computed numbers and simulated posts."),
    "assumption": ("depends on assumptions",
                   "Rests on settings you chose or on values not yet calibrated with real data."),
    "estimate": ("range from repeated runs", "A range or chance found by repeating the run with varied assumptions."),
}

_RUN_NUMBERS = ("computed", "simulated", "model_written", "assumption")
SECTION_BASIS: dict[str, tuple[str, ...]] = {
    "summary": _RUN_NUMBERS,
    "choice": _RUN_NUMBERS,
    "opinion": _RUN_NUMBERS,
    "decisions": _RUN_NUMBERS,
    "drivers": _RUN_NUMBERS,
    "voices": ("simulated", "model_written"),
    "range": ("estimate", "computed", "assumption"),
    "risks": ("model_written", "assumption"),
    "recommendations": ("model_written", "assumption"),
    # Parts the renderer adds that are not sections the writer plans.
    "decision-detail": ("computed", "simulated"),
    "range-detail": ("estimate", "computed", "assumption"),
    "voices-detail": ("computed", "simulated"),
    "quotes": ("simulated",),
}
CAUTIOUS = ("model_written", "assumption")


def section_basis(key: object) -> tuple[str, ...]:
    """The basis ids for one section key; an unknown or non-text key gets the cautious set."""
    return SECTION_BASIS.get(key, CAUTIOUS) if isinstance(key, str) else CAUTIOUS


def basis_line(key: object) -> str:
    """Plain text such as ``Basis: computed by Agora · simulated people``."""
    return "Basis: " + " · ".join(BASIS[b][0] for b in section_basis(key))


def calibration_statement(report: Mapping[str, Any]) -> str:
    """Whether real data was used to calibrate this run, from the report's own calibration record."""
    analysis = report.get("analysis")
    cal = analysis.get("calibration") if isinstance(analysis, Mapping) else None
    cal = cal if isinstance(cal, Mapping) else {}
    points = cal.get("points")
    governance = cal.get("governance")
    reviews = governance.get("review_source_ids") if isinstance(governance, Mapping) else None
    used = []
    if type(points) is int and points > 0:
        used.append(f"{points} real data point{'s' if points != 1 else ''}")
    if isinstance(reviews, list) and reviews:
        used.append("real reviews (they set the starting opinions)")
    if used:
        return "Calibrated against " + " and ".join(used) + " you supplied."
    return "Not calibrated: no real data was used, so starting opinions and action likelihoods are assumptions."


def legend_lines(report: Mapping[str, Any]) -> list[str]:
    """The how-to-read-this lines shown near the top of a report."""
    lines = [f"- **{label}**: {meaning}" for label, meaning in BASIS.values()]
    return ["**How to read this report.** Each section says what kind of content it holds.", *lines,
            calibration_statement(report)]


__all__ = ["BASIS", "CAUTIOUS", "SECTION_BASIS", "basis_line", "calibration_statement", "legend_lines",
           "section_basis"]

"""Time presets: how much real time one simulated round stands for.

Choose the preset that matches what is being simulated. Rounds = days * 24 / round_hours.
Changing the preset changes the pace of the simulation, not the people or the rules.
"""
from __future__ import annotations

PRESETS = {
    "market_day": (0.5, "Fast news: intraday market moves, price shocks"),
    "product_launch": (2.0, "A launch or a campaign week"),
    "election_campaign": (3.0, "Campaign weeks: several rounds a day"),
    "policy_cycle": (6.0, "Slow news: policy and corporate projects over months"),
}


def round_hours(preset: str) -> float:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Choose one of: {', '.join(PRESETS)}.")
    return PRESETS[preset][0]


def rounds_for(preset: str, days: float) -> int:
    if days <= 0:
        raise ValueError("Days must be more than zero.")
    return max(1, round(days * 24 / round_hours(preset)))


def apply(d: dict, preset: str, days: float) -> dict:
    """Return a copy of a scenario dict set to this preset's pace for `days` of real time."""
    out = dict(d)
    out.pop("minutes_per_round", None)
    out["round_hours"] = round_hours(preset)
    out["rounds"] = rounds_for(preset, days)
    return out

"""Daily rhythm and feed-ranking settings (configurable per scenario)."""
from __future__ import annotations

DEFAULT_TIME = {
    "off_peak_hours": [0, 1, 2, 3, 4, 5], "off_peak": 0.08,
    "morning_hours": [6, 7, 8], "morning": 0.7,
    "peak_hours": [17, 18, 19, 20, 21], "peak": 1.0,
    "late_hours": [22, 23], "late": 0.4,
    "other": 0.5,
}

DEFAULT_FEED = {"recency": 0.4, "popularity": 0.3, "relevance": 0.3, "echo_chamber": 0.3,
                "viral_threshold": 10}


class Rhythm:
    def __init__(self, cfg: dict | None):
        c = {**DEFAULT_TIME, **(cfg or {})}
        self.by_hour = [float(c["other"])] * 24
        for key in ("morning", "peak", "late", "off_peak"):        # later keys win
            for h in c.get(f"{key}_hours", []):
                if 0 <= int(h) < 24:
                    self.by_hour[int(h)] = float(c[key])
        if isinstance(c.get("by_hour"), list) and len(c["by_hour"]) == 24:
            self.by_hour = [float(x) for x in c["by_hour"]]

    def factor(self, hour: int, active_hours: list[int] | None = None) -> float:
        f = self.by_hour[hour % 24]
        if active_hours and len(active_hours) == 2:
            a, b = active_hours
            inside = (a <= hour < b) if a <= b else (hour >= a or hour < b)
            if not inside:
                f *= 0.05
        return f


def feed_cfg(feeds: dict | None, platform: str) -> dict:
    return {**DEFAULT_FEED, **((feeds or {}).get(platform) or {})}

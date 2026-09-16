"""Extension points for future statistical providers. Values stay MISSING."""
from __future__ import annotations

FUTURE_SLOTS = (
    "xg",
    "xga",
    "shots",
    "shots_on_target",
    "possession",
    "corners",
    "cards",
    "injuries",
    "suspensions",
    "lineups",
    "players",
    "goalkeeper",
    "tactical",
    "news",
)


def missing_slot(name: str, as_of: str | None = None) -> dict:
    return {
        "name": name,
        "value": None,
        "source": "none",
        "as_of_utc": as_of,
        "status": "MISSING",
        "sample_size": 0,
        "provider": None,
    }


def future_feature_bundle(as_of: str | None = None) -> dict[str, dict]:
    return {name: missing_slot(name, as_of) for name in FUTURE_SLOTS}


class FeatureProvider:
    """Interface for later Sportmonks/OpticOdds/etc. Do not register paid providers now."""

    code = "abstract"
    slots = FUTURE_SLOTS

    def available(self) -> bool:
        return False

    def fetch(self, match: dict, as_of_utc: str) -> dict:
        return future_feature_bundle(as_of_utc)

"""Live odds vs live score. Do not bypass OddsPapi live restrictions."""
from __future__ import annotations

LIVE_ODDS_UNAVAILABLE = "LIVE_ODDS_UNAVAILABLE"
RESTRICTED = "RESTRICTED_ACCESS"


def classify_odds_error(error_kind: str | None, http_status: int | None = None, body: str | None = "") -> str:
    blob = f"{error_kind or ''} {body or ''}".upper()
    if http_status == 403 or "RESTRICTED_ACCESS" in blob or "LIVE ACCESS" in blob:
        return LIVE_ODDS_UNAVAILABLE
    return error_kind or "unknown"


def live_view(match: dict, odds_error: dict | None = None) -> dict:
    status = match.get("status")
    score_live = status == "LIVE" and match.get("home_score") is not None
    err = odds_error or {}
    odds_state = LIVE_ODDS_UNAVAILABLE
    if err.get("kind") or err.get("http_status"):
        odds_state = classify_odds_error(err.get("kind"), err.get("http_status"), err.get("error"))
    return {
        "match_status": status,
        "live_score_available": bool(score_live or (status == "LIVE" and match.get("minute"))),
        "live_score": {
            "home": match.get("home_score"),
            "away": match.get("away_score"),
            "minute": match.get("minute"),
            "source": "bbc" if status == "LIVE" else None,
        },
        "live_odds_state": odds_state if status == "LIVE" else "NOT_LIVE",
        "live_odds": None,
        "note": "BBC live score is independent from OddsPapi live odds.",
    }

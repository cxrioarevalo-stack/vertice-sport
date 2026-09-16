def quality_for_match(match: dict) -> str:
    """Completeness only. Does not claim statistical confidence."""
    core = ["home_team", "away_team", "competition", "kickoff_utc", "status", "external_id"]
    present = sum(1 for k in core if match.get(k))
    has_score = match.get("home_score") is not None and match.get("away_score") is not None
    if present == len(core):
        if match.get("status") == "LIVE" and not (match.get("minute") or has_score):
            return "MEDIUM"
        return "HIGH"
    if present >= 4:
        return "MEDIUM"
    return "LOW"


def completeness(match: dict) -> dict:
    return {
        "competition": bool(match.get("competition")),
        "kickoff": bool(match.get("kickoff_utc")),
        "home": bool(match.get("home_team")),
        "away": bool(match.get("away_team")),
        "status": bool(match.get("status")),
        "external_id": bool(match.get("external_id")),
        "score": match.get("home_score") is not None and match.get("away_score") is not None,
        "minute": bool(match.get("minute")),
        "venue": bool(match.get("venue")),
        "form": False,
        "injuries": False,
        "lineups": False,
        "odds": False,
        "xg": False,
    }

MARKET_CATALOG = [
    {"code": "1x2", "name": "Match result 1X2", "group": "result"},
    {"code": "double_chance", "name": "Double chance", "group": "result"},
    {"code": "dnb", "name": "Draw no bet", "group": "result"},
    {"code": "handicap", "name": "Handicap", "group": "result"},
    {"code": "ah", "name": "Asian handicap", "group": "result"},
    {"code": "ou", "name": "Over/Under", "group": "goals"},
    {"code": "btts", "name": "Both teams to score", "group": "goals"},
    {"code": "team_goals", "name": "Team goals", "group": "goals"},
    {"code": "fh", "name": "First half", "group": "period"},
    {"code": "sh", "name": "Second half", "group": "period"},
    {"code": "time", "name": "Time-based markets", "group": "time"},
    {"code": "live", "name": "Live markets", "group": "live"},
]


def empty_markets() -> list[dict]:
    return [
        {
            **m,
            "odds": None,
            "data_status": "MISSING",
            "note": "MISSING DATA — Betano odds unavailable.",
        }
        for m in MARKET_CATALOG
    ]

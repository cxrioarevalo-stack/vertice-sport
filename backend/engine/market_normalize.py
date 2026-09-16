"""Read-time semantic market families. Does not rewrite provider IDs or fixture_line."""
from __future__ import annotations

from engine.product_line import annotate_product_line

FAMILY_1X2 = "1X2"
FAMILY_DOUBLE_CHANCE = "DOUBLE_CHANCE"
FAMILY_DNB = "DRAW_NO_BET"
FAMILY_BTTS = "BTTS"
FAMILY_OVER_UNDER = "OVER_UNDER"
FAMILY_TEAM_TOTAL = "TEAM_TOTAL"
FAMILY_ASIAN_HANDICAP = "ASIAN_HANDICAP"
FAMILY_EUROPEAN_HANDICAP = "EUROPEAN_HANDICAP"
FAMILY_CORRECT_SCORE = "CORRECT_SCORE"
FAMILY_HTFT = "HT_FT"
FAMILY_FIRST_GOAL = "FIRST_GOAL"
FAMILY_ODD_EVEN = "ODD_EVEN"
FAMILY_CORNERS_OU = "CORNERS_OU"
FAMILY_CORNERS_AH = "CORNERS_HANDICAP"
FAMILY_CARDS_OU = "CARDS_OU"
FAMILY_CARDS_AH = "CARDS_HANDICAP"
FAMILY_PLAYER_PROP = "PLAYER_PROP"
FAMILY_UNKNOWN = "UNKNOWN"

TYPE_BY_FAMILY = {
    FAMILY_1X2: "MATCH_RESULT",
    FAMILY_DOUBLE_CHANCE: "DOUBLE_CHANCE",
    FAMILY_DNB: "DRAW_NO_BET",
    FAMILY_BTTS: "BOTH_TEAMS_TO_SCORE",
    FAMILY_OVER_UNDER: "TOTAL_GOALS",
    FAMILY_TEAM_TOTAL: "TEAM_TOTAL_GOALS",
    FAMILY_ASIAN_HANDICAP: "ASIAN_HANDICAP",
    FAMILY_EUROPEAN_HANDICAP: "EUROPEAN_HANDICAP",
    FAMILY_CORRECT_SCORE: "CORRECT_SCORE",
    FAMILY_HTFT: "HALF_TIME_FULL_TIME",
    FAMILY_FIRST_GOAL: "FIRST_GOAL",
    FAMILY_ODD_EVEN: "ODD_EVEN_GOALS",
    FAMILY_CORNERS_OU: "CORNERS_TOTAL",
    FAMILY_CORNERS_AH: "CORNERS_HANDICAP",
    FAMILY_CARDS_OU: "CARDS_TOTAL",
    FAMILY_CARDS_AH: "CARDS_HANDICAP",
    FAMILY_PLAYER_PROP: "PLAYER_PROP",
    FAMILY_UNKNOWN: "UNKNOWN",
}

_TYPE_FAMILY = {
    "1x2": FAMILY_1X2,
    "moneyline": FAMILY_1X2,
    "doublechance": FAMILY_DOUBLE_CHANCE,
    "drawnobet": FAMILY_DNB,
    "bothteamsscore": FAMILY_BTTS,
    "totals": FAMILY_OVER_UNDER,
    "teamtotals-team1": FAMILY_TEAM_TOTAL,
    "teamtotals-team2": FAMILY_TEAM_TOTAL,
    "spreads": FAMILY_ASIAN_HANDICAP,
    "spreads-european": FAMILY_EUROPEAN_HANDICAP,
    "correctscore": FAMILY_CORRECT_SCORE,
    "exactscore": FAMILY_CORRECT_SCORE,
    "exactscore-team1": FAMILY_CORRECT_SCORE,
    "halftime-fulltime": FAMILY_HTFT,
    "firstgoal": FAMILY_FIRST_GOAL,
    "oddeven": FAMILY_ODD_EVEN,
    "totals-corners": FAMILY_CORNERS_OU,
    "oddeven-corners": FAMILY_UNKNOWN,
    "spread-corners": FAMILY_CORNERS_AH,
    "1x2-corners": FAMILY_UNKNOWN,
    "totals-bookings": FAMILY_CARDS_OU,
    "spread-bookings": FAMILY_CARDS_AH,
    "1x2-bookings": FAMILY_UNKNOWN,
    "teamtotals-corners-team1": FAMILY_UNKNOWN,
    "teamtotals-corners-team2": FAMILY_UNKNOWN,
    "teamtotals-bookings-team1": FAMILY_UNKNOWN,
    "teamtotals-bookings-team2": FAMILY_UNKNOWN,
    "players-goals": FAMILY_PLAYER_PROP,
    "players-shots": FAMILY_PLAYER_PROP,
    "players-assists": FAMILY_PLAYER_PROP,
    "players-offsides": FAMILY_PLAYER_PROP,
    "players-cards": FAMILY_PLAYER_PROP,
}

_PERIOD = {
    "fulltime": "fulltime",
    "ft": "fulltime",
    "p1": "p1",
    "1h": "p1",
    "firsthalf": "p1",
    "p2": "p2",
    "2h": "p2",
    "secondhalf": "p2",
    "result": "result",
}


def canonical_period(raw: str | None) -> str:
    if not raw:
        return "UNKNOWN"
    key = str(raw).strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return _PERIOD.get(key, "UNKNOWN")


def classify_market(market_type: str | None, market_name: str | None = None) -> tuple[str, str]:
    typ = str(market_type or "").strip().lower()
    if typ in _TYPE_FAMILY:
        family = _TYPE_FAMILY[typ]
        return family, TYPE_BY_FAMILY[family]
    name = (market_name or "").lower()
    if typ.startswith("playertotals") or typ.startswith("players-"):
        return FAMILY_PLAYER_PROP, TYPE_BY_FAMILY[FAMILY_PLAYER_PROP]
    if typ:
        return FAMILY_UNKNOWN, TYPE_BY_FAMILY[FAMILY_UNKNOWN]
    if not name:
        return FAMILY_UNKNOWN, TYPE_BY_FAMILY[FAMILY_UNKNOWN]
    return FAMILY_UNKNOWN, TYPE_BY_FAMILY[FAMILY_UNKNOWN]


READY = "READY"
CONDITIONAL = "CONDITIONALLY_READY"
NOT_READY = "NOT_READY"

NO_LINE_READY = {FAMILY_1X2, FAMILY_DOUBLE_CHANCE, FAMILY_DNB, FAMILY_BTTS}
LINE_REQUIRED = {
    FAMILY_OVER_UNDER,
    FAMILY_TEAM_TOTAL,
    FAMILY_CORNERS_OU,
    FAMILY_CARDS_OU,
    FAMILY_ASIAN_HANDICAP,
    FAMILY_EUROPEAN_HANDICAP,
    FAMILY_CORNERS_AH,
    FAMILY_CARDS_AH,
}
PERIOD_SENSITIVE = {FAMILY_HTFT}  # also any non-fulltime period must be known


def parse_decimal_odds(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 1.0:
        return None
    return n


def market_implied_probability(decimal_odds: float | None) -> tuple[float | None, str | None]:
    """Raw 1/odds. MARKET-derived only. Not a model probability."""
    if decimal_odds is None or decimal_odds <= 1.0:
        return None, None
    return 1.0 / decimal_odds, "MARKET"


def market_readiness(row: dict) -> str:
    family = row.get("market_family")
    period = row.get("period_canonical")
    price = row.get("decimal_odds_valid")
    if price is None:
        return NOT_READY
    if family == FAMILY_UNKNOWN or not family:
        return NOT_READY
    if family == FAMILY_PLAYER_PROP:
        if not row.get("player_id") or row.get("product_line") is None:
            return NOT_READY
        return CONDITIONAL
    if period == "UNKNOWN" and family in LINE_REQUIRED | NO_LINE_READY | {FAMILY_HTFT, FAMILY_FIRST_GOAL, FAMILY_ODD_EVEN, FAMILY_CORRECT_SCORE}:
        return NOT_READY
    if family in NO_LINE_READY:
        return READY
    if family in LINE_REQUIRED:
        status = row.get("product_line_status")
        if row.get("product_line") is None or status in ("MISSING", "AMBIGUOUS"):
            return NOT_READY
        if status == "CATALOG_PRODUCT":
            return CONDITIONAL
        return NOT_READY
    if family in {FAMILY_CORRECT_SCORE, FAMILY_HTFT, FAMILY_FIRST_GOAL, FAMILY_ODD_EVEN}:
        return CONDITIONAL
    return NOT_READY


def market_identity(row: dict) -> tuple:
    return (
        row.get("provider_code"),
        row.get("provider_event_id"),
        row.get("market_id") or row.get("market_code"),
        row.get("outcome_id"),
        row.get("snapshot_id"),
    )


def normalize_market(row: dict) -> dict:
    out = annotate_product_line(dict(row))
    family, ctype = classify_market(
        out.get("market_type"),
        out.get("market_name_official") or out.get("market_name"),
    )
    period_raw = out.get("period_official") or out.get("period")
    out["market_family"] = family
    out["market_type_canonical"] = ctype
    out["period_canonical"] = canonical_period(period_raw)
    raw_price = out.get("decimal_odds")
    valid = parse_decimal_odds(raw_price)
    out["decimal_odds_raw"] = raw_price
    out["decimal_odds_valid"] = valid
    if valid is not None:
        out["decimal_odds"] = valid
    implied, src = market_implied_probability(valid)
    out["implied_probability"] = implied
    out["implied_probability_source"] = src
    out["as_of"] = out.get("observed_at") or out.get("as_of") or out.get("source_updated_at")
    out["bookmaker"] = out.get("bookmaker") or out.get("bookmaker_slug")
    out["original_market_name"] = out.get("market_name_official") or out.get("market_name")
    out["original_outcome_name"] = out.get("outcome_name_official") or out.get("outcome_name_raw")
    out["market_readiness"] = market_readiness(out)
    out["market_identity"] = market_identity(out)
    return out

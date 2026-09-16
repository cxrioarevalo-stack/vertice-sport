"""Conservative settlement of market observations against stored match scores.

Read-time only. Does not write historical scans. Not a prediction.
"""
from __future__ import annotations

from engine.market_normalize import (
    FAMILY_1X2,
    FAMILY_ASIAN_HANDICAP,
    FAMILY_BTTS,
    FAMILY_DOUBLE_CHANCE,
    FAMILY_DNB,
    FAMILY_EUROPEAN_HANDICAP,
    FAMILY_OVER_UNDER,
    FAMILY_TEAM_TOTAL,
    normalize_market,
)
from engine.product_line import STATUS_PRODUCT

WON = "WON"
LOST = "LOST"
VOID = "VOID"
UNKNOWN = "UNKNOWN"


def _scores(result: dict | None) -> tuple[int | None, int | None]:
    if not result:
        return None, None
    try:
        h = result.get("home_score")
        a = result.get("away_score")
        if h is None or a is None:
            return None, None
        return int(h), int(a)
    except (TypeError, ValueError):
        return None, None


def _name(row: dict) -> str:
    return str(row.get("outcome_name_official") or row.get("outcome_name_raw") or row.get("selection") or "").strip().lower()


def _oid(row: dict) -> str:
    return str(row.get("outcome_id") or "")


def settle_1x2(home: int, away: int, row: dict) -> str:
    label = _name(row)
    oid = _oid(row)
    if home > away:
        winner = "home"
    elif home < away:
        winner = "away"
    else:
        winner = "draw"
    if label in {"1", "home", "h"} or oid == "101":
        pick = "home"
    elif label in {"x", "draw", "d"} or oid == "102":
        pick = "draw"
    elif label in {"2", "away", "a"} or oid == "103":
        pick = "away"
    else:
        return UNKNOWN
    return WON if pick == winner else LOST


def settle_btts(home: int, away: int, row: dict) -> str:
    yes = home > 0 and away > 0
    label = _name(row)
    if label in {"yes", "y", "gg", "both"}:
        return WON if yes else LOST
    if label in {"no", "n", "ng"}:
        return WON if not yes else LOST
    return UNKNOWN


def settle_ou(home: int, away: int, row: dict) -> str:
    line = row.get("product_line")
    if line is None or row.get("product_line_status") != STATUS_PRODUCT:
        return UNKNOWN
    total = home + away
    label = _name(row)
    try:
        line_f = float(line)
    except (TypeError, ValueError):
        return UNKNOWN
    if abs(total - line_f) < 1e-12:
        return VOID
    over = total > line_f
    if label in {"over", "o"} or "over" in label:
        return WON if over else LOST
    if label in {"under", "u"} or "under" in label:
        return WON if not over else LOST
    return UNKNOWN


def settle_team_total(home: int, away: int, row: dict) -> str:
    line = row.get("product_line")
    if line is None or row.get("product_line_status") != STATUS_PRODUCT:
        return UNKNOWN
    typ = str(row.get("market_type") or "")
    if typ == "teamtotals-team1":
        goals = home
    elif typ == "teamtotals-team2":
        goals = away
    else:
        return UNKNOWN
    label = _name(row)
    try:
        line_f = float(line)
    except (TypeError, ValueError):
        return UNKNOWN
    if abs(goals - line_f) < 1e-12:
        return VOID
    over = goals > line_f
    if "over" in label:
        return WON if over else LOST
    if "under" in label:
        return WON if not over else LOST
    return UNKNOWN


def settle_ah(home: int, away: int, row: dict) -> str:
    line = row.get("product_line")
    if line is None or row.get("product_line_status") != STATUS_PRODUCT:
        return UNKNOWN
    try:
        line_f = float(line)
    except (TypeError, ValueError):
        return UNKNOWN
    margin = home + line_f - away
    if abs(margin) < 1e-12:
        return VOID
    label = _name(row)
    home_win = margin > 0
    if label in {"1", "home", "h"} or oid_home(row):
        return WON if home_win else LOST
    if label in {"2", "away", "a"} or oid_away(row):
        return WON if not home_win else LOST
    return UNKNOWN


def oid_home(row: dict) -> bool:
    return _oid(row) in {"1", "101"} and "away" not in _name(row)


def oid_away(row: dict) -> bool:
    return _oid(row) in {"2", "103"}


def settle_observation(row: dict, result: dict | None) -> dict:
    n = normalize_market(dict(row))
    n["implied_probability_source"] = n.get("implied_probability_source") or "MARKET"
    n["model_probability"] = None
    n["ev"] = None
    n["value"] = None
    n["historical_outcome"] = UNKNOWN
    n["settlement_reason"] = "insufficient_result"
    home, away = _scores(result)
    period = n.get("period_canonical")
    if period not in {"fulltime", None} and period != "fulltime":
        if period in {"p1", "p2"}:
            n["historical_outcome"] = UNKNOWN
            n["settlement_reason"] = "period_score_unavailable"
            return n
    if home is None:
        return n
    family = n.get("market_family")
    if family == FAMILY_1X2 and period == "fulltime":
        n["historical_outcome"] = settle_1x2(home, away, n)
        n["settlement_reason"] = "final_score_1x2"
    elif family == FAMILY_BTTS and period == "fulltime":
        n["historical_outcome"] = settle_btts(home, away, n)
        n["settlement_reason"] = "final_score_btts"
    elif family == FAMILY_OVER_UNDER and period == "fulltime":
        n["historical_outcome"] = settle_ou(home, away, n)
        n["settlement_reason"] = "final_score_ou" if n["historical_outcome"] != UNKNOWN else "ou_unresolved"
    elif family == FAMILY_TEAM_TOTAL and period == "fulltime":
        n["historical_outcome"] = settle_team_total(home, away, n)
        n["settlement_reason"] = "final_score_team_total" if n["historical_outcome"] != UNKNOWN else "team_total_unresolved"
    elif family in {FAMILY_ASIAN_HANDICAP, FAMILY_EUROPEAN_HANDICAP} and period == "fulltime":
        if family == FAMILY_EUROPEAN_HANDICAP:
            n["historical_outcome"] = UNKNOWN
            n["settlement_reason"] = "eh_settlement_not_unique"
        else:
            n["historical_outcome"] = settle_ah(home, away, n)
            n["settlement_reason"] = "final_score_ah" if n["historical_outcome"] != UNKNOWN else "ah_unresolved"
    elif family in {FAMILY_DOUBLE_CHANCE, FAMILY_DNB}:
        n["historical_outcome"] = UNKNOWN
        n["settlement_reason"] = "selection_not_uniquely_identified"
    else:
        n["settlement_reason"] = "market_not_settled"
    if n["historical_outcome"] == UNKNOWN and n["settlement_reason"] == "final_score_1x2":
        n["settlement_reason"] = "selection_not_uniquely_identified"
    return n


def summarize_outcomes(rows: list[dict]) -> dict:
    counts = {WON: 0, LOST: 0, VOID: 0, UNKNOWN: 0}
    by_family: dict[str, dict[str, int]] = {}
    for r in rows:
        o = r.get("historical_outcome") or UNKNOWN
        counts[o] = counts.get(o, 0) + 1
        fam = r.get("market_family") or "UNKNOWN"
        by_family.setdefault(fam, {WON: 0, LOST: 0, VOID: 0, UNKNOWN: 0})
        by_family[fam][o] = by_family[fam].get(o, 0) + 1
    resolved = counts[WON] + counts[LOST] + counts[VOID]
    return {
        "total": len(rows),
        "resolved": resolved,
        "unresolved": counts[UNKNOWN],
        "WON": counts[WON],
        "LOST": counts[LOST],
        "VOID": counts[VOID],
        "UNKNOWN": counts[UNKNOWN],
        "by_family": by_family,
    }

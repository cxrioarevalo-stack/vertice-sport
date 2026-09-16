"""Read-time product_line from OddsPapi catalog. Never writes fixture_line."""
from __future__ import annotations

import re
from typing import Any

STATUS_PRODUCT = "CATALOG_PRODUCT"
STATUS_MISSING = "MISSING"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_NONE = "NOT_APPLICABLE"

LINE_TYPES = {
    "totals",
    "teamtotals-team1",
    "teamtotals-team2",
    "spreads",
    "spreads-european",
    "totals-corners",
    "spread-corners",
    "totals-bookings",
    "spread-bookings",
    "teamtotals-corners-team1",
    "teamtotals-corners-team2",
    "teamtotals-bookings-team1",
    "teamtotals-bookings-team2",
}

NO_LINE_TYPES = {
    "1x2",
    "1x2-corners",
    "1x2-bookings",
    "doublechance",
    "drawnobet",
    "bothteamsscore",
    "correctscore",
    "exactscore",
    "exactscore-team1",
    "halftime-fulltime",
    "firstgoal",
    "oddeven",
    "oddeven-corners",
    "moneyline",
    "highestscoringh",
    "winningmargin",
    "winfrombehind",
}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numbers_in_name(name: str | None) -> list[float]:
    if not name:
        return []
    cleaned = re.sub(r"\bteam\s*[12]\b", " ", name, flags=re.I)
    found = []
    for tok in re.findall(r"-?\d+(?:\.\d+)?", cleaned):
        try:
            found.append(float(tok))
        except ValueError:
            continue
    return found


def _explicit_zero_in_name(name: str | None) -> bool:
    if not name:
        return False
    return bool(re.search(r"(?:^|[^\d])0(?:\.0+)?(?:[^\d]|$)", name))


def resolve_product_line(market_id: str | None, catalog_row: dict | None) -> tuple[float | None, str]:
    if not catalog_row:
        return None, STATUS_MISSING
    typ = str(catalog_row.get("market_type") or "").lower()
    name = catalog_row.get("market_name") or catalog_row.get("market_name_official")
    hcap = _to_float(catalog_row.get("catalog_handicap"))
    if typ in NO_LINE_TYPES:
        return None, STATUS_NONE
    if typ not in LINE_TYPES and typ:
        if hcap is None:
            return None, STATUS_NONE
    if typ not in LINE_TYPES and not typ:
        return None, STATUS_MISSING
    if typ not in LINE_TYPES:
        return None, STATUS_AMBIGUOUS
    if hcap is None:
        return None, STATUS_MISSING
    named = _numbers_in_name(name)
    named_non_period = [n for n in named if n not in (1.0, 2.0) or "handicap" in (name or "").lower() or "over" in (name or "").lower()]
    if named:
        distinct = {round(n, 4) for n in named}
        if len(distinct) == 1 and abs(next(iter(distinct)) - hcap) > 1e-9:
            return None, STATUS_AMBIGUOUS
        if len(distinct) > 1 and hcap not in distinct and round(hcap, 4) not in {round(n, 4) for n in named}:
            return None, STATUS_AMBIGUOUS
    if abs(hcap) < 1e-12 and typ.startswith("spread"):
        if not _explicit_zero_in_name(name):
            return None, STATUS_AMBIGUOUS
    return hcap, STATUS_PRODUCT


def annotate_product_line(row: dict) -> dict:
    catalog = {
        "market_type": row.get("market_type"),
        "market_name": row.get("market_name_official") or row.get("market_name"),
        "catalog_handicap": row.get("catalog_handicap"),
    }
    value, status = resolve_product_line(str(row.get("market_id") or row.get("market_code") or ""), catalog)
    out = dict(row)
    out["product_line"] = value
    out["product_line_status"] = status
    return out

"""Read-time historical evaluation. No ROI, EV, or model_probability."""
from __future__ import annotations

from collections import defaultdict

from engine.market_normalize import parse_decimal_odds
from engine.settlement import LOST, UNKNOWN, VOID, WON

INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
HISTORICAL_BASELINE = "HISTORICAL_BASELINE"
EVALUATION_READY = "EVALUATION_READY"

SAMPLE_BASELINE = 30
SAMPLE_READY = 100

ODDS_BUCKETS = (
    ("<1.50", 0.0, 1.50),
    ("1.50-1.99", 1.50, 2.00),
    ("2.00-2.99", 2.00, 3.00),
    ("3.00-4.99", 3.00, 5.00),
    ("5.00-9.99", 5.00, 10.00),
    ("10.00+", 10.00, None),
)


def odds_bucket(price) -> str | None:
    n = parse_decimal_odds(price)
    if n is None:
        return None
    for name, lo, hi in ODDS_BUCKETS:
        if hi is None:
            if n >= lo:
                return name
        elif lo <= n < hi:
            return name
    return None


def sample_sufficiency(n: int) -> str:
    if n < SAMPLE_BASELINE:
        return INSUFFICIENT_SAMPLE
    if n < SAMPLE_READY:
        return HISTORICAL_BASELINE
    return EVALUATION_READY


def _empty_counts() -> dict:
    return {WON: 0, LOST: 0, VOID: 0, UNKNOWN: 0}


def evaluate(observations: list[dict], *, filters: dict | None = None) -> dict:
    rows = list(observations)
    if filters:
        for key, val in filters.items():
            if val is None or val == "":
                continue
            if key == "odds_bucket":
                rows = [r for r in rows if odds_bucket(r.get("decimal_odds")) == val]
            elif key == "settlement":
                rows = [r for r in rows if r.get("settlement_result") == val]
            elif key == "market_type":
                rows = [r for r in rows if r.get("market_type_canonical") == val]
            else:
                rows = [r for r in rows if r.get(key) == val]

    counts = _empty_counts()
    prices = []
    implied = []
    by_family: dict[str, dict] = defaultdict(_empty_counts)
    by_type: dict[str, dict] = defaultdict(_empty_counts)
    by_line: dict[str, dict] = defaultdict(_empty_counts)
    by_period: dict[str, dict] = defaultdict(_empty_counts)
    by_comp: dict[str, dict] = defaultdict(_empty_counts)
    by_bucket: dict[str, dict] = defaultdict(_empty_counts)

    for r in rows:
        o = r.get("settlement_result") or UNKNOWN
        counts[o] = counts.get(o, 0) + 1
        fam = r.get("market_family") or "UNKNOWN"
        by_family[fam][o] += 1
        typ = r.get("market_type_canonical") or "UNKNOWN"
        by_type[typ][o] += 1
        line = r.get("product_line")
        by_line[str(line) if line is not None else "NULL"][o] += 1
        by_period[r.get("period_canonical") or "UNKNOWN"][o] += 1
        by_comp[r.get("competition") or "UNKNOWN"][o] += 1
        price = parse_decimal_odds(r.get("decimal_odds"))
        if price is not None:
            prices.append(price)
            b = odds_bucket(price)
            if b:
                by_bucket[b][o] += 1
            ip = r.get("implied_probability")
            if ip is not None:
                implied.append(float(ip))

    resolved_wl = counts[WON] + counts[LOST]
    resolved_all = resolved_wl + counts[VOID]
    total = len(rows)
    win_rate = (counts[WON] / resolved_wl) if resolved_wl else None
    return {
        "total": total,
        "resolved": resolved_all,
        "unresolved": counts[UNKNOWN],
        "WON": counts[WON],
        "LOST": counts[LOST],
        "VOID": counts[VOID],
        "UNKNOWN": counts[UNKNOWN],
        "win_rate_resolved_non_void": win_rate,
        "void_rate": (counts[VOID] / total) if total else None,
        "unknown_rate": (counts[UNKNOWN] / total) if total else None,
        "average_decimal_odds": (sum(prices) / len(prices)) if prices else None,
        "average_implied_probability": (sum(implied) / len(implied)) if implied else None,
        "sample_sufficiency": sample_sufficiency(resolved_wl),
        "sample_sufficiency_resolved_non_void": resolved_wl,
        "by_market_family": dict(by_family),
        "by_market_type_canonical": dict(by_type),
        "by_product_line": dict(by_line),
        "by_period_canonical": dict(by_period),
        "by_competition": dict(by_comp),
        "by_odds_bucket": dict(by_bucket),
        "model_probability": None,
        "ev": None,
    }

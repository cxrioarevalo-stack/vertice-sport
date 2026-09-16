"""Read-time analysis gate. No model_probability, no EV, no picks."""
from __future__ import annotations

from collections import defaultdict

from engine.market_normalize import (
    CONDITIONAL,
    NOT_READY,
    READY,
    normalize_market,
)

OK = "OK"
PARTIAL = "PARTIAL"
DATA_INSUFFICIENT = "DATA_INSUFFICIENT"

ANALYZE = "ANALYZE"
WATCH = "WATCH"
EXCLUDE = "EXCLUDE"
NO_BET = "NO_BET"

RISKY_INTEGRITY = {"HIGH", "CRITICAL", "FAIL", "FAILED"}


def _integrity_risk(row: dict) -> bool:
    level = str(row.get("integrity_level") or "").upper()
    return level in RISKY_INTEGRITY


def analyze_market(row: dict) -> dict:
    n = normalize_market(dict(row))
    readiness = n.get("market_readiness")
    phase = n.get("phase") or "PREMATCH"
    n["model_probability"] = None
    n["ev"] = None
    n["value"] = None
    n["confidence"] = None
    n["model_version"] = None
    n["feature_set"] = None
    n["implied_probability_source"] = n.get("implied_probability_source")
    n["data_completeness"] = DATA_INSUFFICIENT
    n["data_completeness_reason"] = (
        "No xG, match statistics, injuries, lineups, player stats, or independent model."
    )
    if _integrity_risk(n):
        n["analysis_state"] = EXCLUDE
        n["analysis_reason"] = "existing_integrity_risk"
        n["structurally_analyzable"] = False
        return n
    if phase == "LIVE":
        n["analysis_state"] = EXCLUDE
        n["analysis_reason"] = "live_odds_not_supported"
        n["structurally_analyzable"] = False
        return n
    if readiness == READY:
        n["analysis_state"] = ANALYZE
        n["analysis_reason"] = "structural_ready_context_insufficient"
        n["structurally_analyzable"] = True
        n["data_status"] = PARTIAL
        return n
    if readiness == CONDITIONAL:
        n["analysis_state"] = WATCH
        n["analysis_reason"] = "conditionally_ready_missing_context"
        n["structurally_analyzable"] = True
        n["data_status"] = DATA_INSUFFICIENT
        return n
    n["analysis_state"] = EXCLUDE
    n["analysis_reason"] = "not_structurally_ready"
    n["structurally_analyzable"] = False
    n["data_status"] = DATA_INSUFFICIENT
    return n


def _compat_key(row: dict) -> tuple:
    return (
        row.get("provider_code"),
        row.get("provider_event_id"),
        row.get("market_family"),
        row.get("period_canonical"),
        row.get("product_line"),
        row.get("bookmaker"),
    )


def group_compatible_markets(rows: list[dict]) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[_compat_key(r)].append(r)
    return dict(groups)


def analyze_fixture(rows: list[dict]) -> dict:
    analyzed = [analyze_market(r) for r in rows]
    states = [r["analysis_state"] for r in analyzed]
    if any(s == ANALYZE for s in states):
        fixture_state = ANALYZE
    elif any(s == WATCH for s in states):
        fixture_state = WATCH
    elif analyzed:
        fixture_state = NO_BET
    else:
        fixture_state = NO_BET
    return {
        "markets": analyzed,
        "groups": {str(k): v for k, v in group_compatible_markets(analyzed).items()},
        "fixture_analysis_state": fixture_state,
        "analyze_count": states.count(ANALYZE),
        "watch_count": states.count(WATCH),
        "exclude_count": states.count(EXCLUDE),
        "model_probability": None,
        "ev": None,
        "no_bet": fixture_state == NO_BET,
        "no_bet_reason": "no_analyzable_market" if fixture_state == NO_BET else None,
        "data_completeness": DATA_INSUFFICIENT,
    }

"""Daily analysis pipeline over already-ingested rows. No new provider calls."""
from __future__ import annotations

from engine.analysis import analyze_fixture
from engine.calibration import calibration_report
from engine.combination import combine
from engine.features import build_features
from engine.future_features import future_feature_bundle
from engine.live import live_view
from engine.model import model_probability, model_status
from engine.risk import risk_state
from engine.selection import select_today
from engine.value import expected_value


def analyze_match_bundle(match: dict, market_rows: list[dict], as_of_utc: str,
                         history: list[dict] | None = None) -> dict:
    ms = model_status()
    fixture = analyze_fixture(market_rows)
    selection = select_today(market_rows, ms["model_status"])
    feats = None
    try:
        feats = build_features(match, as_of_utc, market_rows[0] if market_rows else None, history)
    except Exception:
        feats = None
    pred = model_probability(feats, market_rows[0] if market_rows else None)
    ev = expected_value(pred.get("model_probability"), (market_rows[0] or {}).get("decimal_odds") if market_rows else None)
    risk = risk_state(match)
    live = live_view(match)
    return {
        "match": {
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "status": match.get("status"),
            "competition": match.get("competition"),
        },
        "model": ms,
        "prediction": pred,
        "ev": ev,
        "features": feats,
        "future_features": future_feature_bundle(as_of_utc),
        "analysis": fixture,
        "selection": selection,
        "combinations": combine(market_rows),
        "risk": risk,
        "live": live,
        "calibration": calibration_report([]),
        "headline": selection.get("headline") or "NO BET TODAY",
    }

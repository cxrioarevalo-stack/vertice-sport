import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.analysis import (
    ANALYZE,
    DATA_INSUFFICIENT,
    EXCLUDE,
    NO_BET,
    WATCH,
    analyze_fixture,
    analyze_market,
)


def _row(**kw):
    base = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "market_id": "101",
        "outcome_id": "101",
        "market_name_official": "Full Time Result",
        "market_type": "1x2",
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 1.90,
        "fixture_line": None,
        "catalog_handicap": None,
        "snapshot_id": 13,
        "match_id": None,
        "observed_at": "2026-09-09T12:00:00+00:00",
        "bookmaker": "betano",
    }
    base.update(kw)
    return base


def test_valid_1x2_analyze():
    a = analyze_market(_row())
    assert a["analysis_state"] == ANALYZE
    assert a["model_probability"] is None
    assert a["ev"] is None
    assert a["implied_probability_source"] == "MARKET"
    assert a["snapshot_id"] == 13
    assert a["match_id"] is None
    assert a["fixture_line"] is None
    assert a["data_completeness"] == DATA_INSUFFICIENT


def test_valid_ou_watch():
    a = analyze_market(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        catalog_handicap=2.5,
    ))
    assert a["analysis_state"] == WATCH
    assert a["product_line"] == 2.5
    assert a["fixture_line"] is None


def test_ambiguous_ah_exclude():
    a = analyze_market(_row(
        market_id="10604", market_type="spreads",
        market_name_official="Asian Handicap First Half",
        catalog_handicap=0.0, period_official="p1",
    ))
    assert a["analysis_state"] == EXCLUDE


def test_missing_product_line_exclude():
    a = analyze_market(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        catalog_handicap=None,
    ))
    assert a["analysis_state"] == EXCLUDE


def test_invalid_odds_exclude():
    a = analyze_market(_row(decimal_odds=0))
    assert a["analysis_state"] == EXCLUDE


def test_period_and_phase():
    a = analyze_market(_row(period_official="p1"))
    assert a["period_canonical"] == "p1"
    live = analyze_market(_row(phase="LIVE"))
    assert live["analysis_state"] == EXCLUDE
    assert live["analysis_reason"] == "live_odds_not_supported"


def test_data_insufficient_and_no_model():
    a = analyze_market(_row())
    assert a["data_completeness"] == DATA_INSUFFICIENT
    assert a["model_probability"] is None
    assert a["ev"] is None
    assert a["value"] is None


def test_no_bet_when_all_excluded():
    fx = analyze_fixture([
        _row(decimal_odds="bad"),
        _row(market_type="11-overs", market_name_official="11 Overs"),
    ])
    assert fx["fixture_analysis_state"] == NO_BET
    assert fx["no_bet"] is True
    assert fx["model_probability"] is None
    assert fx["ev"] is None


def test_watch_fixture():
    fx = analyze_fixture([_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time", catalog_handicap=2.5,
    )])
    assert fx["fixture_analysis_state"] == WATCH
    assert fx["no_bet"] is False

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.settlement import LOST, UNKNOWN, VOID, WON, settle_observation, summarize_outcomes


def _row(**kw):
    base = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "market_id": "101",
        "outcome_id": "101",
        "outcome_name_official": "1",
        "market_name_official": "Full Time Result",
        "market_type": "1x2",
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 1.90,
        "fixture_line": None,
        "catalog_handicap": None,
        "snapshot_id": 9,
        "match_id": None,
    }
    base.update(kw)
    return base


RES = {"home_score": 2, "away_score": 1}


def test_1x2_home_win():
    a = settle_observation(_row(), RES)
    assert a["historical_outcome"] == WON
    assert a["model_probability"] is None
    assert a["ev"] is None
    assert a["implied_probability_source"] == "MARKET"
    assert a["fixture_line"] is None
    assert a["snapshot_id"] == 9
    assert a["match_id"] is None


def test_1x2_away_lost():
    a = settle_observation(_row(outcome_id="103", outcome_name_official="2"), RES)
    assert a["historical_outcome"] == LOST


def test_btts():
    yes = settle_observation(_row(
        market_type="bothteamsscore", market_id="104",
        outcome_name_official="Yes", outcome_id="104",
    ), RES)
    no = settle_observation(_row(
        market_type="bothteamsscore", market_id="104",
        outcome_name_official="No", outcome_id="105",
    ), {"home_score": 2, "away_score": 0})
    assert yes["historical_outcome"] == WON
    assert no["historical_outcome"] == WON


def test_ou_with_product_line():
    over = settle_observation(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        outcome_name_official="Over", catalog_handicap=2.5,
    ), RES)
    assert over["product_line"] == 2.5
    assert over["historical_outcome"] == WON
    void = settle_observation(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        outcome_name_official="Over", catalog_handicap=3.0,
    ), {"home_score": 2, "away_score": 1})
    assert void["historical_outcome"] == VOID


def test_missing_product_line_unknown():
    a = settle_observation(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        outcome_name_official="Over", catalog_handicap=None,
    ), RES)
    assert a["historical_outcome"] == UNKNOWN


def test_ambiguous_ah_unknown():
    a = settle_observation(_row(
        market_id="10604", market_type="spreads",
        market_name_official="Asian Handicap First Half",
        outcome_name_official="1", catalog_handicap=0.0,
        period_official="fulltime",
    ), RES)
    assert a["historical_outcome"] == UNKNOWN


def test_insufficient_result():
    a = settle_observation(_row(), None)
    assert a["historical_outcome"] == UNKNOWN


def test_period_specific_unknown():
    a = settle_observation(_row(period_official="p1"), RES)
    assert a["historical_outcome"] == UNKNOWN
    assert a["settlement_reason"] == "period_score_unavailable"


def test_summary_counts():
    rows = [
        settle_observation(_row(), RES),
        settle_observation(_row(outcome_id="103", outcome_name_official="2"), RES),
        settle_observation(_row(), None),
    ]
    s = summarize_outcomes(rows)
    assert s["total"] == 3
    assert s["WON"] == 1
    assert s["LOST"] == 1
    assert s["UNKNOWN"] == 1
    assert s["resolved"] == 2

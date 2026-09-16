import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.historical_dataset import build_observation
from engine.settlement import LOST, UNKNOWN, VOID, WON


def _row(**kw):
    base = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "sport_key": "football",
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
        "snapshot_id": 42,
        "match_id": None,
        "observed_at": "2026-09-07T12:00:00+00:00",
        "bookmaker": "betano",
    }
    base.update(kw)
    return base


def test_observation_from_existing_shape():
    obs = build_observation(
        _row(),
        {"home_score": 2, "away_score": 1},
        {"competition": "Serie A", "home_team": "A", "away_team": "B", "kickoff_utc": "2026-09-07T17:00:00Z"},
    )
    assert obs["settlement_result"] == WON
    assert obs["as_of_utc"] == "2026-09-07T12:00:00+00:00"
    assert obs["competition"] == "Serie A"
    assert obs["match_id"] is None
    assert obs["snapshot_id"] == 42
    assert obs["model_probability"] is None
    assert obs["ev"] is None
    assert obs["result_used_for"] == "settlement_only"
    assert abs(obs["implied_probability"] - 1 / 1.90) < 1e-12
    assert obs["implied_probability_source"] == "MARKET"


def test_lost_and_void_and_unknown():
    lost = build_observation(_row(outcome_id="103", outcome_name_official="2"), {"home_score": 2, "away_score": 1})
    void = build_observation(_row(
        market_id="1010", market_type="totals", market_name_official="Over Under Full Time",
        outcome_name_official="Over", catalog_handicap=3.0,
    ), {"home_score": 2, "away_score": 1})
    unk = build_observation(_row(), None)
    assert lost["settlement_result"] == LOST
    assert void["settlement_result"] == VOID
    assert unk["settlement_result"] == UNKNOWN


def test_fixture_line_not_from_product():
    obs = build_observation(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        outcome_name_official="Over", catalog_handicap=2.5, fixture_line=None,
    ), {"home_score": 3, "away_score": 1})
    assert obs["product_line"] == 2.5
    assert obs["fixture_line"] is None

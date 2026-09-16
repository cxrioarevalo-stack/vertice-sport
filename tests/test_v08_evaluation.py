import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.evaluation import (
    EVALUATION_READY,
    HISTORICAL_BASELINE,
    INSUFFICIENT_SAMPLE,
    evaluate,
    odds_bucket,
    sample_sufficiency,
)
from engine.historical_dataset import build_observation
from engine.settlement import LOST, UNKNOWN, VOID, WON


def _obs(result_scores, **kw):
    row = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "market_id": "101",
        "outcome_id": "101",
        "outcome_name_official": "1",
        "market_name_official": "Full Time Result",
        "market_type": "1x2",
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 2.0,
        "fixture_line": None,
        "catalog_handicap": None,
        "snapshot_id": 1,
        "match_id": None,
        "observed_at": "2026-09-07T12:00:00+00:00",
        "bookmaker": "betano",
    }
    row.update(kw)
    result = None
    if result_scores is not None:
        result = {"home_score": result_scores[0], "away_score": result_scores[1]}
    return build_observation(row, result, {"competition": kw.pop("competition_ctx", None) or "Liga"})


def test_win_rate_excludes_void_and_unknown():
    rows = [
        _obs((2, 1)),
        _obs((2, 1), outcome_id="103", outcome_name_official="2"),
        _obs((2, 1), market_id="1010", market_type="totals",
             market_name_official="Over Under Full Time", outcome_name_official="Over",
             catalog_handicap=3.0),
        _obs(None),
    ]
    ev = evaluate(rows)
    assert ev["WON"] == 1 and ev["LOST"] == 1 and ev["VOID"] == 1 and ev["UNKNOWN"] == 1
    assert ev["win_rate_resolved_non_void"] == 0.5
    assert ev["model_probability"] is None
    assert ev["ev"] is None


def test_implied_is_one_over_odds():
    ev = evaluate([_obs((2, 1), decimal_odds=2.0)])
    assert ev["average_implied_probability"] == 0.5


def test_odds_buckets_and_invalid():
    assert odds_bucket(1.40) == "<1.50"
    assert odds_bucket(1.50) == "1.50-1.99"
    assert odds_bucket(2.5) == "2.00-2.99"
    assert odds_bucket(4) == "3.00-4.99"
    assert odds_bucket(7) == "5.00-9.99"
    assert odds_bucket(11) == "10.00+"
    assert odds_bucket("bad") is None
    ev = evaluate([_obs((2, 1), decimal_odds="nope")])
    assert ev["average_decimal_odds"] is None


def test_sample_sufficiency():
    assert sample_sufficiency(5) == INSUFFICIENT_SAMPLE
    assert sample_sufficiency(30) == HISTORICAL_BASELINE
    assert sample_sufficiency(100) == EVALUATION_READY


def test_grouping_family_line_competition():
    rows = [
        _obs((2, 1)),
        _obs((3, 1), market_id="1010", market_type="totals",
             market_name_official="Over Under Full Time", outcome_name_official="Over",
             catalog_handicap=2.5),
    ]
    ev = evaluate(rows)
    assert "1X2" in ev["by_market_family"]
    assert "OVER_UNDER" in ev["by_market_family"]
    assert "2.5" in ev["by_product_line"]
    assert "Liga" in ev["by_competition"]


def test_historical_snapshots_untouched():
    import sqlite3
    c = sqlite3.connect(str(ROOT / "data" / "vertice.db"))
    before = {i: c.execute("select count(*) from odds_snapshots where scan_id=?", (i,)).fetchone()[0] for i in range(7, 14)}
    assert before == {7: 8044, 8: 7644, 9: 7645, 10: 0, 11: 0, 12: 995, 13: 1001}
    c.close()

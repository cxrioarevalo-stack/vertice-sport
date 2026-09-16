import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.calibration import calibration_report
from engine.combination import combine, families_correlated
from engine.live import LIVE_ODDS_UNAVAILABLE, classify_odds_error, live_view
from engine.model import MODEL_NOT_READY, BaselineModel, model_probability, model_status
from engine.risk import UNKNOWN, risk_state
from engine.selection import NO_BET, select_opportunity, select_today
from engine.value import expected_value
from engine.walkforward import chronological_split


def test_model_not_ready_null_probability():
    p = model_probability({"x": 1}, {"implied_probability": 0.5})
    assert p["model_probability"] is None
    assert p["market_implied_probability"] == 0.5
    assert model_status()["model_status"] == MODEL_NOT_READY


def test_baseline_refuses_small_sample():
    m = BaselineModel()
    out = m.train([{"settlement_result": "WON"}] * 10)
    assert out["trained"] is False
    assert m.status == MODEL_NOT_READY


def test_ev_null_without_model():
    ev = expected_value(None, 2.0)
    assert ev["ev"] is None
    assert ev["value"] is None


def test_ev_formula_when_model_exists():
    ev = expected_value(0.6, 2.0)
    assert abs(ev["ev"] - 0.2) < 1e-9


def test_selection_no_bet_when_model_not_ready():
    row = {
        "market_id": "101",
        "market_name_official": "Full Time Result",
        "outcome_name_official": "1",
        "decimal_odds": 1.9,
        "phase": "PREMATCH",
        "product_line_status": "CATALOG_PRODUCT",
    }
    s = select_opportunity(row)
    assert s["selection"] == NO_BET
    assert s["model_probability"] is None
    day = select_today([row])
    assert day["headline"] == "NO BET TODAY"
    assert day["picks"] == []


def test_calibration_not_ready():
    r = calibration_report([{"model_probability": None, "settlement_result": "UNKNOWN"}])
    assert r["status"] == "NOT_READY"
    assert r["brier"] is None


def test_walkforward_not_ready_and_no_shuffle():
    wf = chronological_split([])
    assert wf["status"] == "NOT_READY"
    assert wf["random_split"] is False


def test_combinations_blocked():
    assert families_correlated("BTTS", "OVER_UNDER")
    c = combine([{"model_probability": None, "market_family": "1X2"}])
    assert c["combined_probability"] is None
    assert c["assumed_independence"] is False


def test_live_odds_restricted():
    assert classify_odds_error("forbidden", 403, "RESTRICTED_ACCESS") == LIVE_ODDS_UNAVAILABLE
    v = live_view({"status": "LIVE", "home_score": 1, "away_score": 0, "minute": "67"})
    assert v["live_score_available"] is True
    assert v["live_odds"] is None
    assert v["live_odds_state"] == LIVE_ODDS_UNAVAILABLE


def test_risk_unknown_no_fix_claim():
    r = risk_state({"home_team": "A", "away_team": "B"})
    assert r["risk_state"] == UNKNOWN
    assert r["claim"] is None
    assert r["exclude_from_selection"] is False


def test_snapshots_untouched():
    import sqlite3
    c = sqlite3.connect(str(ROOT / "data" / "vertice.db"))
    snaps = {i: c.execute("select count(*) from odds_snapshots where scan_id=?", (i,)).fetchone()[0] for i in range(7, 15)}
    assert snaps[7] == 8044
    assert snaps[14] == 322
    c.close()

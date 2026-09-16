from datetime import datetime, timedelta, timezone
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.features import (
    AVAILABLE,
    FEATURE_VERSION,
    INSUFFICIENT_HISTORY,
    build_features,
)


def ko(day: int, hour=15) -> str:
    return datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def m(mid, home, away, day, hg, ag, hid=1, aid=2):
    return {
        "id": mid,
        "home_team": home,
        "away_team": away,
        "home_team_id": hid,
        "away_team_id": aid,
        "kickoff_utc": ko(day),
        "home_score": hg,
        "away_score": ag,
        "status": "FINISHED",
        "competition": "Liga",
        "sport_key": "football",
    }


HIST = [
    m(1, "Alpha", "Zeta", 1, 2, 0, 10, 90),
    m(2, "Beta", "Alpha", 2, 1, 1, 11, 10),
    m(3, "Alpha", "Gamma", 3, 3, 1, 10, 12),
    m(4, "Delta", "Alpha", 4, 0, 2, 13, 10),
    m(5, "Alpha", "Omega", 10, 4, 0, 10, 14),  # future vs as_of day 6
]


CURRENT = {
    "id": 99,
    "home_team": "Alpha",
    "away_team": "Beta",
    "home_team_id": 10,
    "away_team_id": 11,
    "kickoff_utc": ko(6),
    "home_score": 9,
    "away_score": 9,
    "competition": "Liga",
    "sport_key": "football",
}


def test_builder_and_context():
    out = build_features(CURRENT, ko(6), {"decimal_odds": 2.0, "implied_probability": 0.5}, HIST)
    assert out["feature_version"] == FEATURE_VERSION
    assert out["features"]["home_team"]["value"] == "Alpha"
    assert out["training_readiness"] == "NOT_READY"
    assert out["model_probability"] is None
    assert out["ev"] is None


def test_deterministic_hash():
    a = build_features(CURRENT, ko(6), {"decimal_odds": 2.0}, HIST)
    b = build_features(CURRENT, ko(6), {"decimal_odds": 2.0}, HIST)
    assert a["feature_hash"] == b["feature_hash"]


def test_excludes_current_and_future():
    out = build_features(CURRENT, ko(6), None, HIST)
    assert out["home_prior_n"] == 4
    names = {1, 2, 3, 4}
    # future id 5 day 10 excluded; current 99 not in hist anyway
    assert out["features"]["home_n_prior"]["value"] == 4


def test_as_of_respected():
    early = build_features(CURRENT, ko(2, 0), None, HIST)
    assert early["home_prior_n"] == 1


def test_home_away_split():
    out = build_features(CURRENT, ko(6), None, HIST)
    # Alpha home matches before day 6: id1 (2-0) id3 (3-1) — 2 samples < MIN_RATE 3
    assert out["features"]["home_home_goals_scored_avg"]["status"] == INSUFFICIENT_HISTORY
    assert out["features"]["home_home_goals_scored_avg"]["sample_size"] == 2
    assert out["features"]["home_goals_scored_avg"]["status"] == AVAILABLE
    assert out["features"]["home_goals_scored_avg"]["value"] == (2 + 1 + 3 + 2) / 4


def test_form_windows():
    extra = HIST + [
        m(6, "Alpha", "X", 4, 1, 0, 10, 20),
        m(7, "Y", "Alpha", 5, 2, 0, 21, 10),
    ]
    out = build_features(CURRENT, ko(6), None, extra)
    assert out["features"]["home_last_3_points"]["status"] == AVAILABLE
    assert out["features"]["home_last_5_points"]["status"] == AVAILABLE
    assert out["features"]["home_last_10_points"]["status"] == INSUFFICIENT_HISTORY


def test_insufficient_and_missing():
    out = build_features({"home_team": "Nobody", "away_team": "Ghost", "id": 1}, ko(6), None, HIST)
    assert out["features"]["home_goals_scored_avg"]["status"] == INSUFFICIENT_HISTORY
    assert out["features"]["home_goals_scored_avg"]["value"] is None
    assert out["features"]["home_days_since_last_match"]["status"] == "MISSING"


def test_rest_and_congestion():
    out = build_features(CURRENT, ko(6), None, HIST)
    assert out["features"]["home_days_since_last_match"]["status"] == AVAILABLE
    assert out["features"]["home_matches_last_7_days"]["value"] == 4


def test_odds_and_lines():
    mkt = {
        "decimal_odds": 2.0,
        "product_line": 2.5,
        "product_line_status": "CATALOG_PRODUCT",
        "fixture_line": None,
        "market_family": "OVER_UNDER",
    }
    out = build_features(CURRENT, ko(6), mkt, HIST)
    assert out["features"]["implied_probability"]["value"] == 0.5
    assert out["features"]["implied_probability_source"]["value"] == "MARKET"
    assert out["features"]["product_line"]["value"] == 2.5
    assert out["features"]["fixture_line"]["value"] is None
    assert out["features"]["model_probability"]["value"] is None


def test_no_db_write():
    import sqlite3
    path = ROOT / "data" / "vertice.db"
    c = sqlite3.connect(str(path))
    before = c.execute("select count(*) from odds_snapshots").fetchone()[0]
    build_features(CURRENT, ko(6), None, HIST)
    after = c.execute("select count(*) from odds_snapshots").fetchone()[0]
    assert before == after
    c.close()

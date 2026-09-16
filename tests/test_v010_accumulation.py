import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.historical_dataset import build_observation
from engine.historical_match import MATCHED, UNMATCHED, resolve_historical_match
from engine.settlement import UNKNOWN, WON


def test_upcoming_to_finished_settlement_refresh():
    row = {
        "provider_code": "oddspapi",
        "provider_event_id": "id1",
        "market_id": "101",
        "outcome_id": "101",
        "outcome_name_official": "1",
        "market_name_official": "Full Time Result",
        "market_type": "1x2",
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 1.9,
        "fixture_line": None,
        "snapshot_id": 1,
        "match_id": None,
        "observed_at": "2026-09-07T12:00:00+00:00",
    }
    unknown = build_observation(row, None)
    assert unknown["settlement_result"] == UNKNOWN
    won = build_observation(row, {"home_score": 2, "away_score": 1})
    assert won["settlement_result"] == WON
    assert won["decimal_odds"] == unknown["decimal_odds"]
    assert won["snapshot_id"] == 1


def test_resolver_ignores_score():
    pe = {
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "kickoff_utc": "2026-09-07T16:30:00Z",
        "competition": "Liga",
    }
    wrong = {
        "id": 2,
        "home_team": "Other",
        "away_team": "Side",
        "kickoff_utc": "2026-09-07T16:30:00Z",
        "home_score": 2,
        "away_score": 1,
        "competition": "Liga",
    }
    right = {
        "id": 3,
        "home_team": "Alpha",
        "away_team": "Beta",
        "kickoff_utc": "2026-09-07T16:30:00Z",
        "home_score": None,
        "away_score": None,
        "competition": "Liga",
    }
    r = resolve_historical_match(pe, [wrong, right])
    assert r["state"] == MATCHED
    assert r["match_id"] == 3


def test_unmatched_stays_null():
    r = resolve_historical_match(
        {"home_team": "X", "away_team": "Y", "kickoff_utc": "2026-09-07T16:30:00Z"},
        [],
    )
    assert r["state"] == UNMATCHED
    assert r["match_id"] is None


def test_snapshots_immutable_counts():
    import sqlite3
    c = sqlite3.connect(str(ROOT / "data" / "vertice.db"))
    snaps = {i: c.execute("select count(*) from odds_snapshots where scan_id=?", (i,)).fetchone()[0] for i in range(7, 14)}
    assert snaps == {7: 8044, 8: 7644, 9: 7645, 10: 0, 11: 0, 12: 995, 13: 1001}
    c.close()

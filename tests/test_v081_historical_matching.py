import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.historical_match import (
    AMBIGUOUS,
    MATCHED,
    REASON_MULTI,
    UNMATCHED,
    resolve_historical_match,
)


def bbc(**kw):
    base = {
        "id": 10,
        "home_team": "Cagliari",
        "away_team": "Lecce",
        "kickoff_utc": "2026-09-07T16:30:00Z",
        "competition": "Serie A",
        "home_score": 2,
        "away_score": 1,
    }
    base.update(kw)
    return base


def pe(**kw):
    base = {
        "home_team": "Cagliari Calcio",
        "away_team": "US Lecce",
        "kickoff_utc": "2026-09-07T16:30:00.000Z",
        "competition": "Serie A",
        "provider_event_id": "idABC",
    }
    base.update(kw)
    return base


def test_exact_team_time():
    r = resolve_historical_match(pe(), [bbc()])
    assert r["state"] == MATCHED
    assert r["match_id"] == 10


def test_normalized_names():
    r = resolve_historical_match(
        pe(home_team="Atlético Madrid", away_team="FC Barcelona"),
        [bbc(home_team="Atletico Madrid", away_team="Barcelona")],
    )
    assert r["state"] == MATCHED


def test_time_tolerance():
    r = resolve_historical_match(
        pe(kickoff_utc="2026-09-07T16:45:00Z"),
        [bbc(kickoff_utc="2026-09-07T16:30:00Z")],
    )
    assert r["state"] == MATCHED


def test_competition_supporting():
    r = resolve_historical_match(pe(), [bbc()])
    assert r["reason"] in {"TEAM_TIME_EXACT", "TEAM_COMPETITION_TIME"}


def test_multiple_ambiguous():
    r = resolve_historical_match(pe(), [bbc(id=1), bbc(id=2)])
    assert r["state"] == AMBIGUOUS
    assert r["reason"] == REASON_MULTI
    assert r["match_id"] is None


def test_no_candidate():
    r = resolve_historical_match(pe(), [bbc(home_team="Milan", away_team="Roma")])
    assert r["state"] == UNMATCHED
    assert r["match_id"] is None


def test_missing_team():
    r = resolve_historical_match(pe(home_team=None), [bbc()])
    assert r["state"] == UNMATCHED
    assert r["match_id"] is None


def test_score_not_used():
    r = resolve_historical_match(
        pe(),
        [bbc(home_score=9, away_score=9, home_team="Other", away_team="Side", id=99)],
    )
    assert r["state"] == UNMATCHED


def test_match_id_not_provider_id():
    r = resolve_historical_match(pe(), [bbc(id=77)])
    assert r["match_id"] == 77
    assert r["match_id"] != "idABC"


def test_historical_scans_untouched():
    import sqlite3
    c = sqlite3.connect(str(ROOT / "data" / "vertice.db"))
    snaps = {i: c.execute("select count(*) from odds_snapshots where scan_id=?", (i,)).fetchone()[0] for i in range(7, 14)}
    assert snaps == {7: 8044, 8: 7644, 9: 7645, 10: 0, 11: 0, 12: 995, 13: 1001}
    c.close()

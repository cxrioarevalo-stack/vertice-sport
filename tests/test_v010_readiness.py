import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.evaluation import evaluate
from engine.historical_dataset import build_observation
from engine.readiness import NOT_READY, assess_readiness, temporal_from_dates, walk_forward_possible
from engine.settlement import UNKNOWN, WON


def _obs(scores=None, **kw):
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
        "decimal_odds": 2.0,
        "fixture_line": None,
        "snapshot_id": 1,
        "match_id": None,
        "observed_at": "2026-09-07T12:00:00+00:00",
        "kickoff_utc": "2026-09-07T16:30:00Z",
    }
    row.update(kw)
    res = None if scores is None else {"home_score": scores[0], "away_score": scores[1]}
    return build_observation(row, res, {"competition": "Liga", "kickoff_utc": row["kickoff_utc"]})


def test_not_ready_when_zero_settled():
    rows = [_obs(None), _obs(None, outcome_id="102", outcome_name_official="X")]
    r = assess_readiness(rows, {"finished_matches": 416, "unique_teams": 771, "kickoffs": []})
    assert r["state"] == NOT_READY
    assert r["metrics"]["settled_non_void"] == 0
    assert r["model_probability"] is None
    assert r["ev"] is None


def test_evaluation_updates_when_settled():
    before = evaluate([_obs(None)])
    after = evaluate([_obs((2, 1))])
    assert before["UNKNOWN"] == 1
    assert after["WON"] == 1


def test_temporal_and_walk_forward():
    t = temporal_from_dates(["2026-09-05T12:00:00Z", "2026-09-09T12:00:00Z"])
    assert t["distinct_days"] == 2
    wf = walk_forward_possible(2, 0)
    assert wf["possible"] is False
    assert wf["random_split"] is False


def test_imbalance_flag():
    rows = [_obs((2, 1)) for _ in range(20)]
    r = assess_readiness(rows, {})
    assert "OUTCOME_IMBALANCE" in r["warnings"] or r["metrics"]["resolved_lost"] == 0


def test_product_line_distinct():
    o = _obs((3, 0), market_id="1010", market_type="totals",
             market_name_official="Over Under Full Time",
             outcome_name_official="Over", catalog_handicap=2.5)
    assert o["product_line"] == 2.5
    assert o["fixture_line"] is None


def test_current_db_not_ready_no_writes():
    import sqlite3
    c = sqlite3.connect(str(ROOT / "data" / "vertice.db"))
    n = c.execute("select count(*) from odds_snapshots").fetchone()[0]
    from engine.readiness import current_readiness
    r = current_readiness()
    assert r["state"] == NOT_READY
    assert r["metrics"]["settled_non_void"] == 0
    assert c.execute("select count(*) from odds_snapshots").fetchone()[0] == n
    c.close()

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "v044.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T15:00:00Z','UPCOMING','t','t')"""
    )
    conn.commit()
    conn.close()
    return dbmod


def _row(fid, market, outcome, price, extra=None):
    d = {
        "provider_code": "oddspapi",
        "provider_event_id": fid,
        "bookmaker": "betano",
        "market_code": market,
        "market_name": None,
        "selection": outcome,
        "outcome_id": outcome,
        "line": None,
        "decimal_odds": price,
        "raw_odds": str(price),
        "phase": "PREMATCH",
        "data_status": "REAL",
        "source_updated_at": "t0",
        "observed_at": "t1",
        "bookmaker_market_id": "bm-" + market,
        "bookmaker_outcome_id": "bo-" + outcome,
    }
    if extra:
        d.update(extra)
    return d


def test_snapshot_id_exact_link(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_catalog, persist_normalized_v043
    persist_catalog([{
        "market_id": "101",
        "market_name": "Full Time Result",
        "market_type": "1x2",
        "period": "fulltime",
        "player_prop": False,
        "catalog_handicap": 0,
        "outcomes": [
            {"outcome_id": "101", "outcome_name": "1"},
            {"outcome_id": "102", "outcome_name": "X"},
        ],
    }], provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at="t")
    rows = [
        _row("fxA", "101", "101", 2.1),
        _row("fxA", "101", "102", 3.2),
        _row("fxA", "1016", "1016", 1.9),
    ]
    n = persist_odds_rows(rows, 11, {"fxA": 1})
    assert n == 3
    assert all(r.get("snapshot_id") for r in rows)
    persist_normalized_v043(rows, 11, {"fxA": 1})
    conn = dbmod.get_conn()
    v = list(conn.execute("select * from odds_normalized_v043 order by id"))
    assert len(v) == 3
    assert all(r["snapshot_id"] is not None for r in v)
    for r in v:
        snap = dict(conn.execute("select * from odds_snapshots where id=?", (r["snapshot_id"],)).fetchone())
        assert snap["id"] == r["snapshot_id"]
        assert snap["scan_id"] == r["scan_id"] == 11
        assert snap["provider_event_id"] == r["provider_event_id"]
        assert snap["market_code"] == r["market_id"]
        assert str(snap["selection"]) == str(r["outcome_id"])
        assert snap["decimal_odds"] == r["decimal_odds"]
    ids = [r["snapshot_id"] for r in v]
    assert len(set(ids)) == 3


def test_historical_snapshots_untouched(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    persist_odds_rows([_row("fxA", "101", "101", 2.1)], 7, {"fxA": 1})
    persist_odds_rows([_row("fxA", "101", "102", 3.2)], 11, {"fxA": 1})
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from odds_snapshots where scan_id=7").fetchone()[0] == 1
    assert conn.execute("select decimal_odds from odds_snapshots where scan_id=7").fetchone()[0] == 2.1

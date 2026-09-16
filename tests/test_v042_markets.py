import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

CATALOG = [
    {
        "market_id": "10228",
        "market_name": "Over Under Team 1",
        "market_type": "teamtotals-team1",
        "period": "fulltime",
        "player_prop": False,
        "catalog_handicap": 2.5,
        "outcomes": [
            {"outcome_id": "10228", "outcome_name": "Over"},
            {"outcome_id": "10229", "outcome_name": "Under"},
        ],
    },
    {
        "market_id": "10871",
        "market_name": "Corners - Handicap",
        "market_type": "spread-corners",
        "period": "fulltime",
        "player_prop": False,
        "catalog_handicap": -1.5,
        "outcomes": [
            {"outcome_id": "10871", "outcome_name": "1"},
            {"outcome_id": "10872", "outcome_name": "2"},
        ],
    },
]


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "v042.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def test_persist_catalog_and_freshness(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_catalog import catalog_is_fresh, persist_catalog
    assert catalog_is_fresh() is False
    from engine.timeutil import now_utc_iso
    n = persist_catalog(CATALOG, provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at=now_utc_iso())
    assert n == 2
    assert catalog_is_fresh() is True
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from odds_market_catalog").fetchone()[0] == 2
    assert conn.execute("select count(*) from odds_market_outcomes").fetchone()[0] == 4


def test_map_known_and_unknown(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_catalog import persist_catalog, map_scan_snapshots
    persist_catalog(CATALOG, provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at="t")
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T14:30:00Z','UPCOMING','t','t')"""
    )
    conn.execute(
        """INSERT INTO odds_snapshots
           (id, scan_id, match_id, provider_code, provider_event_id, bookmaker, market_code,
            market_name, selection, line, decimal_odds, raw_odds, phase, data_status, observed_at)
           VALUES (1,9,1,'oddspapi','fx1','betano','10228',NULL,'10228',1.5,1.09,'1.09','PREMATCH','REAL','t1')"""
    )
    conn.execute(
        """INSERT INTO odds_snapshots
           (id, scan_id, match_id, provider_code, provider_event_id, bookmaker, market_code,
            market_name, selection, line, decimal_odds, raw_odds, phase, data_status, observed_at)
           VALUES (2,9,1,'oddspapi','fx1','betano','999999',NULL,'unlabeled',NULL,2.0,'2.0','PREMATCH','REAL','t1')"""
    )
    conn.commit()
    conn.close()
    stats = map_scan_snapshots(9)
    assert stats["mapped"] == 1
    assert stats["unmapped"] == 1
    conn = dbmod.get_conn()
    mapped = dict(conn.execute("select * from odds_mapped_snapshots").fetchone())
    assert mapped["market_name_official"] == "Over Under Team 1"
    assert mapped["period_official"] == "fulltime"
    assert mapped["phase"] == "PREMATCH"
    assert mapped["fixture_line"] == 1.5
    assert mapped["catalog_handicap"] == 2.5
    assert mapped["fixture_line"] != mapped["catalog_handicap"]
    assert mapped["outcome_name_official"] == "Over"
    assert mapped["decimal_odds"] == 1.09
    assert conn.execute("select reason from odds_unmapped_markets").fetchone()[0] == "catalog_miss"
    # raw snapshots intact
    assert conn.execute("select count(*) from odds_snapshots").fetchone()[0] == 2
    assert conn.execute("select market_name from odds_snapshots where market_code='10228'").fetchone()[0] is None


def test_two_lines_same_market(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_catalog import persist_catalog, map_scan_snapshots
    persist_catalog(CATALOG, provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at="t")
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T14:30:00Z','UPCOMING','t','t')"""
    )
    for i, line in enumerate((2.5, 3.5), start=1):
        conn.execute(
            """INSERT INTO odds_snapshots
               (scan_id, match_id, provider_code, provider_event_id, bookmaker, market_code,
                market_name, selection, line, decimal_odds, raw_odds, phase, data_status, observed_at)
               VALUES (9,1,'oddspapi','fx1','betano','10228',NULL,'10228',?,?,?,'PREMATCH','REAL','t')""",
            (line, 1.8 + i * 0.1, str(1.8 + i * 0.1)),
        )
    conn.commit()
    conn.close()
    stats = map_scan_snapshots(9)
    assert stats["mapped"] == 2
    conn = dbmod.get_conn()
    lines = {r[0] for r in conn.execute("select fixture_line from odds_mapped_snapshots")}
    assert lines == {2.5, 3.5}


def test_parse_markets_no_invented_names():
    from providers.odds.oddspapi import OddsPapiProvider

    class Fake(OddsPapiProvider):
        def _get(self, path, params):
            assert path == "/markets"
            return [{
                "marketId": 10228,
                "marketName": "Over Under Team 1",
                "marketType": "teamtotals-team1",
                "period": "fulltime",
                "playerProp": False,
                "handicap": 2.5,
                "outcomes": [{"outcomeId": 10228, "outcomeName": "Over"}],
            }]

    rows = Fake(api_key="x").fetch_markets(10)
    assert rows[0]["market_name"] == "Over Under Team 1"
    assert rows[0]["catalog_handicap"] == 2.5


def test_catalog_failure_does_not_drop_raw(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T14:30:00Z','UPCOMING','t','t')"""
    )
    conn.commit()
    conn.close()
    n = persist_odds_rows([{
        "provider_event_id": "fx",
        "bookmaker": "betano",
        "market_code": "10228",
        "market_name": None,
        "selection": "unlabeled",
        "line": None,
        "decimal_odds": 1.9,
        "raw_odds": "1.9",
        "phase": "PREMATCH",
        "data_status": "REAL",
        "source_updated_at": "t0",
        "observed_at": "t1",
        "provider_code": "oddspapi",
    }], 1, {"fx": 1})
    assert n == 1
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from odds_snapshots").fetchone()[0] == 1

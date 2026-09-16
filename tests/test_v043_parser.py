import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from providers.odds.oddspapi import flatten_bookmaker_odds, parse_market_outcomes


FT_RESULT = {
    "bookmakerMarketId": "2923099116",
    "marketActive": True,
    "outcomes": {
        "101": {"players": {"0": {"playerName": None, "price": 2.1, "bookmakerOutcomeId": "b101"}}},
        "102": {"players": {"0": {"playerName": None, "price": 3.15, "bookmakerOutcomeId": "b102"}}},
        "103": {"players": {"0": {"playerName": None, "price": 3.95, "bookmakerOutcomeId": "b103"}}},
    },
}
OU = {
    "bookmakerMarketId": "2923099418",
    "marketActive": True,
    "outcomes": {
        "1016": {"players": {"0": {"playerName": None, "price": 13.0}}},
        "1017": {"players": {"0": {"playerName": None, "price": 1.03}}},
    },
}
SHOTS = {
    "bookmakerMarketId": "2940400926",
    "marketActive": True,
    "outcomes": {
        "10744": {"players": {
            "2419011": {"playerName": "Kofler, Raphael", "price": 2.12},
            "2735949": {"playerName": "Esposito, Sebastian", "price": 2.57},
        }},
        "10745": {"players": {
            "1712603": {"playerName": "N’Dri, Konan", "price": 1.42},
        }},
    },
}


def test_parse_1x2_outcome_ids():
    rows = parse_market_outcomes("101", FT_RESULT)
    oids = {r["outcome_id"] for r in rows}
    assert oids == {"101", "102", "103"}
    prices = {r["outcome_id"]: r["price"] for r in rows}
    assert prices["101"] == 2.1
    assert all(r["player_id"] is None for r in rows)
    assert all(r["player_name"] is None for r in rows)
    assert all(r["line"] is None for r in rows)
    assert rows[0]["bookmaker_market_id"] == "2923099116"
    assert {r["bookmaker_outcome_id"] for r in rows} == {"b101", "b102", "b103"}


def test_parse_over_under():
    rows = parse_market_outcomes("1016", OU)
    assert {r["outcome_id"] for r in rows} == {"1016", "1017"}
    assert all(r["line"] is None for r in rows)


def test_parse_player_shots_separates_ids():
    rows = parse_market_outcomes("10743", SHOTS)
    assert len(rows) == 3
    assert {r["outcome_id"] for r in rows} == {"10744", "10745"}
    assert {r["player_id"] for r in rows} == {"2419011", "2735949", "1712603"}
    names = {r["player_name"] for r in rows}
    assert "Kofler, Raphael" in names
    assert all(r["player_name"] != r["outcome_id"] for r in rows)
    assert all(r["player_id"] != r["outcome_id"] for r in rows)


def test_flatten_payload_scan8_shape():
    payload = {
        "fixtureId": "id1000002371945228",
        "statusId": 0,
        "updatedAt": "t",
        "bookmakerOdds": {"betano": {"markets": {"101": FT_RESULT, "10743": SHOTS}}},
    }
    rows = flatten_bookmaker_odds(payload, "now", "betano")
    ones = [r for r in rows if r["market_code"] == "101"]
    assert len(ones) == 3
    shots = [r for r in rows if r["market_code"] == "10743"]
    assert len(shots) == 3
    assert shots[0]["player_name"] in {"Kofler, Raphael", "Esposito, Sebastian", "N’Dri, Konan"}
    assert shots[0]["selection"] in {"10744", "10745"}


def test_normalize_catalog_and_null_line(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "v043.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
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
            {"outcome_id": "103", "outcome_name": "2"},
        ],
    }], provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at="t")
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T15:00:00Z','UPCOMING','t','t')"""
    )
    conn.execute(
        """INSERT INTO odds_snapshots (id,scan_id,match_id,provider_code,provider_event_id,bookmaker,market_code,
           market_name,selection,line,decimal_odds,raw_odds,phase,data_status,observed_at)
           VALUES (99,8,1,'oddspapi','fx','betano','OLD',NULL,'keep',NULL,9.9,'9.9','PREMATCH','REAL','hist')"""
    )
    conn.commit()
    conn.close()
    rows = flatten_bookmaker_odds({
        "fixtureId": "fx", "statusId": 0, "updatedAt": "t",
        "bookmakerOdds": {"betano": {"markets": {"101": FT_RESULT, "999999": OU}}},
    }, "now", "betano")
    stats = persist_normalized_v043(rows, 8, {"fx": 1})
    assert stats["mapped"] >= 3
    conn = dbmod.get_conn()
    n043 = list(conn.execute("select * from odds_normalized_v043 where market_id='101'"))
    assert len(n043) == 3
    names = {r["outcome_name_official"] for r in n043}
    assert names == {"1", "X", "2"}
    assert all(r["fixture_line"] is None for r in n043)
    assert all(r["catalog_handicap"] == 0 for r in n043)
    unknown = conn.execute("select outcome_name_official, mapped from odds_normalized_v043 where market_id='999999'").fetchone()
    assert unknown is not None
    assert unknown[0] is None
    assert unknown[1] == 0
    hist = conn.execute("select selection, decimal_odds from odds_snapshots where id=99").fetchone()
    assert hist[0] == "keep" and hist[1] == 9.9

"""V0.4.6 P0: fixture_line from OddsPapi odds payload, never catalog_handicap."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from providers.odds.oddspapi import flatten_bookmaker_odds, parse_market_outcomes


def _market(mid, outcomes, handicap=None):
    m = {"bookmakerMarketId": f"bm-{mid}", "outcomes": outcomes}
    if handicap is not None:
        m["handicap"] = handicap
    return m


def _payload(markets, fid="fx-1"):
    return {
        "fixtureId": fid,
        "statusId": 0,
        "updatedAt": "t0",
        "bookmakerOdds": {
            "betano": {"slug": "betano", "markets": markets}
        },
    }


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "v046.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def test_ou_points_2_5():
    market = _market("1010", {
        "1010": {"players": {"0": {"price": 1.90, "points": 2.5, "bookmakerOutcomeId": "bo-o"}}},
        "1011": {"players": {"0": {"price": 1.85, "points": 2.5, "bookmakerOutcomeId": "bo-u"}}},
    })
    rows = parse_market_outcomes("1010", market)
    assert {r["line"] for r in rows} == {2.5}


def test_asian_points_neg_025():
    market = _market("1062", {
        "1": {"players": {"0": {"price": 1.87, "points": -0.25}}},
        "2": {"players": {"0": {"price": 1.91, "points": 0.25}}},
    })
    rows = parse_market_outcomes("1062", market)
    assert sorted(r["line"] for r in rows) == [-0.25, 0.25]


def test_team_total_points_05():
    market = _market("10224", {
        "10224": {"players": {"0": {"price": 1.70, "points": 0.5}}},
    })
    assert parse_market_outcomes("10224", market)[0]["line"] == 0.5


def test_1x2_no_line():
    market = _market("101", {
        "101": {"players": {"0": {"price": 2.10}}},
        "102": {"players": {"0": {"price": 3.40}}},
        "103": {"players": {"0": {"price": 3.20}}},
    })
    rows = parse_market_outcomes("101", market)
    assert all(r["line"] is None for r in rows)
    assert len(rows) == 3


def test_totals_missing_line_stays_null():
    market = _market("1010", {
        "1010": {"players": {"0": {"price": 1.90}}},
    })
    assert parse_market_outcomes("1010", market)[0]["line"] is None


def test_catalog_handicap_does_not_leak_into_flatten(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_catalog, persist_normalized_v043
    persist_catalog([{
        "market_id": "1010",
        "market_name": "Over Under Full Time",
        "market_type": "totals",
        "period": "fulltime",
        "player_prop": False,
        "catalog_handicap": 2.5,
        "outcomes": [{"outcome_id": "1010", "outcome_name": "Over"}],
    }], provider_code="oddspapi", sport_key="football", sport_id=10, fetched_at="now")
    payload = _payload({
        "1010": _market("1010", {
            "1010": {"players": {"0": {"price": 1.92}}},
        })
    })
    rows = flatten_bookmaker_odds(payload, "t1", "betano")
    assert rows[0]["line"] is None
    persist_odds_rows(rows, 99, {})
    persist_normalized_v043(rows, 99, {}, provider_code="oddspapi")
    conn = dbmod.get_conn()
    snap = dict(conn.execute("select line from odds_snapshots").fetchone())
    v = dict(conn.execute("select fixture_line, catalog_handicap from odds_normalized_v043").fetchone())
    assert snap["line"] is None
    assert v["fixture_line"] is None
    assert v["catalog_handicap"] == 2.5


def test_snapshot_id_and_unmatched_with_line(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_normalized_v043
    payload = _payload({
        "1010": _market("1010", {
            "1010": {"players": {"0": {"price": 1.88, "points": 2.5}}},
        })
    }, fid="orphan-fx")
    rows = flatten_bookmaker_odds(payload, "t1", "betano")
    persist_odds_rows(rows, 99, {})
    persist_normalized_v043(rows, 99, {}, provider_code="oddspapi")
    conn = dbmod.get_conn()
    snap = dict(conn.execute("select * from odds_snapshots").fetchone())
    v = dict(conn.execute("select * from odds_normalized_v043").fetchone())
    assert snap["match_id"] is None
    assert snap["line"] == 2.5
    assert v["match_id"] is None
    assert v["fixture_line"] == 2.5
    assert v["snapshot_id"] == snap["id"]
    assert v["provider_event_id"] == "orphan-fx"


def test_distinct_market_ids_not_merged():
    payload = _payload({
        "1010": _market("1010", {"1010": {"players": {"0": {"price": 1.80, "points": 2.5}}}}),
        "1012": _market("1012", {"1012": {"players": {"0": {"price": 1.95, "points": 3.5}}}}),
    })
    rows = flatten_bookmaker_odds(payload, "t1", "betano")
    codes = sorted(r["market_code"] for r in rows)
    assert codes == ["1010", "1012"]
    by = {r["market_code"]: r["line"] for r in rows}
    assert by["1010"] == 2.5 and by["1012"] == 3.5

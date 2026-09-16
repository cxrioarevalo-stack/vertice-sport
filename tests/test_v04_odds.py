import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def test_parse_rejects_invalid_odds():
    from providers.odds.odds_api_io import parse_decimal
    assert parse_decimal("1.85") == 1.85
    assert parse_decimal(2) == 2.0
    assert parse_decimal("1.00") is None
    assert parse_decimal(1) is None
    assert parse_decimal(0) is None
    assert parse_decimal("abc") is None
    assert parse_decimal(None) is None


def test_flatten_markets_and_bookmaker():
    from providers.odds.odds_api_io import flatten_bookmaker_markets
    event = {"id": 9, "home": "A", "away": "B", "date": "2026-09-05T15:00:00Z", "status": "pending"}
    markets = [{
        "name": "ML",
        "updatedAt": "2026-09-05T12:00:00Z",
        "odds": [{"home": "1.72", "draw": "3.80", "away": "4.90"}],
    }, {
        "name": "Totals",
        "odds": [{"total": 2.5, "over": "1.85", "under": "1.95"}],
    }, {
        "name": "ML",
        "odds": [{"home": "1.00", "away": "bad"}],
    }]
    rows = flatten_bookmaker_markets(event, "Betano", markets, "PREMATCH", "t")
    books = {r["bookmaker"] for r in rows}
    assert books == {"Betano"}
    codes = {r["market_code"] for r in rows}
    assert "1x2" in codes and "ou" in codes
    assert all(r["decimal_odds"] > 1.0 for r in rows)
    assert all(r["phase"] == "PREMATCH" for r in rows)
    assert all(r["data_status"] == "REAL" for r in rows)


def test_prematch_live_not_mixed():
    from providers.odds.odds_api_io import flatten_bookmaker_markets
    ev = {"id": 1, "home": "A", "away": "B"}
    mk = [{"name": "ML", "odds": [{"home": "1.5", "away": "5.0", "draw": "4.0"}]}]
    pre = flatten_bookmaker_markets(ev, "Betano", mk, "PREMATCH", "t1")
    live = flatten_bookmaker_markets(ev, "Betano", mk, "LIVE", "t2")
    assert pre[0]["phase"] != live[0]["phase"]


def test_event_match_and_reject():
    from engine.odds_match import match_event
    bbc = {"home_team": "Manchester City", "away_team": "Coventry City", "kickoff_utc": "2026-09-05T14:00:00Z"}
    ok, c, r = match_event(bbc, {"home_team": "Man City", "away_team": "Coventry", "kickoff_utc": "2026-09-05T14:00:00Z"})
    assert ok and c >= 0.8
    bad, *_ = match_event(bbc, {"home_team": "Arsenal", "away_team": "Chelsea", "kickoff_utc": "2026-09-05T14:00:00Z"})
    assert bad is False
    rev, *_ = match_event(bbc, {"home_team": "Coventry City", "away_team": "Manchester City", "kickoff_utc": "2026-09-05T14:00:00Z"})
    assert rev is False


def test_low_confidence_unmatched_kickoff():
    from engine.odds_match import match_event
    bbc = {"home_team": "Hull City", "away_team": "Aston Villa", "kickoff_utc": "2026-09-05T16:30:00Z"}
    ok, _, reason = match_event(bbc, {"home_team": "Hull City", "away_team": "Aston Villa", "kickoff_utc": "2026-09-06T16:30:00Z"})
    assert ok is False
    assert "kickoff" in reason


def test_missing_key_and_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "o.db"))
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.odds_ingest import ingest_odds_for_matches
    st = ingest_odds_for_matches([], 1)
    assert st["odds_available"] is False
    assert st["error_kind"] == "missing_key"


def test_persist_snapshots_history(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "odds.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.odds_store import persist_odds_rows, odds_for_match
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute("""INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
                    VALUES (1,'football',1,2,'bbc','e1','2026-09-05T12:00:00Z','UPCOMING','t','t')""")
    conn.commit(); conn.close()
    row = {
        "provider_event_id": "9", "bookmaker": "Betano", "market_code": "1x2",
        "market_name": "1X2", "selection": "Home", "line": None,
        "decimal_odds": 1.72, "raw_odds": "1.72", "phase": "PREMATCH",
        "data_status": "REAL", "source_updated_at": "t0", "observed_at": "t1",
        "provider_code": "odds_api_io",
    }
    persist_odds_rows([row], 1, {"9": 1})
    row2 = dict(row, decimal_odds=1.80, observed_at="t2", raw_odds="1.80")
    persist_odds_rows([row2], 2, {"9": 1})
    snaps = odds_for_match(1)
    assert len(snaps) == 2
    assert {s["decimal_odds"] for s in snaps} == {1.72, 1.80}


def test_bbc_survives_odds_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "mix.db"))
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.store import upsert_matches
    from engine.odds_ingest import ingest_odds_for_matches
    conn = dbmod.get_conn()
    sid = conn.execute("INSERT INTO scan_runs (started_at,date_local,status,sport_key) VALUES ('t','2026-09-05','P','football')").lastrowid
    conn.commit(); conn.close()
    m = {
        "external_id": "bbc-1", "competition": "PL", "kickoff_utc": "2026-09-05T15:00:00Z",
        "status": "FINISHED", "home_team": "A", "away_team": "B",
        "home_score": "1", "away_score": "0", "fetched_at": "t",
    }
    r = upsert_matches([m], sid)
    assert r["new"] == 1
    st = ingest_odds_for_matches([{**m, "match_id": r["match_ids"][0]}], sid)
    assert st["odds_available"] is False
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from matches").fetchone()[0] == 1


def test_multi_batches_not_per_match():
    from providers.odds.odds_api_io import OddsApiIoProvider, OddsProviderError

    class Fake(OddsApiIoProvider):
        def __init__(self):
            super().__init__(api_key="k", bookmakers="Betano")
            self.calls = []
        def _get(self, path, params):
            self.calls.append((path, params))
            if path == "/odds/multi":
                ids = params["eventIds"].split(",")
                return [{"id": i, "status": "pending", "bookmakers": {"Betano": [{"name": "ML", "odds": [{"home": "1.5", "draw": "4.0", "away": "6.0"}]}]}} for i in ids]
            raise OddsProviderError("should not hit single", kind="http")

    p = Fake()
    rows = p.fetch_odds([str(i) for i in range(12)], "t")
    multi = [c for c in p.calls if c[0] == "/odds/multi"]
    single = [c for c in p.calls if c[0] == "/odds"]
    assert len(multi) == 2  # 10 + 2
    assert single == []
    assert len(rows) >= 12

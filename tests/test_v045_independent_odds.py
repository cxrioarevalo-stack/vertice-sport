import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "v045.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'Home')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'Away')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','bbc-1','2026-09-09T19:00:00Z','UPCOMING','t','t')"""
    )
    conn.commit()
    conn.close()
    return dbmod


def _row(fid, price=1.9, market="101", outcome="101"):
    return {
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
    }


def test_matched_fixture_gets_match_id_and_snapshot(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_normalized_v043
    rows = [_row("fx-match", 2.1)]
    n = persist_odds_rows(rows, 12, {"fx-match": 1})
    assert n == 1
    persist_normalized_v043(rows, 12, {"fx-match": 1})
    conn = dbmod.get_conn()
    snap = dict(conn.execute("select * from odds_snapshots").fetchone())
    v = dict(conn.execute("select * from odds_normalized_v043").fetchone())
    assert snap["match_id"] == 1
    assert v["match_id"] == 1
    assert v["snapshot_id"] == snap["id"]
    assert v["provider_event_id"] == "fx-match"
    assert v["decimal_odds"] == 2.1


def test_unmatched_fixture_persists_with_null_match_id(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_normalized_v043
    rows = [_row("fx-only", 3.5)]
    n = persist_odds_rows(rows, 12, {})
    assert n == 1
    persist_normalized_v043(rows, 12, {})
    conn = dbmod.get_conn()
    snap = dict(conn.execute("select * from odds_snapshots").fetchone())
    v = dict(conn.execute("select * from odds_normalized_v043").fetchone())
    assert snap["match_id"] is None
    assert v["match_id"] is None
    assert v["snapshot_id"] == snap["id"]
    assert snap["provider_event_id"] == "fx-only"
    assert conn.execute("select count(*) from odds_event_map").fetchone()[0] == 0


def test_mixed_matched_and_unmatched(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_odds_rows
    from engine.odds_catalog import persist_normalized_v043
    rows = [_row("fx-a", 1.8), _row("fx-b", 2.2)]
    persist_odds_rows(rows, 12, {"fx-a": 1})
    persist_normalized_v043(rows, 12, {"fx-a": 1})
    conn = dbmod.get_conn()
    by = {r["provider_event_id"]: dict(r) for r in conn.execute("select * from odds_snapshots")}
    assert by["fx-a"]["match_id"] == 1
    assert by["fx-b"]["match_id"] is None
    assert conn.execute("select count(*) from odds_normalized_v043").fetchone()[0] == 2


def test_provider_event_upsert_stable(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_provider_events
    ev = {
        "provider_code": "oddspapi",
        "provider_event_id": "idX",
        "home_team": "A",
        "away_team": "B",
        "competition": "L",
        "kickoff_utc": "2026-09-09T19:00:00Z",
        "raw_status": "0",
    }
    persist_provider_events([ev], "t1")
    persist_provider_events([{**ev, "home_team": "A2"}], "t2")
    conn = dbmod.get_conn()
    n = conn.execute("select count(*) from odds_provider_events").fetchone()[0]
    home = conn.execute("select home_team, fetched_at from odds_provider_events").fetchone()
    assert n == 1 and home[0] == "A2" and home[1] == "t2"


def test_max_event_calls_respected(monkeypatch):
    monkeypatch.setenv("ODDSPAPI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ODDS_MAX_EVENT_CALLS", "2")
    import importlib
    import providers.odds.oddspapi as op
    importlib.reload(op)
    calls = []

    def fake_get(self, path, params):
        calls.append(params.get("fixtureId"))
        return {"fixtureId": params.get("fixtureId"), "statusId": 0, "bookmakerOdds": {}}

    monkeypatch.setattr(op.OddsPapiProvider, "_get", fake_get)
    p = op.OddsPapiProvider(api_key="test-key-not-real")
    p.fetch_odds(["a", "b", "c", "d"], "now")
    assert calls == ["a", "b"]


def test_ingest_fetches_odds_without_bbc_match(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    monkeypatch.setenv("ODDS_PROVIDER", "oddspapi")
    monkeypatch.setenv("ODDSPAPI_API_KEY", "test-key-not-real")
    from providers.odds.base import OddsProviderError
    import engine.odds_ingest as ingest

    class Fake:
        code = "oddspapi"
        display_name = "OddsPapi v4"
        bookmakers = "betano"
        api_key = "test-key-not-real"
        requests = 2
        raw_captures = []
        fixture_errors = []
        def configured(self):
            return True
        def fetch_events(self, a, b):
            return [{
                "provider_code": "oddspapi",
                "provider_event_id": "fx-orphan",
                "home_team": "Alpha",
                "away_team": "Beta",
                "competition": "Cup",
                "kickoff_utc": "2026-09-09T19:00:00Z",
                "raw_status": "0",
            }]
        def fetch_odds(self, ids, fetched_at):
            assert ids == ["fx-orphan"]
            return [_row("fx-orphan", 1.55)]

    import engine.odds_ingest as mod
    monkeypatch.setattr(mod, "get_odds_provider", lambda: Fake())
    status = ingest.ingest_odds_for_matches([], scan_id=12)
    assert status["events"] == 1
    assert status["matched"] == 0
    assert status["odds_rows"] == 1
    import db as dbmod
    conn = dbmod.get_conn()
    snap = dict(conn.execute("select * from odds_snapshots").fetchone())
    assert snap["match_id"] is None
    assert snap["decimal_odds"] == 1.55
    assert conn.execute("select count(*) from odds_event_map").fetchone()[0] == 0

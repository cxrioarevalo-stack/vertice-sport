import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


SAMPLE_FIXTURES = [
    {
        "fixtureId": "id1002709272053608",
        "participant1Name": "Puntarenas FC",
        "participant2Name": "CS Cartagines",
        "tournamentName": "Primera Division, Apertura",
        "startTime": "2026-09-06T22:00:00.000Z",
        "statusId": 0,
        "hasOdds": True,
        "sportId": 10,
    }
]

SAMPLE_ODDS = {
    "fixtureId": "id1002709272053608",
    "hasOdds": True,
    "statusId": 0,
    "updatedAt": "2026-09-04T23:14:32.524Z",
    "startTime": "2026-09-06T22:00:00.000Z",
    "bookmakerOdds": {
        "betano": {
            "bookmakerIsActive": True,
            "suspended": False,
            "markets": {
                "1010": {"a": {"price": 1.9}, "b": {"price": 1.8}},
                "102041": {
                    "x": {"price": 3.35},
                    "y": {"price": 1.95},
                    "z": {"price": 3.1},
                },
            },
        }
    },
}


def test_no_key():
    from providers.odds.oddspapi import OddsPapiProvider
    p = OddsPapiProvider(api_key="")
    assert p.configured() is False


def test_parse_fixtures():
    from providers.odds.oddspapi import OddsPapiProvider

    class Fake(OddsPapiProvider):
        def _get(self, path, params):
            assert path == "/fixtures"
            assert params["sportId"] == 10
            assert params["bookmakers"] == "betano"
            return SAMPLE_FIXTURES

    ev = Fake(api_key="x", bookmakers="betano").fetch_events("2026-09-06", "2026-09-06")
    assert ev[0]["provider_event_id"] == "id1002709272053608"
    assert ev[0]["home_team"] == "Puntarenas FC"


def test_flatten_betano_numeric_markets():
    from providers.odds.oddspapi import flatten_bookmaker_odds
    rows = flatten_bookmaker_odds(SAMPLE_ODDS, "t", "betano")
    assert rows
    assert all(r["bookmaker_slug"] == "betano" for r in rows)
    assert all(r["data_status"] == "REAL" for r in rows)
    assert all(r["decimal_odds"] > 1.0 for r in rows)
    assert all(r["market_name"] is None for r in rows)
    assert all(r["mapping_needed"] for r in rows)
    assert {r["market_code"] for r in rows} == {"1010", "102041"}


def test_rejects_other_bookmaker_and_bad_prices():
    from providers.odds.oddspapi import flatten_bookmaker_odds
    payload = {
        "fixtureId": "x",
        "statusId": 0,
        "bookmakerOdds": {
            "pinnacle": {"markets": {"1": {"p": {"price": 2.0}}}},
            "betano": {"markets": {"1": {"p": {"price": 1.0}}}},
        },
    }
    assert flatten_bookmaker_odds(payload, "t", "betano") == []


def test_malformed_odds():
    from providers.odds.oddspapi import flatten_bookmaker_odds
    assert flatten_bookmaker_odds({}, "t", "betano") == []
    assert flatten_bookmaker_odds({"bookmakerOdds": None}, "t", "betano") == []


def test_http_errors(monkeypatch):
    from providers.odds.oddspapi import OddsPapiProvider
    from providers.odds.base import OddsProviderError

    class Boom(OddsPapiProvider):
        def _get(self, path, params):
            raise OddsProviderError("HTTP 500", kind="http", http_status=500)

    try:
        Boom(api_key="x").fetch_events("2026-09-06", "2026-09-06")
        assert False
    except OddsProviderError as e:
        assert e.http_status == 500


def test_factory_oddspapi(monkeypatch):
    monkeypatch.setenv("ODDS_PROVIDER", "oddspapi")
    from providers.odds.base import get_odds_provider
    p = get_odds_provider()
    assert p.code == "oddspapi"


def test_ingest_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "a.db"))
    monkeypatch.setenv("ODDS_PROVIDER", "oddspapi")
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.odds_ingest import ingest_odds_for_matches
    st = ingest_odds_for_matches([], 1)
    assert st["provider_status"] == "NOT_CONFIGURED"
    assert st["odds_available"] is False


def test_bbc_survives_oddspapi_error(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "b.db"))
    monkeypatch.setenv("ODDS_PROVIDER", "oddspapi")
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.store import upsert_matches
    from engine.odds_ingest import ingest_odds_for_matches
    conn = dbmod.get_conn()
    sid = conn.execute(
        "INSERT INTO scan_runs (started_at,date_local,status,sport_key) VALUES ('t','2026-09-06','P','football')"
    ).lastrowid
    conn.commit()
    conn.close()
    m = {
        "external_id": "bbc-x",
        "competition": "PL",
        "kickoff_utc": "2026-09-06T22:00:00Z",
        "status": "UPCOMING",
        "home_team": "Puntarenas FC",
        "away_team": "CS Cartagines",
        "home_score": None,
        "away_score": None,
        "fetched_at": "t",
    }
    r = upsert_matches([m], sid)
    assert r["new"] == 1
    st = ingest_odds_for_matches([{**m, "match_id": r["match_ids"][0]}], sid)
    assert st["odds_available"] is False
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from matches").fetchone()[0] == 1


def test_snapshots_append_only(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "c.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.odds_store import persist_odds_rows, odds_for_match
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'A')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'B')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-06T22:00:00Z','UPCOMING','t','t')"""
    )
    conn.commit()
    conn.close()
    row = {
        "provider_event_id": "id1",
        "bookmaker": "betano",
        "market_code": "1010",
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
    }
    persist_odds_rows([row], 1, {"id1": 1})
    persist_odds_rows([{**row, "decimal_odds": 2.0, "observed_at": "t2"}], 2, {"id1": 1})
    snaps = odds_for_match(1)
    assert len(snaps) == 2


def test_match_mapping_conservative():
    from engine.odds_match import match_event
    bbc = {
        "home_team": "Puntarenas FC",
        "away_team": "CS Cartagines",
        "kickoff_utc": "2026-09-06T22:00:00.000Z",
    }
    ok, c, _ = match_event(bbc, {
        "home_team": "Puntarenas FC",
        "away_team": "CS Cartagines",
        "kickoff_utc": "2026-09-06T22:00:00.000Z",
    })
    assert ok and c >= 0.8
    bad, *_ = match_event(bbc, {
        "home_team": "Saprissa",
        "away_team": "Alajuelense",
        "kickoff_utc": "2026-09-06T22:00:00.000Z",
    })
    assert bad is False


class _Resp:
    def __init__(self, status, text="err", json_data=None):
        self.status_code = status
        self.text = text
        self._json = json_data
    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _Client:
    def __init__(self, resp):
        self.resp = resp
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        assert "apiKey" in (params or {})
        return self.resp if not callable(self.resp) else self.resp(url, params)


def test_status_classification(monkeypatch):
    from providers.odds import oddspapi
    from providers.odds.oddspapi import OddsPapiProvider
    from providers.odds.base import OddsProviderError

    cases = [
        (401, "auth"),
        (403, "forbidden"),
        (404, "client"),
        (429, "rate_limit"),
        (500, "server"),
    ]
    p = OddsPapiProvider(api_key="SUPERSECRETKEY")
    for status, kind in cases:
        monkeypatch.setattr(oddspapi.httpx, "Client", lambda timeout=None: _Client(_Resp(status, f"nope SUPERSECRETKEY {status}")))
        try:
            p._get("/odds", {"fixtureId": "id1"})
            assert False, status
        except OddsProviderError as e:
            assert e.kind == kind
            assert e.http_status == status
            assert "SUPERSECRETKEY" not in str(e)
            assert "auth failed" not in str(e).lower() or status == 401


def test_malformed_json(monkeypatch):
    from providers.odds import oddspapi
    from providers.odds.oddspapi import OddsPapiProvider
    from providers.odds.base import OddsProviderError
    monkeypatch.setattr(oddspapi.httpx, "Client", lambda timeout=None: _Client(_Resp(200, "not-json", None)))
    p = OddsPapiProvider(api_key="SUPERSECRETKEY")
    try:
        p._get("/odds", {"fixtureId": "id1"})
        assert False
    except OddsProviderError as e:
        assert e.kind == "parse"
        assert "SUPERSECRETKEY" not in str(e)


def test_first_403_second_ok(monkeypatch):
    from providers.odds.oddspapi import OddsPapiProvider
    from providers.odds.base import OddsProviderError
    p = OddsPapiProvider(api_key="SUPERSECRETKEY")
    seen = []

    def fake_get(path, params):
        seen.append(params.get("fixtureId"))
        if params.get("fixtureId") == "bad":
            raise OddsProviderError("HTTP 403 forbidden: denied", kind="forbidden", http_status=403)
        return {
            "fixtureId": params.get("fixtureId"),
            "statusId": 0,
            "updatedAt": "t",
            "bookmakerOdds": {"betano": {"markets": {"1010": {"a": {"price": 1.91}}}}},
        }

    p._get = fake_get
    monkeypatch.setattr("providers.odds.oddspapi.time.sleep", lambda s: None)
    rows = p.fetch_odds(["bad", "good"], "now")
    assert seen == ["bad", "good"]
    assert len(rows) >= 1
    assert rows[0]["decimal_odds"] == 1.91
    assert p.fixture_errors[0]["kind"] == "forbidden"
    assert p.fixture_errors[0]["fixture_id"] == "bad"
    blob = str(p.fixture_errors)
    assert "SUPERSECRETKEY" not in blob

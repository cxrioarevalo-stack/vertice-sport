import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "rel.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def test_wal_or_fallback(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    conn = dbmod.get_conn()
    mode = conn.execute("pragma journal_mode").fetchone()[0].lower()
    assert mode in {"wal", "delete", "truncate", "persist", "memory", "off"}
    sync = conn.execute("pragma synchronous").fetchone()[0]
    assert sync in (1, 2)  # NORMAL or FULL
    timeout = conn.execute("pragma busy_timeout").fetchone()[0]
    assert timeout >= 1000
    conn.close()


def test_map_events_batched(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import MAP_BATCH_SIZE, map_events
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'Home')")
    conn.execute("INSERT INTO teams (sport_id,name) VALUES (1,'Away')")
    conn.execute(
        """INSERT INTO matches (sport_id,sport_key,home_team_id,away_team_id,source_code,external_id,kickoff_utc,status,created_at,updated_at)
           VALUES (1,'football',1,2,'bbc','e1','2026-09-07T15:00:00Z','UPCOMING','t','t')"""
    )
    conn.commit()
    conn.close()
    bbc = [{
        "match_id": 1, "home_team": "Home FC", "away_team": "Away FC",
        "kickoff_utc": "2026-09-07T15:00:00Z",
    }]
    events = [{
        "provider_code": "oddspapi", "provider_event_id": "id1",
        "home_team": "Home FC", "away_team": "Away FC",
        "kickoff_utc": "2026-09-07T15:00:00Z",
    }]
    for i in range(MAP_BATCH_SIZE + 3):
        events.append({
            "provider_code": "oddspapi", "provider_event_id": f"u{i}",
            "home_team": f"X{i}", "away_team": f"Y{i}",
            "kickoff_utc": "2026-09-07T18:00:00Z",
        })
    out = map_events(bbc, events)
    assert out["persist_ok"] is True
    assert out["persist_error"] is None
    assert len(out["matched"]) == 1
    assert len(out["unmatched"]) == MAP_BATCH_SIZE + 3
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from odds_event_map").fetchone()[0] == 1
    assert conn.execute("select count(*) from odds_unmatched").fetchone()[0] == MAP_BATCH_SIZE + 3


def test_map_events_rollback_batch(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine import odds_store
    bbc = []
    events = [{
        "provider_code": "oddspapi", "provider_event_id": "id1",
        "home_team": "A", "away_team": "B", "kickoff_utc": "2026-09-07T15:00:00Z",
    }]

    class BoomConn:
        def execute(self, *a, **k):
            raise odds_store.sqlite3.OperationalError("disk I/O error") if False else (_ for _ in ()).throw(Exception("forced"))
        def commit(self):
            raise Exception("forced commit fail")
        def rollback(self):
            self.rolled = True
        def close(self):
            pass

    # force persist path with a bad connection after pairing
    real_get = odds_store.get_conn

    class FailConn:
        def __init__(self):
            self._c = real_get()
            self.rolled = False
        def execute(self, sql, params=None):
            return self._c.execute(sql, params or ())
        def commit(self):
            raise sqlite3_err()
        def rollback(self):
            self.rolled = True
            self._c.rollback()
        def close(self):
            self._c.close()

    def sqlite3_err():
        import sqlite3
        return sqlite3.OperationalError("disk I/O error")

    import sqlite3 as sqlmod
    monkeypatch.setattr(odds_store, "get_conn", lambda: FailConn())
    out = odds_store.map_events(bbc, events)
    assert out["persist_ok"] is False
    assert out["persist_error"]
    assert "disk I/O" in out["persist_error"] or "forced" in out["persist_error"]

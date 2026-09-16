import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "pev.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def _ev(i, fetched="t1", home="H"):
    return {
        "provider_code": "oddspapi",
        "provider_event_id": f"id{i}",
        "home_team": home,
        "away_team": "A",
        "competition": "L",
        "kickoff_utc": "2026-09-07T15:00:00Z",
        "raw_status": "0",
    }


def test_multiple_batches_commit_separately(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine import odds_store
    real_get = odds_store.get_conn
    commits = {"n": 0}

    class CountConn:
        def __init__(self):
            self._c = real_get()
        def execute(self, *a, **k):
            return self._c.execute(*a, **k)
        def commit(self):
            commits["n"] += 1
            return self._c.commit()
        def rollback(self):
            return self._c.rollback()
        def close(self):
            return self._c.close()

    monkeypatch.setattr(odds_store, "get_conn", lambda: CountConn())
    odds_store.persist_provider_events([_ev(i) for i in range(51)], "t1")
    assert commits["n"] == 3
    conn = real_get()
    assert conn.execute("select count(*) from odds_provider_events").fetchone()[0] == 51


def test_137_events_no_duplicates(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import PROVIDER_EVENT_BATCH, persist_provider_events
    assert PROVIDER_EVENT_BATCH == 25
    persist_provider_events([_ev(i) for i in range(137)], "t1")
    conn = dbmod.get_conn()
    n = conn.execute("select count(*) from odds_provider_events").fetchone()[0]
    uniq = conn.execute("select count(distinct provider_event_id) from odds_provider_events").fetchone()[0]
    assert n == 137 and uniq == 137
    commits_expected = 137 // 25 + (1 if 137 % 25 else 0)
    assert commits_expected == 6


def test_upsert_updates_existing(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_provider_events
    persist_provider_events([_ev(1, home="Old")], "t1")
    persist_provider_events([_ev(1, home="New")], "t2")
    conn = dbmod.get_conn()
    row = conn.execute("select home_team, fetched_at, count(*) from odds_provider_events").fetchone()
    assert row[0] == "New" and row[1] == "t2" and row[2] == 1


def test_batch_rollback_does_not_corrupt(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine import odds_store
    odds_store.persist_provider_events([_ev(i) for i in range(10)], "t1")
    real_get = odds_store.get_conn

    class Boom:
        def __init__(self):
            self._c = real_get()
        def execute(self, *a, **k):
            raise RuntimeError("forced batch fail")
        def commit(self):
            pass
        def rollback(self):
            self._c.rollback()
        def close(self):
            self._c.close()

    monkeypatch.setattr(odds_store, "get_conn", lambda: Boom())
    try:
        odds_store.persist_provider_events([_ev(i) for i in range(10, 20)], "t2")
    except RuntimeError:
        pass
    monkeypatch.setattr(odds_store, "get_conn", real_get)
    conn = dbmod.get_conn()
    assert conn.execute("select count(*) from odds_provider_events").fetchone()[0] == 10
    assert conn.execute("pragma integrity_check").fetchone()[0] == "ok"

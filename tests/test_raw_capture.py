import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _init(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "cap.db"))
    monkeypatch.setenv("VERTICE_CAPTURE_RAW_ODDS", os.environ.get("VERTICE_CAPTURE_RAW_ODDS", "1"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    return dbmod


def test_sanitize_strips_api_key():
    from engine.odds_store import sanitize_payload
    secret = "super-secret-key-value"
    raw = {
        "fixtureId": "id1",
        "apiKey": secret,
        "bookmakerOdds": {"betano": {"markets": {"101": {"outcomes": {"101": {"price": 1.9}}}}}},
        "url": f"https://api.oddspapi.io/v4/odds?apiKey={secret}",
    }
    clean = sanitize_payload(raw, secret)
    assert "apiKey" not in clean
    blob = json.dumps(clean)
    assert secret not in blob
    assert clean["fixtureId"] == "id1"
    assert clean["bookmakerOdds"]["betano"]["markets"]["101"]["outcomes"]["101"]["price"] == 1.9


def test_persist_and_reload_unchanged(tmp_path, monkeypatch):
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_raw_captures
    secret = "KEY-MUST-NOT-LAND"
    payload = {
        "fixtureId": "id9",
        "apiKey": secret,
        "bookmakerOdds": {"betano": {"markets": {"10228": {"outcomes": {"10228": {"players": {"0": {"price": 1.11, "handicap": 2.5}}}}}}}},
    }
    n = persist_raw_captures([{
        "provider_code": "oddspapi",
        "provider_event_id": "id9",
        "bookmaker": "betano",
        "captured_at": "t",
        "payload": payload,
    }], scan_id=7, secret=secret)
    assert n == 1
    conn = dbmod.get_conn()
    row = conn.execute("select * from odds_raw_captures").fetchone()
    assert row["purpose"] == "debug_raw_odds"
    assert row["provider_event_id"] == "id9"
    stored = json.loads(row["payload_json"])
    assert "apiKey" not in stored
    assert secret not in row["payload_json"]
    assert stored["bookmakerOdds"]["betano"]["markets"]["10228"]["outcomes"]["10228"]["players"]["0"]["price"] == 1.11
    assert stored["bookmakerOdds"]["betano"]["markets"]["10228"]["outcomes"]["10228"]["players"]["0"]["handicap"] == 2.5
    assert conn.execute("select count(*) from odds_snapshots").fetchone()[0] == 0


def test_capture_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_CAPTURE_RAW_ODDS", "0")
    dbmod = _init(tmp_path, monkeypatch)
    from engine.odds_store import persist_raw_captures
    n = persist_raw_captures([{
        "provider_code": "oddspapi",
        "provider_event_id": "id9",
        "bookmaker": "betano",
        "payload": {"fixtureId": "id9"},
    }], 1, secret=None)
    assert n == 0

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("VERTICE_TZ", "America/New_York")


def _bbc_html(payload: dict) -> str:
    inner = json.dumps(payload, ensure_ascii=False)
    wrapped = json.dumps(inner, ensure_ascii=False)
    return f"<html><script>window.__INITIAL_DATA__={wrapped};</script></html>"


def _payload(events, competition="Premier League"):
    return {
        "data": {
            "sport-data-scores-fixtures?x=1": {
                "data": {
                    "eventGroups": [
                        {
                            "displayLabel": competition,
                            "secondaryGroups": [{"events": events}],
                        }
                    ]
                }
            }
        }
    }


def _event(eid, home, away, status, kickoff="2026-09-05T16:30:00Z", score_h=None, score_a=None, minute=None):
    ev = {
        "id": eid,
        "urn": f"urn:bbc:{eid}",
        "status": status,
        "startDateTime": kickoff,
        "time": {"displayTimeUK": "17:30"},
        "home": {"fullName": home, "score": score_h},
        "away": {"fullName": away, "score": score_a},
    }
    if minute:
        ev["periodLabel"] = {"value": minute}
    return ev


def test_utf8_team_names():
    from providers.bbc import events_from_payload
    data = _payload([_event("m1", "Marítimo", "Benfica", "PreEvent")])
    matches = events_from_payload(data)
    assert matches[0]["home_team"] == "Marítimo"


def test_status_maps():
    from providers.bbc import events_from_payload
    events = [
        _event("a", "A", "B", "PreEvent"),
        _event("b", "C", "D", "MidEvent", minute="12'"),
        _event("c", "E", "F", "PostEvent", score_h="1", score_a="0"),
    ]
    by = {m["external_id"]: m for m in events_from_payload(_payload(events))}
    assert by["a"]["status"] == "UPCOMING"
    assert by["b"]["status"] == "LIVE"
    assert by["b"]["minute"] == "12'"
    assert by["c"]["status"] == "FINISHED"


def test_duplicate_events_collapsed():
    from providers.bbc import events_from_payload
    ev = _event("same", "Hull City", "Aston Villa", "MidEvent", minute="10'")
    data = {
        "data": {
            "sport-data-scores-fixtures?x=1": {
                "data": {
                    "eventGroups": [
                        {"displayLabel": "PL", "secondaryGroups": [{"events": [ev]}]},
                        {"displayLabel": "PL copy", "secondaryGroups": [{"events": [ev]}]},
                    ]
                }
            }
        }
    }
    matches = events_from_payload(data)
    assert len(matches) == 1


def test_malformed_rejected():
    from providers.bbc import ProviderParseError, extract_js_json_string, events_from_payload
    with pytest.raises(ProviderParseError):
        extract_js_json_string("<html>no payload</html>")
    data = _payload([{"id": None, "home": {}, "away": {}, "status": "PreEvent"}])
    assert events_from_payload(data) == []


def test_timezone_not_date_today(monkeypatch):
    from engine import timeutil
    monkeypatch.setenv("VERTICE_TZ", "Pacific/Auckland")
    # just ensure helper uses configured tz and returns ISO date
    d = timeutil.today_in_app_tz()
    assert len(d) == 10


def test_persistence_and_reload(tmp_path, monkeypatch):
    db = tmp_path / "vertice.db"
    monkeypatch.setenv("VERTICE_DB", str(db))
    import db as dbmod
    dbmod.init_db()
    from engine.store import load_latest_scan, upsert_matches
    conn = dbmod.get_conn()
    cur = conn.execute(
        "INSERT INTO scan_runs (started_at, date_local, timezone, sport_key, status) VALUES ('t','2026-09-05','UTC','football','PERSISTING')"
    )
    scan_id = cur.lastrowid
    conn.commit()
    conn.close()
    m = {
        "external_id": "ext-1",
        "external_urn": "urn:1",
        "competition": "Premier League",
        "kickoff_utc": "2026-09-05T16:30:00Z",
        "status": "LIVE",
        "minute": "11'",
        "home_team": "Hull City",
        "away_team": "Aston Villa",
        "home_score": "0",
        "away_score": "0",
        "data_quality": "HIGH",
        "integrity_level": "INSUFFICIENT DATA",
        "integrity_note": "n",
        "fetched_at": "2026-09-05T18:00:00+00:00",
    }
    r1 = upsert_matches([m], scan_id)
    assert r1["new"] == 1
    conn = dbmod.get_conn()
    cur = conn.execute(
        "INSERT INTO scan_runs (started_at, date_local, timezone, sport_key, status) VALUES ('t2','2026-09-05','UTC','football','PERSISTING')"
    )
    scan2 = cur.lastrowid
    conn.commit()
    conn.close()
    m2 = dict(m)
    m2["status"] = "FINISHED"
    m2["minute"] = None
    m2["home_score"] = "0"
    m2["away_score"] = "1"
    r2 = upsert_matches([m2], scan2)
    assert r2["updated"] == 1
    loaded = load_latest_scan("football")
    assert loaded["matches"][0]["external_id"] == "ext-1"
    assert loaded["matches"][0]["status"] == "FINISHED"
    assert loaded["matches"][0]["id"] == r1["match_ids"][0]


def test_disappeared(tmp_path, monkeypatch):
    db = tmp_path / "gone.db"
    monkeypatch.setenv("VERTICE_DB", str(db))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.store import upsert_matches
    conn = dbmod.get_conn()
    s1 = conn.execute("INSERT INTO scan_runs (started_at,date_local,status,sport_key) VALUES ('a','2026-09-05','P','football')").lastrowid
    conn.commit(); conn.close()
    a = {
        "external_id": "keep", "competition": "X", "kickoff_utc": "2026-09-05T10:00:00Z",
        "status": "FINISHED", "home_team": "A", "away_team": "B",
        "home_score": "1", "away_score": "0", "fetched_at": "t",
    }
    b = dict(a, external_id="drop", home_team="C", away_team="D")
    upsert_matches([a, b], s1)
    conn = dbmod.get_conn()
    s2 = conn.execute("INSERT INTO scan_runs (started_at,date_local,status,sport_key) VALUES ('b','2026-09-05','P','football')").lastrowid
    conn.commit(); conn.close()
    r = upsert_matches([a], s2)
    assert r["disappeared"] == 1
    conn = dbmod.get_conn()
    drop = conn.execute("SELECT presence FROM matches WHERE external_id='drop'").fetchone()
    keep = conn.execute("SELECT presence FROM matches WHERE external_id='keep'").fetchone()
    assert drop["presence"] == "DISAPPEARED_FROM_SOURCE"
    assert keep["presence"] != "DISAPPEARED_FROM_SOURCE"


def test_failed_db_write_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("VERTICE_DB", str(tmp_path / "nope.db"))
    import importlib
    import db as dbmod
    importlib.reload(dbmod)
    dbmod.init_db()
    from engine.store import upsert_matches
    with pytest.raises(Exception):
        upsert_matches([{"home_team": "A", "away_team": "B", "competition": "Z"}], 1)


def test_html_roundtrip_utf8():
    from providers.bbc import extract_js_json_string, events_from_payload
    html = _bbc_html(_payload([_event("z", "Marítimo", "São Paulo", "PreEvent")]))
    data = extract_js_json_string(html)
    matches = events_from_payload(data)
    assert matches[0]["home_team"] == "Marítimo"
    assert matches[0]["away_team"] == "São Paulo"

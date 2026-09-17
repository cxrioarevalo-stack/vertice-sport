import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module  # noqa: E402


client = TestClient(app_module.app)


def _patch_scan_basics(monkeypatch):
    monkeypatch.setattr(app_module, "today_in_app_tz", lambda: "2026-09-17")
    monkeypatch.setattr(app_module, "app_timezone_name", lambda: "UTC")
    monkeypatch.setattr(app_module, "now_utc_iso", lambda: "2026-09-17T12:00:00+00:00")
    monkeypatch.setattr(app_module, "_record_scan", lambda **fields: (7, None))
    monkeypatch.setattr(app_module, "_touch_scan", lambda scan_id, **fields: None)
    monkeypatch.setattr(app_module, "_decorate", lambda match: dict(match))
    monkeypatch.setattr(app_module, "db_path", lambda: "/tmp/test-vertice.sqlite3")


def test_scan_valid_provider_response_completes(monkeypatch):
    _patch_scan_basics(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "fetch_today",
        lambda target: {
            "count": 1,
            "fetched_at": "2026-09-17T12:00:00+00:00",
            "url": "https://example.test/bbc",
            "matches": [{"match_id": 101, "status": "UPCOMING"}],
        },
    )
    monkeypatch.setattr(app_module, "upsert_matches", lambda matches, scan_id, sport_key: {"inserted": 1})
    monkeypatch.setattr(
        app_module,
        "ingest_odds_for_matches",
        lambda matches, scan_id: {"odds_available": False, "error": None, "error_kind": "empty"},
    )
    monkeypatch.setattr(
        app_module,
        "_payload_from_db",
        lambda: {"matches": [{"match_id": 101, "status": "UPCOMING"}]},
    )

    response = client.post("/api/scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_status"] == "COMPLETED"
    assert payload["persist_ok"] is True
    assert payload["recommendation"] == "NO BET TODAY"


def test_scan_parse_error_is_failed_and_not_persisted(monkeypatch):
    _patch_scan_basics(monkeypatch)

    def raise_parse_error(target):
        raise app_module.ProviderParseError("invalid provider payload")

    monkeypatch.setattr(app_module, "fetch_today", raise_parse_error)
    monkeypatch.setattr(
        app_module,
        "_payload_from_db",
        lambda: {"matches": []},
    )

    response = client.post("/api/scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_status"] == "FAILED"
    assert payload["persist_ok"] is False
    assert payload["sources_fail"][0]["code"] == "bbc"
    assert payload["recommendation"] == "NO BET TODAY"


def test_scan_persistence_error_exposes_warning(monkeypatch):
    _patch_scan_basics(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "fetch_today",
        lambda target: {
            "count": 1,
            "fetched_at": "2026-09-17T12:00:00+00:00",
            "url": "https://example.test/bbc",
            "matches": [{"match_id": 102, "status": "UPCOMING"}],
        },
    )

    def raise_persistence_error(matches, scan_id, sport_key):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app_module, "upsert_matches", raise_persistence_error)

    response = client.post("/api/scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_status"] == "FAILED"
    assert payload["persist_ok"] is False
    assert payload["persist_error"] == "database unavailable"
    assert payload["warning"] == "Matches were fetched but NOT persisted."
    assert payload["recommendation"] == "NO BET TODAY"

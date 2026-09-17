import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app  # noqa: E402
from app import app as fastapi_app  # noqa: E402


client = TestClient(fastapi_app)


def test_touch_scan_without_id_reports_audit_failure():
    assert app._touch_scan(None, status="FETCHING") == "no scan_id"


def test_record_scan_returns_error_when_database_insert_fails(monkeypatch):
    class BrokenConnection:
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("insert failed")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(app, "get_conn", lambda: BrokenConnection())

    scan_id, error = app._record_scan(status="STARTED")

    assert scan_id is None
    assert error == "insert failed"


def test_scan_reports_missing_audit_row_when_initial_insert_fails(monkeypatch):
    monkeypatch.setattr(app, "today_in_app_tz", lambda: "2026-09-17")
    monkeypatch.setattr(app, "app_timezone_name", lambda: "UTC")
    monkeypatch.setattr(app, "now_utc_iso", lambda: "2026-09-17T00:00:00+00:00")
    monkeypatch.setattr(app, "_record_scan", lambda **fields: (None, "insert failed"))
    monkeypatch.setattr(app, "_touch_scan", lambda scan_id, **fields: "no scan_id")
    monkeypatch.setattr(
        app,
        "fetch_today",
        lambda target: {
            "count": 0,
            "fetched_at": "2026-09-17T00:00:00+00:00",
            "url": "https://example.test",
            "matches": [],
        },
    )

    response = client.post("/api/scan")
    assert response.status_code == 200
    payload = response.json()

    assert payload["scan_id"] is None
    assert payload["scan_meta_error"] == "insert failed"
    assert payload["scan_status"] == "FAILED"
    assert payload["persist_ok"] is False

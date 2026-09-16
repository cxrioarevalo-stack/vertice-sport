from __future__ import annotations

from engine.odds_catalog import (
    catalog_is_fresh,
    map_scan_snapshots,
    persist_catalog,
    persist_normalized_v043,
)
from engine.odds_store import (
    log_request,
    map_events,
    persist_odds_rows,
    persist_provider_events,
    persist_raw_captures,
)
from engine.timeutil import now_utc_iso, today_in_app_tz
from providers.odds.base import OddsProviderError, get_odds_provider


def ingest_odds_for_matches(bbc_matches: list[dict], scan_id: int | None) -> dict:
    status = {
        "odds_available": False,
        "provider": None,
        "provider_status": "UNAVAILABLE",
        "bookmaker_request": None,
        "error": None,
        "error_kind": None,
        "events": 0,
        "matched": 0,
        "unmatched": 0,
        "odds_rows": 0,
        "requests": 0,
        "fetched_at": None,
        "fixture_errors": [],
        "catalog_refreshed": False,
        "catalog_count": 0,
        "mapped_odds": 0,
        "unmapped_odds": 0,
    }
    try:
        provider = get_odds_provider()
    except OddsProviderError as exc:
        status["error"] = str(exc)
        status["error_kind"] = exc.kind
        status["provider_status"] = "ERROR"
        return status
    status["provider"] = provider.display_name
    status["bookmaker_request"] = getattr(provider, "bookmakers", None)
    if not provider.configured():
        status["error"] = "odds API key missing"
        status["error_kind"] = "missing_key"
        status["provider_status"] = "NOT_CONFIGURED"
        log_request(provider.code, "config", None, False, status["error"])
        return status

    fetched_at = now_utc_iso()
    status["fetched_at"] = fetched_at
    day = today_in_app_tz()
    try:
        events = provider.fetch_events(day, day)
        log_request(provider.code, "/events", 200, True, None)
        persist_provider_events(events, fetched_at)
        status["events"] = len(events)
        mapping = map_events(bbc_matches, events)
        status["matched"] = len(mapping["matched"])
        status["unmatched"] = len(mapping["unmatched"])
        if mapping.get("persist_ok") is False:
            status["error"] = mapping.get("persist_error") or "odds map persist failed"
            status["error_kind"] = "sqlite"
            status["provider_status"] = "ERROR"
        id_to_match = {m["provider_event_id"]: m["match_id"] for m in mapping["matched"]}
        event_ids = [str(e.get("provider_event_id")) for e in events if e.get("provider_event_id")]
        if event_ids:
            rows = provider.fetch_odds(event_ids, fetched_at)
            for r in rows:
                r["provider_code"] = provider.code
            persist_raw_captures(
                list(getattr(provider, "raw_captures", []) or []),
                scan_id,
                secret=getattr(provider, "api_key", None),
            )
            n = persist_odds_rows(rows, scan_id, id_to_match)
            status["odds_rows"] = n
            try:
                v043 = persist_normalized_v043(rows, scan_id, id_to_match, provider_code=provider.code)
                status["v043_mapped"] = v043["mapped"]
                status["v043_unmapped"] = v043["unmapped"]
            except Exception as exc:
                status["v043_error"] = str(exc)
            status["odds_available"] = n > 0
            status["fixture_errors"] = list(getattr(provider, "fixture_errors", []) or [])
            status["provider_status"] = "OK" if n > 0 else "UNAVAILABLE"
            if n > 0 and hasattr(provider, "fetch_markets"):
                try:
                    if not catalog_is_fresh(provider.code, "football", 10):
                        catalog = provider.fetch_markets(10)
                        status["catalog_count"] = persist_catalog(
                            catalog,
                            provider_code=provider.code,
                            sport_key="football",
                            sport_id=10,
                            fetched_at=fetched_at,
                        )
                        status["catalog_refreshed"] = True
                        log_request(provider.code, "/markets", 200, True, None)
                    mapped = map_scan_snapshots(scan_id, provider_code=provider.code, sport_key="football")
                    status["mapped_odds"] = mapped["mapped"]
                    status["unmapped_odds"] = mapped["unmapped"]
                except OddsProviderError as exc:
                    status["catalog_error"] = str(exc)
                    log_request(provider.code, "/markets", exc.http_status, False, "catalog error")
                    mapped = map_scan_snapshots(scan_id, provider_code=provider.code, sport_key="football")
                    status["mapped_odds"] = mapped["mapped"]
                    status["unmapped_odds"] = mapped["unmapped"]
        else:
            status["provider_status"] = "UNAVAILABLE"
        status["requests"] = getattr(provider, "requests", 0)
    except OddsProviderError as exc:
        status["error"] = str(exc)
        status["error_kind"] = exc.kind
        status["provider_status"] = "ERROR" if exc.kind != "missing_key" else "NOT_CONFIGURED"
        log_request(provider.code, "fetch", exc.http_status, False, "provider error")
        status["requests"] = getattr(provider, "requests", 0)
    return status

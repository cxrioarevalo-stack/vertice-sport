"""BBC Sport public fixtures parser. No API key. Strict UTF-8 JSON decode."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

BBC_URL = "https://www.bbc.co.uk/sport/football/scores-fixtures/{date}"
HEADERS = {
    "User-Agent": "VerticeSport/0.3.1 research scanner",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

STATUS_MAP = {
    "PreEvent": "UPCOMING",
    "MidEvent": "LIVE",
    "PostEvent": "FINISHED",
    "Suspended": "SUSPENDED",
}


class ProviderParseError(ValueError):
    pass


def extract_js_json_string(html: str) -> dict:
    marker = "window.__INITIAL_DATA__="
    i = html.find(marker)
    if i < 0:
        raise ProviderParseError("BBC page did not contain __INITIAL_DATA__")
    s = html[i + len(marker) :].lstrip()
    if not s.startswith('"'):
        raise ProviderParseError("Unexpected BBC payload format")
    decoder = json.JSONDecoder()
    try:
        encoded, _ = decoder.raw_decode(s)
    except json.JSONDecodeError as exc:
        raise ProviderParseError(f"Invalid BBC JSON wrapper: {exc}") from exc
    if isinstance(encoded, str):
        try:
            return json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise ProviderParseError(f"Invalid BBC inner JSON: {exc}") from exc
    if isinstance(encoded, dict):
        return encoded
    raise ProviderParseError("BBC payload was not an object")


def _period(ev: dict) -> str | None:
    pl = ev.get("periodLabel") or {}
    if isinstance(pl, dict):
        val = pl.get("value")
        return str(val) if val is not None else None
    return None


def normalize_event(ev: dict, competition: str, fetched_at: str) -> dict | None:
    if not isinstance(ev, dict):
        return None
    home = ev.get("home") or {}
    away = ev.get("away") or {}
    ext_id = ev.get("id")
    home_name = home.get("fullName") if isinstance(home, dict) else None
    away_name = away.get("fullName") if isinstance(away, dict) else None
    if not ext_id or not home_name or not away_name:
        return None
    raw_status = ev.get("status")
    status = STATUS_MAP.get(raw_status)
    if status is None:
        return None
    kickoff = ev.get("startDateTime")
    if not kickoff:
        return None
    return {
        "external_id": str(ext_id),
        "external_urn": ev.get("urn"),
        "competition": competition,
        "kickoff_utc": kickoff,
        "display_time_uk": (ev.get("time") or {}).get("displayTimeUK") if isinstance(ev.get("time"), dict) else None,
        "status": status,
        "status_raw": raw_status,
        "minute": _period(ev) if raw_status == "MidEvent" else None,
        "home_team": home_name,
        "away_team": away_name,
        "home_score": home.get("score") if isinstance(home, dict) else None,
        "away_score": away.get("score") if isinstance(away, dict) else None,
        "venue": None,
        "source": "bbc",
        "source_name": "BBC Sport",
        "sport_key": "football",
        "data_status": "REAL",
        "fetched_at": fetched_at,
        "tournament_path": ev.get("onwardJourneyLink"),
    }


def events_from_payload(data: dict, fetched_at: str | None = None) -> list[dict]:
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    block = data.get("data") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        raise ProviderParseError("BBC payload missing data object")
    key = next((k for k in block if str(k).startswith("sport-data-scores-fixtures")), None)
    if not key:
        raise ProviderParseError("BBC payload missing scores-fixtures block")
    inner = (block[key] or {}).get("data") or {}
    groups = inner.get("eventGroups") or []
    by_id: dict[str, dict] = {}
    rejected = 0
    for g in groups:
        if not isinstance(g, dict):
            continue
        comp = g.get("displayLabel") or "Unknown"
        for sg in g.get("secondaryGroups") or []:
            if not isinstance(sg, dict):
                continue
            for ev in sg.get("events") or []:
                norm = normalize_event(ev, comp, fetched_at)
                if not norm:
                    rejected += 1
                    continue
                by_id[norm["external_id"]] = norm
    return list(by_id.values())


def fetch_today(date_iso: str, timeout: float = 25.0, client: httpx.Client | None = None) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    url = BBC_URL.format(date=date_iso)
    own = client is None
    if own:
        client = httpx.Client(timeout=timeout, follow_redirects=True, headers=HEADERS)
    try:
        r = client.get(url)
        r.raise_for_status()
        html = r.text
    finally:
        if own:
            client.close()
    data = extract_js_json_string(html)
    matches = events_from_payload(data, fetched_at)
    return {
        "ok": True,
        "source": "bbc",
        "url": url,
        "fetched_at": fetched_at,
        "count": len(matches),
        "matches": matches,
    }

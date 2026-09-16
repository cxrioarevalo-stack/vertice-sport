"""Odds-API.io third-party aggregator. Not an official Betano API."""
from __future__ import annotations

import os
from typing import Any

import httpx

from providers.odds.base import OddsProviderError

BASE = os.environ.get("ODDS_API_BASE", "https://api.odds-api.io/v3")
DEFAULT_BOOKMAKERS = os.environ.get("ODDS_BOOKMAKERS", "Betano")
MAX_EVENT_ODDS_CALLS = int(os.environ.get("ODDS_MAX_EVENT_CALLS", "25"))


MARKET_MAP = {
    "ML": ("1x2", "Match result 1X2"),
    "1X2": ("1x2", "Match result 1X2"),
    "MONEYLINE": ("1x2", "Match result 1X2"),
    "DC": ("double_chance", "Double chance"),
    "DOUBLE CHANCE": ("double_chance", "Double chance"),
    "DNB": ("dnb", "Draw no bet"),
    "DRAW NO BET": ("dnb", "Draw no bet"),
    "SPREAD": ("ah", "Asian handicap"),
    "AH": ("ah", "Asian handicap"),
    "ASIAN HANDICAP": ("ah", "Asian handicap"),
    "HANDICAP": ("handicap", "European handicap"),
    "TOTALS": ("ou", "Over/Under"),
    "OU": ("ou", "Over/Under"),
    "OVER/UNDER": ("ou", "Over/Under"),
    "BTTS": ("btts", "Both teams to score"),
    "BOTH TEAMS TO SCORE": ("btts", "Both teams to score"),
    "TEAM TOTALS": ("team_goals", "Team totals"),
}


def normalize_market_name(raw: str) -> tuple[str, str]:
    key = (raw or "").strip().upper()
    return MARKET_MAP.get(key, (key.lower().replace(" ", "_") or "unknown", raw or "unknown"))


def parse_decimal(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 1.0:
        return None
    return n


def flatten_bookmaker_markets(event: dict, bookmaker: str, markets: list, phase: str, fetched_at: str) -> list[dict]:
    rows = []
    if not isinstance(markets, list):
        return rows
    for market in markets:
        if not isinstance(market, dict):
            continue
        raw_name = market.get("name") or ""
        code, label = normalize_market_name(str(raw_name))
        updated = market.get("updatedAt")
        odds_list = market.get("odds") or []
        if not isinstance(odds_list, list):
            continue
        for block in odds_list:
            if not isinstance(block, dict):
                continue
            line = block.get("hdp") if block.get("hdp") is not None else block.get("total")
            mapping = [
                ("home", "Home"),
                ("draw", "Draw"),
                ("away", "Away"),
                ("over", "Over"),
                ("under", "Under"),
                ("yes", "Yes"),
                ("no", "No"),
            ]
            for key, sel in mapping:
                if key not in block:
                    continue
                dec = parse_decimal(block.get(key))
                if dec is None:
                    continue
                rows.append({
                    "provider_event_id": str(event.get("id")),
                    "bookmaker": bookmaker,
                    "market_code": code,
                    "market_name": label,
                    "selection": sel,
                    "line": float(line) if line is not None and line != "" else None,
                    "decimal_odds": dec,
                    "raw_odds": str(block.get(key)),
                    "phase": phase,
                    "data_status": "REAL",
                    "source_updated_at": updated,
                    "observed_at": fetched_at,
                    "home": event.get("home"),
                    "away": event.get("away"),
                    "kickoff_utc": event.get("date"),
                    "competition": (event.get("league") or {}).get("name") if isinstance(event.get("league"), dict) else None,
                })
    return rows


class OddsApiIoProvider:
    code = "odds_api_io"
    display_name = "Odds-API.io"

    def __init__(self, api_key: str | None = None, bookmakers: str | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("ODDS_API_KEY", "").strip()
        self.bookmakers = bookmakers or DEFAULT_BOOKMAKERS
        self.requests = 0

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict) -> Any:
        if not self.api_key:
            raise OddsProviderError("ODDS_API_KEY missing", kind="missing_key")
        params = {**params, "apiKey": self.api_key}
        self.requests += 1
        with httpx.Client(timeout=25.0) as client:
            r = client.get(f"{BASE}{path}", params=params)
        if r.status_code == 429:
            raise OddsProviderError("rate limited", kind="rate_limit", http_status=429)
        if r.status_code in (401, 403):
            raise OddsProviderError(f"auth failed HTTP {r.status_code}", kind="auth", http_status=r.status_code)
        if r.status_code >= 400:
            raise OddsProviderError(f"HTTP {r.status_code}", kind="http", http_status=r.status_code)
        return r.json()

    def fetch_events(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        raw = self._get("/events", {
            "sport": "football",
            "from": date_from if "T" in date_from else f"{date_from}T00:00:00Z",
            "to": date_to if "T" in date_to else f"{date_to}T23:59:59Z",
            "limit": 500,
        })
        if not isinstance(raw, list):
            raise OddsProviderError("events payload is not a list", kind="parse")
        out = []
        for ev in raw:
            if not isinstance(ev, dict) or ev.get("id") is None:
                continue
            out.append({
                "provider_code": self.code,
                "provider_event_id": str(ev["id"]),
                "home_team": ev.get("home"),
                "away_team": ev.get("away"),
                "competition": (ev.get("league") or {}).get("name") if isinstance(ev.get("league"), dict) else None,
                "kickoff_utc": ev.get("date"),
                "raw_status": ev.get("status"),
                "raw": ev,
            })
        return out

    def _odds_rows_from_payload(self, payload: dict, fetched_at: str) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        status = str(payload.get("status") or "")
        phase = "LIVE" if status.lower() == "live" else "PREMATCH"
        books = payload.get("bookmakers") or {}
        if not isinstance(books, dict):
            return []
        rows = []
        for bookmaker, markets in books.items():
            rows.extend(flatten_bookmaker_markets(payload, str(bookmaker), markets, phase, fetched_at))
        return rows

    def fetch_odds(self, event_ids: list[str], fetched_at: str) -> list[dict[str, Any]]:
        """Prefer /odds/multi (up to 10 IDs = 1 request). Fall back to /odds per event."""
        ids = [str(i) for i in event_ids if i][:MAX_EVENT_ODDS_CALLS]
        rows: list[dict] = []
        batch_size = 10
        for i in range(0, len(ids), batch_size):
            chunk = ids[i:i + batch_size]
            used_multi = False
            try:
                payload = self._get("/odds/multi", {
                    "eventIds": ",".join(chunk),
                    "bookmakers": self.bookmakers,
                })
                events = payload if isinstance(payload, list) else ([payload] if isinstance(payload, dict) else [])
                if events:
                    for ev in events:
                        rows.extend(self._odds_rows_from_payload(ev, fetched_at))
                    used_multi = True
            except OddsProviderError:
                used_multi = False
            if used_multi:
                continue
            for eid in chunk:
                try:
                    single = self._get("/odds", {"eventId": eid, "bookmakers": self.bookmakers})
                except OddsProviderError:
                    continue
                if isinstance(single, dict):
                    rows.extend(self._odds_rows_from_payload(single, fetched_at))
        return rows

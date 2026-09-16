"""OddsPapi v4 adapter. Third-party odds feed — not an official Betano API."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

from providers.odds.base import OddsProviderError

BASE = os.environ.get("ODDSPAPI_BASE", "https://api.oddspapi.io/v4")
SPORT_FOOTBALL = 10
MAX_ODDS_CALLS = int(os.environ.get("ODDS_MAX_EVENT_CALLS", "15"))
DEFAULT_BOOKMAKERS = os.environ.get("ODDS_BOOKMAKERS", "betano")


def _redact(text: str, key: str) -> str:
    if key and key in text:
        return text.replace(key, "[REDACTED]")
    return text


def parse_price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 1.0:
        return None
    return n


def _numeric_line(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _supplied_line(obj: dict | None) -> float | None:
    """Fixture-specific bookmaker line from an odds node. Never catalog handicap.

    Precedence on the same object (OddsPapi Betano payload):
    1. points
    2. handicap  (odds-node field only; catalog handicap is stored separately)
    3. line
    4. selection_line only when numeric (ignore over/under labels)
    mainLine is a flag, not a line.
    """
    if not isinstance(obj, dict):
        return None
    for key in ("points", "handicap", "line"):
        parsed = _numeric_line(obj.get(key)) if key in obj else None
        if parsed is not None:
            return parsed
    if "selection_line" in obj:
        return _numeric_line(obj.get("selection_line"))
    return None


def parse_market_outcomes(market_id: str, market: Any) -> list[dict]:
    """market → outcomes[outcomeId] → players[playerId] → price. No inferred lines."""
    found: list[dict] = []
    if not isinstance(market, dict):
        return found
    book_mid = market.get("bookmakerMarketId")
    outcomes = market.get("outcomes")
    if not isinstance(outcomes, dict):
        return found
    for oid, oc in outcomes.items():
        if not isinstance(oc, dict):
            continue
        players = oc.get("players")
        if not isinstance(players, dict):
            continue
        for pid, node in players.items():
            if not isinstance(node, dict) or "price" not in node:
                continue
            price = parse_price(node.get("price"))
            if price is None:
                continue
            line = _supplied_line(node)
            if line is None:
                line = _supplied_line(oc)
            if line is None:
                line = _supplied_line(market)
            pname = node.get("playerName")
            if pname == "":
                pname = None
            found.append({
                "market_id": str(market_id),
                "bookmaker_market_id": book_mid,
                "outcome_id": str(oid),
                "bookmaker_outcome_id": node.get("bookmakerOutcomeId"),
                "player_id": None if str(pid) == "0" else str(pid),
                "player_name": pname,
                "price": price,
                "line": line,
            })
    return found


def extract_prices(node: Any, market_id: str) -> list[dict]:
    """Backward-compatible wrapper used by older tests."""
    structured = parse_market_outcomes(market_id, node)
    if structured:
        return [{
            "market_id": x["market_id"],
            "market_name_raw": None,
            "outcome_id": x["outcome_id"],
            "outcome_name_raw": x.get("player_name"),
            "price": x["price"],
            "line": x["line"],
        } for x in structured]
    found: list[dict] = []

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            if "price" in obj:
                price = parse_price(obj.get("price"))
                if price is not None:
                    raw_name = obj.get("playerName") or obj.get("name") or obj.get("label") or obj.get("selection")
                    found.append({
                        "market_id": str(market_id),
                        "market_name_raw": None,
                        "outcome_id": obj.get("id") or obj.get("outcomeId") or obj.get("selectionId") or path,
                        "outcome_name_raw": raw_name if raw_name else None,
                        "price": price,
                        "line": _supplied_line(obj),
                    })
                return
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(node, str(market_id))
    return found


def flatten_bookmaker_odds(payload: dict, fetched_at: str, wanted_slug: str) -> list[dict]:
    rows: list[dict] = []
    if not isinstance(payload, dict):
        return rows
    books = payload.get("bookmakerOdds")
    if not isinstance(books, dict):
        return rows
    status_id = payload.get("statusId")
    if status_id == 2:
        phase = "LIVE"
    elif status_id in (0, 1, None):
        phase = "PREMATCH"
    else:
        phase = "PREMATCH"
    fid = str(payload.get("fixtureId") or "")
    for slug, block in books.items():
        slug_l = str(slug).lower()
        if wanted_slug and slug_l != wanted_slug.lower():
            continue
        if not isinstance(block, dict):
            continue
        markets = block.get("markets") or {}
        if not isinstance(markets, dict):
            continue
        for mid, market in markets.items():
            name = None
            if isinstance(market, dict):
                raw_n = market.get("marketName") or market.get("name") or market.get("label")
                if raw_n and not str(raw_n).isdigit():
                    name = str(raw_n)
            structured = parse_market_outcomes(str(mid), market)
            items = structured or extract_prices(market, str(mid))
            for item in items:
                oid = item.get("outcome_id")
                rows.append({
                    "provider_code": "oddspapi",
                    "provider_event_id": fid,
                    "bookmaker": slug_l,
                    "bookmaker_slug": slug_l,
                    "market_code": item.get("market_id") or str(mid),
                    "market_name": name,
                    "selection": oid or "unlabeled",
                    "outcome_id": oid,
                    "outcome_name_raw": None,
                    "player_id": item.get("player_id"),
                    "player_name": item.get("player_name"),
                    "bookmaker_market_id": item.get("bookmaker_market_id"),
                    "bookmaker_outcome_id": item.get("bookmaker_outcome_id"),
                    "line": item.get("line"),
                    "decimal_odds": item["price"] if "price" in item else item.get("decimal_odds"),
                    "raw_odds": str(item.get("price") or item.get("decimal_odds")),
                    "phase": phase,
                    "data_status": "REAL",
                    "source_updated_at": payload.get("updatedAt"),
                    "observed_at": fetched_at,
                    "home": payload.get("participant1Name"),
                    "away": payload.get("participant2Name"),
                    "kickoff_utc": payload.get("startTime"),
                    "mapping_needed": True,
                })
    return rows


class OddsPapiProvider:
    code = "oddspapi"
    display_name = "OddsPapi v4"

    def __init__(self, api_key: str | None = None, bookmakers: str | None = None):
        self.api_key = (api_key if api_key is not None else os.environ.get("ODDSPAPI_API_KEY", "")).strip()
        self.bookmakers = (bookmakers or DEFAULT_BOOKMAKERS).split(",")[0].strip()
        self.requests = 0

    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict) -> Any:
        if not self.api_key:
            raise OddsProviderError("ODDSPAPI_API_KEY missing", kind="missing_key")
        q = {**params, "apiKey": self.api_key}
        self.requests += 1
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(f"{BASE}{path}", params=q)
        except httpx.HTTPError as exc:
            raise OddsProviderError(_redact(str(exc), self.api_key), kind="network") from exc
        if r.status_code >= 400:
            body = _redact((r.text or "")[:400], self.api_key)
            if r.status_code == 401:
                kind = "auth"
            elif r.status_code == 403:
                kind = "forbidden"
            elif r.status_code == 429:
                kind = "rate_limit"
            elif r.status_code >= 500:
                kind = "server"
            else:
                kind = "client"
            raise OddsProviderError(
                f"HTTP {r.status_code} {kind}: {body}",
                kind=kind,
                http_status=r.status_code,
            )
        try:
            return r.json()
        except ValueError as exc:
            raise OddsProviderError("invalid JSON", kind="parse") from exc

    def fetch_events(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        start = date_from if "T" in date_from else f"{date_from}T00:00:00"
        end = date_to if "T" in date_to else f"{date_to}T23:59:59"
        # OddsPapi: sportId + from/to window
        raw = self._get("/fixtures", {
            "sportId": SPORT_FOOTBALL,
            "from": start,
            "to": end,
            "hasOdds": "true",
            "bookmakers": self.bookmakers,
        })
        if not isinstance(raw, list):
            raise OddsProviderError("fixtures payload is not a list", kind="parse")
        out = []
        for fx in raw:
            if not isinstance(fx, dict) or not fx.get("fixtureId"):
                continue
            out.append({
                "provider_code": self.code,
                "provider_event_id": str(fx["fixtureId"]),
                "home_team": fx.get("participant1Name"),
                "away_team": fx.get("participant2Name"),
                "competition": fx.get("tournamentName"),
                "kickoff_utc": fx.get("startTime"),
                "raw_status": str(fx.get("statusId")) if fx.get("statusId") is not None else None,
                "has_odds": fx.get("hasOdds"),
                "raw": fx,
            })
        return out

    def fetch_odds(self, event_ids: list[str], fetched_at: str) -> list[dict[str, Any]]:
        """v4 /odds is per fixture. Cap with ODDS_MAX_EVENT_CALLS. One failure does not abort the rest."""
        rows: list[dict] = []
        self.fixture_errors: list[dict] = []
        self.raw_captures: list[dict] = []
        ids = [str(i) for i in event_ids if i][:MAX_ODDS_CALLS]
        for i, eid in enumerate(ids):
            if i > 0:
                time.sleep(0.6)
            try:
                payload = self._get("/odds", {"fixtureId": eid, "bookmakers": self.bookmakers})
            except OddsProviderError as exc:
                self.fixture_errors.append({
                    "fixture_id": eid,
                    "http_status": exc.http_status,
                    "kind": exc.kind,
                    "error": _redact(str(exc), self.api_key),
                })
                continue
            if not isinstance(payload, dict):
                self.fixture_errors.append({
                    "fixture_id": eid,
                    "http_status": None,
                    "kind": "parse",
                    "error": "odds payload is not an object",
                })
                continue
            self.raw_captures.append({
                "provider_code": self.code,
                "provider_event_id": eid,
                "bookmaker": self.bookmakers,
                "captured_at": fetched_at,
                "payload": payload,
            })
            rows.extend(flatten_bookmaker_odds(payload, fetched_at, self.bookmakers))
        return rows

    def fetch_markets(self, sport_id: int = SPORT_FOOTBALL) -> list[dict[str, Any]]:
        raw = self._get("/markets", {"language": "en", "sportId": sport_id})
        if not isinstance(raw, list):
            raise OddsProviderError("markets payload is not a list", kind="parse")
        out = []
        for m in raw:
            if not isinstance(m, dict) or m.get("marketId") is None:
                continue
            outcomes = []
            for oc in m.get("outcomes") or []:
                if not isinstance(oc, dict):
                    continue
                if oc.get("outcomeId") is None:
                    continue
                outcomes.append({
                    "outcome_id": str(oc.get("outcomeId")),
                    "outcome_name": oc.get("outcomeName"),
                })
            out.append({
                "market_id": str(m.get("marketId")),
                "market_name": m.get("marketName"),
                "market_type": m.get("marketType"),
                "period": m.get("period"),
                "player_prop": bool(m.get("playerProp")),
                "catalog_handicap": m.get("handicap"),
                "outcomes": outcomes,
            })
        return out

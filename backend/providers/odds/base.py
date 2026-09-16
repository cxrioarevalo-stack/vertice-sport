from __future__ import annotations

import os
from typing import Any, Protocol


class OddsProviderError(Exception):
    def __init__(self, message: str, *, kind: str = "error", http_status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status


class OddsProvider(Protocol):
    code: str
    display_name: str

    def configured(self) -> bool: ...
    def fetch_events(self, date_from: str, date_to: str) -> list[dict[str, Any]]: ...
    def fetch_odds(self, event_ids: list[str]) -> list[dict[str, Any]]: ...


def get_odds_provider() -> OddsProvider:
    name = os.environ.get("ODDS_PROVIDER", "oddspapi").strip().lower()
    if name in {"oddspapi", "odds_papi", "odds-papi"}:
        from providers.odds.oddspapi import OddsPapiProvider
        return OddsPapiProvider()
    if name in {"odds_api_io", "odds-api.io", "oddsapiio"}:
        from providers.odds.odds_api_io import OddsApiIoProvider
        return OddsApiIoProvider()
    raise OddsProviderError(f"Unknown ODDS_PROVIDER={name}", kind="config")

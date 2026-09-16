from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/New_York"


def app_timezone_name() -> str:
    return os.environ.get("VERTICE_TZ", DEFAULT_TZ)


def app_tz() -> ZoneInfo:
    return ZoneInfo(app_timezone_name())


def now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def now_utc_iso() -> str:
    return now_utc().isoformat()


def today_in_app_tz() -> str:
    return datetime.now(tz=app_tz()).date().isoformat()


def to_display(iso_utc: str | None, tz_name: str | None = None) -> str | None:
    if not iso_utc:
        return None
    raw = iso_utc.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local = dt.astimezone(ZoneInfo(tz_name or app_timezone_name()))
    return local.strftime("%Y-%m-%d %H:%M %Z")

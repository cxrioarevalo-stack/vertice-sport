"""Market attention. UNKNOWN unless a verifiable volume field exists."""
from __future__ import annotations

UNKNOWN = "UNKNOWN"
LOW = "LOW"
NORMAL = "NORMAL"
HIGH = "HIGH"
EXTREME = "EXTREME"


VOLUME_KEYS = (
    "ticket_share",
    "bet_share",
    "volume",
    "handle",
    "popularity",
    "market_share",
)


def market_attention(row: dict | None) -> dict:
    row = row or {}
    found = None
    key_used = None
    for k in VOLUME_KEYS:
        if row.get(k) is not None:
            found = row[k]
            key_used = k
            break
    if found is None:
        return {
            "attention": UNKNOWN,
            "value": None,
            "source": None,
            "note": "No ticket share/volume from current providers. Popularity is not inferred from price.",
            "implies_failure": False,
        }
    try:
        v = float(found)
    except (TypeError, ValueError):
        return {"attention": UNKNOWN, "value": found, "source": key_used, "implies_failure": False}
    if v >= 0.7:
        att = EXTREME
    elif v >= 0.5:
        att = HIGH
    elif v >= 0.2:
        att = NORMAL
    else:
        att = LOW
    return {
        "attention": att,
        "value": v,
        "source": key_used,
        "note": "Attention is not a prediction that the selection will lose.",
        "implies_failure": False,
    }

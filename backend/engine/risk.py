"""Conservative risk wrapper over integrity. Never claims a match is fixed or clean."""
from __future__ import annotations

from engine.integrity import assess

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"
CRITICAL = "CRITICAL"
UNKNOWN = "UNKNOWN"
LIMITED = "LIMITED"


def risk_state(match: dict, news: list | None = None) -> dict:
    integ = assess(match, news)
    level = integ.get("level") or ""
    if level in ("CRITICAL", "HIGH"):
        risk = CRITICAL if level == "CRITICAL" else HIGH
    elif level in ("MODERATE RISK", "MEDIUM"):
        risk = MEDIUM
    elif level in ("LOW",):
        risk = LOW
    else:
        risk = LIMITED
    exclude = risk in {HIGH, CRITICAL}
    return {
        **integ,
        "risk_state": risk if integ.get("signals") else UNKNOWN,
        "risk_label": integ.get("label") or UNKNOWN,
        "exclude_from_selection": exclude,
        "claim": None,
        "note": integ.get("note"),
    }

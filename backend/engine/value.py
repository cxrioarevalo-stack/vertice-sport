"""EV/value. NULL whenever model_probability is NULL. Never EV from implied-only."""
from __future__ import annotations


def expected_value(model_p: float | None, decimal_odds: float | None) -> dict:
    if model_p is None or decimal_odds is None:
        return {
            "ev": None,
            "value": None,
            "edge": None,
            "status": "NOT_READY",
            "reason": "model_probability_or_odds_missing",
        }
    try:
        p = float(model_p)
        o = float(decimal_odds)
    except (TypeError, ValueError):
        return {"ev": None, "value": None, "edge": None, "status": "INVALID", "reason": "non_numeric"}
    if o <= 1 or p < 0 or p > 1:
        return {"ev": None, "value": None, "edge": None, "status": "INVALID", "reason": "out_of_range"}
    ev = p * o - 1.0
    implied = 1.0 / o
    return {
        "ev": ev,
        "value": ev,
        "edge": p - implied,
        "status": "OK",
        "reason": None,
    }


def value_from_row(row: dict) -> dict:
    return expected_value(row.get("model_probability"), row.get("decimal_odds"))

"""Combination architecture. Disabled until independent model probabilities exist."""
from __future__ import annotations

CORRELATED_FAMILIES = {
    frozenset({"1X2", "DOUBLE_CHANCE"}),
    frozenset({"1X2", "DRAW_NO_BET"}),
    frozenset({"BTTS", "OVER_UNDER"}),
    frozenset({"TEAM_TOTAL", "OVER_UNDER"}),
    frozenset({"1X2", "OVER_UNDER"}),
}


def families_correlated(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    pair = frozenset({a, b})
    return pair in CORRELATED_FAMILIES


def combine(rows: list[dict]) -> dict:
    probs = [r.get("model_probability") for r in rows]
    if any(p is None for p in probs) or not rows:
        return {
            "status": "NOT_READY",
            "combined_probability": None,
            "reason": "missing_model_probability_or_empty",
            "assumed_independence": False,
            "correlated": any(
                families_correlated(rows[i].get("market_family"), rows[j].get("market_family"))
                for i in range(len(rows))
                for j in range(i + 1, len(rows))
            ),
        }
    return {
        "status": "BLOCKED",
        "combined_probability": None,
        "reason": "independence_not_assumed",
        "assumed_independence": False,
        "correlated": True,
    }

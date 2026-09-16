"""Calibration metrics. Disabled until a trained model and settled sample exist."""
from __future__ import annotations

import math

MIN_CALIB = 50


def _safe_p(p) -> float | None:
    try:
        v = float(p)
    except (TypeError, ValueError):
        return None
    if v <= 0 or v >= 1:
        return None
    return v


def brier_score(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    total = 0.0
    for p, y in pairs:
        p = min(max(p, 1e-15), 1 - 1e-15)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(pairs)


def calibration_report(observations: list[dict]) -> dict:
    pairs = []
    for o in observations:
        mp = _safe_p(o.get("model_probability"))
        outcome = o.get("settlement_result")
        if mp is None or outcome not in ("WON", "LOST"):
            continue
        pairs.append((mp, 1 if outcome == "WON" else 0))
    if len(pairs) < MIN_CALIB:
        return {
            "status": "NOT_READY",
            "n": len(pairs),
            "brier": None,
            "log_loss": None,
            "calibration_error": None,
            "reason": "insufficient_settled_model_predictions",
        }
    return {
        "status": "OK",
        "n": len(pairs),
        "brier": brier_score(pairs),
        "log_loss": log_loss(pairs),
        "calibration_error": None,
        "reason": None,
    }

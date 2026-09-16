"""Selection gate. Prefer NO_BET when model or data is insufficient."""
from __future__ import annotations

from engine.analysis import ANALYZE, EXCLUDE, NO_BET, WATCH, analyze_market
from engine.model import MODEL_NOT_READY, model_probability
from engine.value import expected_value

BET = "BET"


def select_opportunity(row: dict, model_status: str = MODEL_NOT_READY) -> dict:
    analyzed = analyze_market(row)
    pred = model_probability(None, analyzed)
    ev = expected_value(pred.get("model_probability"), analyzed.get("decimal_odds"))
    analyzed["model_probability"] = pred.get("model_probability")
    analyzed["ev"] = ev.get("ev")
    analyzed["value"] = ev.get("value")
    if analyzed.get("analysis_state") == EXCLUDE:
        analyzed["selection"] = NO_BET
        analyzed["selection_reason"] = analyzed.get("analysis_reason")
        return analyzed
    if model_status == MODEL_NOT_READY or pred.get("model_probability") is None:
        analyzed["selection"] = NO_BET
        analyzed["selection_reason"] = "model_not_ready"
        return analyzed
    if ev.get("ev") is None:
        analyzed["selection"] = NO_BET
        analyzed["selection_reason"] = "ev_unavailable"
        return analyzed
    if ev["ev"] <= 0:
        analyzed["selection"] = WATCH if analyzed.get("analysis_state") == ANALYZE else NO_BET
        analyzed["selection_reason"] = "non_positive_ev"
        return analyzed
    analyzed["selection"] = BET
    analyzed["selection_reason"] = "positive_ev_and_ready"
    return analyzed


def select_today(rows: list[dict], model_status: str = MODEL_NOT_READY) -> dict:
    selected = [select_opportunity(r, model_status) for r in rows]
    bets = [r for r in selected if r.get("selection") == BET]
    return {
        "selection_state": BET if bets else NO_BET,
        "picks": bets,
        "watch": [r for r in selected if r.get("selection") == WATCH],
        "no_bet_count": sum(1 for r in selected if r.get("selection") == NO_BET),
        "headline": "NO BET TODAY" if not bets else f"{len(bets)} BET",
        "reason": "model_or_data_insufficient" if not bets else None,
        "model_status": model_status,
        "markets": selected,
    }

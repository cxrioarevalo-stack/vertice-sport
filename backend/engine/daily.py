"""Cuota del Día. Disabled while model is NOT_READY. Never pick by lowest/highest price."""
from __future__ import annotations

from engine.analysis import EXCLUDE
from engine.model import MODEL_EVALUATED, MODEL_TRAINED, model_status
from engine.popularity import UNKNOWN, market_attention
from engine.selection import NO_BET, select_opportunity
from engine.value import expected_value

READY_MODEL = {MODEL_TRAINED, MODEL_EVALUATED, "CALIBRATED"}


def cuota_del_dia(rows: list[dict], model_st: str | None = None) -> dict:
    st = model_st or model_status()["model_status"]
    attn_unknown = all(market_attention(r)["attention"] == UNKNOWN for r in (rows or [{}]))
    base = {
        "module": "CUOTA_DEL_DIA",
        "model_status": st,
        "pick": None,
        "selection": NO_BET,
        "headline": "NO BET TODAY — No existe actualmente una oportunidad con datos y probabilidad de modelo suficientes.",
        "market_attention": UNKNOWN if attn_unknown else None,
        "predictive": False,
    }
    if st not in READY_MODEL:
        base["mode"] = "OPORTUNIDADES_EN_OBSERVACION"
        base["label"] = "MODEL NOT READY · DATA INSUFFICIENT"
        base["available_markets"] = len(rows or [])
        return base
    candidates = []
    for r in rows or []:
        sel = select_opportunity(r, st)
        if sel.get("selection") == NO_BET:
            continue
        if sel.get("analysis_state") == EXCLUDE:
            continue
        if sel.get("model_probability") is None:
            continue
        ev = expected_value(sel.get("model_probability"), sel.get("decimal_odds"))
        if ev.get("ev") is None:
            continue
        attn = market_attention(r)
        candidates.append({**sel, "ev": ev.get("ev"), "attention": attn})
    if not candidates:
        return base
    candidates.sort(key=lambda x: (x.get("model_probability") or 0, x.get("ev") or 0), reverse=True)
    best = candidates[0]
    return {
        "module": "CUOTA_DEL_DIA",
        "model_status": st,
        "predictive": True,
        "selection": best.get("selection"),
        "pick": best,
        "headline": "CUOTA DEL DÍA",
        "market_attention": best.get("attention", {}).get("attention"),
    }

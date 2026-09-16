"""Build a combined price near a target. Disabled without model probabilities."""
from __future__ import annotations

from engine.combination import combine, families_correlated
from engine.model import MODEL_EVALUATED, MODEL_TRAINED, model_status
from engine.selection import NO_BET, select_opportunity
from engine.value import expected_value

READY_MODEL = {MODEL_TRAINED, MODEL_EVALUATED, "CALIBRATED"}


def _price(row: dict) -> float | None:
    try:
        o = float(row.get("decimal_odds"))
    except (TypeError, ValueError):
        return None
    return o if o > 1 else None


def construir_cuota(rows: list[dict], target: float, model_st: str | None = None) -> dict:
    st = model_st or model_status()["model_status"]
    try:
        tgt = float(target)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_target", "combination": None}
    if tgt <= 1:
        return {"ok": False, "error": "target_must_be_greater_than_1", "combination": None}
    if st not in READY_MODEL:
        return {
            "ok": False,
            "module": "CONSTRUIR_CUOTA",
            "model_status": st,
            "predictive": False,
            "combination": None,
            "headline": "NO HAY COMBINACIÓN DE CALIDAD — MODEL NOT READY / DATA INSUFFICIENT",
            "reason": "model_probability_null",
        }
    eligible = []
    for r in rows or []:
        sel = select_opportunity(r, st)
        if sel.get("selection") == NO_BET or sel.get("model_probability") is None:
            continue
        ev = expected_value(sel.get("model_probability"), sel.get("decimal_odds"))
        if ev.get("ev") is None or ev.get("ev") <= 0:
            continue
        px = _price(sel)
        if px is None:
            continue
        eligible.append({**sel, "ev": ev["ev"]})
    if not eligible:
        return {
            "ok": False,
            "module": "CONSTRUIR_CUOTA",
            "headline": f"NO HAY COMBINACIÓN DE CALIDAD PARA {tgt:.2f}",
            "reason": "no_positive_ev_selections",
            "combination": None,
        }
    eligible.sort(key=lambda x: x.get("ev") or 0, reverse=True)
    chosen = []
    prod = 1.0
    for row in eligible:
        if any(
            row.get("provider_event_id") == c.get("provider_event_id")
            and families_correlated(row.get("market_family"), c.get("market_family"))
            for c in chosen
        ):
            continue
        nxt = prod * float(row["decimal_odds"])
        if chosen and abs(nxt - tgt) > abs(prod - tgt) and prod >= tgt * 0.85:
            break
        chosen.append(row)
        prod = nxt
        if prod >= tgt:
            break
    combo = combine(chosen)
    if combo.get("status") != "OK" or combo.get("combined_probability") is None:
        # correlation unknown → do not force
        if not chosen:
            return {
                "ok": False,
                "headline": f"NO HAY COMBINACIÓN DE CALIDAD PARA {tgt:.2f}",
                "reason": combo.get("reason") or "correlation_unknown",
                "correlation": "UNKNOWN",
                "combination": None,
            }
        return {
            "ok": False,
            "headline": f"NO HAY COMBINACIÓN DE CALIDAD PARA {tgt:.2f}",
            "reason": "correlation_unknown_or_independence_not_assumed",
            "correlation": "UNKNOWN",
            "cuota_objetivo": tgt,
            "cuota_conseguida": prod if chosen else None,
            "n_selecciones": len(chosen),
            "combination": chosen,
            "note": "Existe la cuota objetivo, pero alcanzar esa cuota requeriría selecciones con calidad estadística insuficiente o correlación no modelada.",
        }
    return {
        "ok": True,
        "cuota_objetivo": tgt,
        "cuota_conseguida": prod,
        "diferencia": prod - tgt,
        "n_selecciones": len(chosen),
        "combination": chosen,
        "correlation": combo,
    }


import math

def build_market_target(rows: list[dict], target: float) -> dict:
    """Build a target-price combination from real market prices.
    No joint probability is claimed because independence/correlation is unknown.
    """
    try:
        tgt=float(target)
    except (TypeError, ValueError):
        return {"ok":False,"error":"invalid_target","combination":None}
    if tgt<=1:
        return {"ok":False,"error":"target_must_be_greater_than_1","combination":None}
    candidates=[]
    for r in rows or []:
        try: px=float(r.get("decimal_odds"))
        except (TypeError,ValueError): continue
        if px < 1.50 or r.get("market_readiness")=="NOT_READY": continue
        rr=dict(r); rr["market_probability"]=r.get("implied_probability")
        candidates.append(rr)
    candidates.sort(key=lambda r: (r.get("market_probability") or 0), reverse=True)
    # Beam search: keep the best few partial combinations by log-distance to target,
    # while requiring different provider events. This is bounded and avoids an
    # explosive combinations() search across hundreds of markets.
    beam=[(1.0, [])]
    max_items=6
    for _ in range(max_items):
        expanded=[]
        for prod, combo in beam:
            used={x.get("provider_event_id") for x in combo}
            for row in candidates[:80]:
                if row.get("provider_event_id") in used: continue
                px=float(row["decimal_odds"])
                newprod=prod*px
                newcombo=combo+[row]
                # Prefer close-to-target combinations; mildly reward higher market probability.
                dist=abs(math.log(max(newprod,1e-9)/tgt))
                prob_bonus=sum(x.get("market_probability") or 0 for x in newcombo)*0.02
                score=dist-prob_bonus
                expanded.append((score,newprod,newcombo))
        if not expanded: break
        expanded.sort(key=lambda x:x[0])
        seen=set(); beam=[]
        for score,prod,combo in expanded:
            key=tuple(sorted(x.get("provider_event_id") for x in combo))
            if key in seen: continue
            seen.add(key); beam.append((prod,combo))
            if len(beam)>=120: break
    options=[]
    for prod,combo in beam:
        if len(combo)<2: continue
        options.append((abs(math.log(prod/tgt)), -sum(x.get("market_probability") or 0 for x in combo), prod, combo))
    if not options:
        return {"ok":False,"module":"CONSTRUIR_CUOTA","mode":"MODO_MERCADO",
                "headline":f"NO HAY COMBINACIÓN REAL PARA {tgt:.2f}","reason":"no_independent_events","combination":None}
    _,_,prod,combo=min(options,key=lambda x:(x[0],x[1]))
    items=[dict(x) for x in combo]
    return {
        "ok":True,"module":"CONSTRUIR_CUOTA","mode":"MODO_MERCADO","predictive":False,
        "cuota_objetivo":tgt,"cuota_conseguida":prod,"diferencia":prod-tgt,
        "n_selecciones":len(items),"combination":items,
        "market_probability":None,"probability_source":"MARKET",
        "correlation":"UNKNOWN","joint_probability":None,
        "headline":f"COMBINACIÓN DE MERCADO · {prod:.2f}",
        "note":"Cuotas reales persistidas de OddsPapi/Betano. La probabilidad conjunta no se calcula porque la independencia/correlación no está validada."
    }

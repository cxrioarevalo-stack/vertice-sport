"""Mathematical bankroll/target simulation. Not a betting recommendation."""
from __future__ import annotations

import math

CONSERVADOR = "CONSERVADOR"
MODERADO = "MODERADO"
AGRESIVO = "AGRESIVO"

RISK_FRACTIONS = {
    CONSERVADOR: 0.10,
    MODERADO: 0.25,
    AGRESIVO: 0.50,
}


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def steps_to_target(capital: float, meta: float, cuota: float) -> dict:
    c, m, q = _f(capital), _f(meta), _f(cuota)
    if c is None or m is None or q is None:
        return {"ok": False, "error": "invalid_input", "steps": None, "path": []}
    if c <= 0 or m <= 0:
        return {"ok": False, "error": "capital_and_meta_must_be_positive", "steps": None, "path": []}
    if q <= 1:
        return {"ok": False, "error": "cuota_must_be_greater_than_1", "steps": None, "path": []}
    if c >= m:
        return {
            "ok": True,
            "already_met": True,
            "steps": 0,
            "path": [{"step": 0, "capital": c}],
            "final_capital": c,
            "disclaimer": "SIMULACIÓN MATEMÁTICA. No es garantía.",
        }
    n = math.ceil(math.log(m / c) / math.log(q))
    path = [{"step": 0, "capital": c}]
    val = c
    for i in range(1, n + 1):
        val = val * q
        path.append({"step": i, "capital": val})
    return {
        "ok": True,
        "already_met": False,
        "steps": n,
        "path": path,
        "final_capital": val,
        "disclaimer": "SIMULACIÓN MATEMÁTICA. Supone aciertos consecutivos. No es probabilidad real ni garantía.",
    }


def risk_plan(capital: float, nivel: str = MODERADO) -> dict:
    c = _f(capital)
    if c is None or c <= 0:
        return {"ok": False, "error": "invalid_capital"}
    key = (nivel or MODERADO).upper()
    if key not in RISK_FRACTIONS:
        key = MODERADO
    frac = RISK_FRACTIONS[key]
    exposed = c * frac
    reserve = c - exposed
    return {
        "ok": True,
        "label": "SIMULACIÓN DE GESTIÓN DE RIESGO",
        "nivel": key,
        "capital_total": c,
        "fraction_at_risk": frac,
        "capital_en_riesgo": exposed,
        "reserva_protegida": reserve,
        "monto_por_operacion": exposed,
        "drawdown_simulado_max": frac,
        "note": "Porcentajes ilustrativos, no una regla universal. No es martingala.",
    }


def meta_de_capital(capital: float, meta: float, cuota: float, nivel: str = MODERADO) -> dict:
    steps = steps_to_target(capital, meta, cuota)
    risk = risk_plan(capital, nivel)
    return {
        "module": "META_DE_CAPITAL",
        "simulation": True,
        "recommendation": False,
        "steps": steps,
        "risk": risk,
    }


def ruta_hacia_la_meta(capital: float, meta: float, cuota: float) -> dict:
    scenarios = {}
    for nivel in (CONSERVADOR, MODERADO, AGRESIVO):
        scenarios[nivel] = meta_de_capital(capital, meta, cuota, nivel)
    base = steps_to_target(capital, meta, cuota)
    return {
        "module": "RUTA_HACIA_LA_META",
        "simulation": True,
        "recommendation": False,
        "cuota_objetivo": _f(cuota),
        "steps_matematicos": base.get("steps"),
        "scenarios": scenarios,
        "disclaimer": "SIMULACIÓN. No convierte la calculadora en una apuesta.",
    }

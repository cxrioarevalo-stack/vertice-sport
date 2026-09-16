import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.capital import (
    AGRESIVO,
    CONSERVADOR,
    MODERADO,
    meta_de_capital,
    risk_plan,
    ruta_hacia_la_meta,
    steps_to_target,
)
from engine.daily import cuota_del_dia
from engine.model import MODEL_NOT_READY, MODEL_TRAINED
from engine.popularity import UNKNOWN, market_attention
from engine.selection import NO_BET
from engine.target_odds import construir_cuota
from engine.value import expected_value


def test_steps_1_50_to_100():
    r = steps_to_target(1, 100, 1.5)
    assert r["ok"] is True
    assert r["steps"] == math.ceil(math.log(100) / math.log(1.5))
    assert r["path"][0]["capital"] == 1
    assert abs(r["path"][1]["capital"] - 1.5) < 1e-9
    assert abs(r["path"][2]["capital"] - 2.25) < 1e-9
    assert r["final_capital"] >= 100


def test_steps_2_00():
    r = steps_to_target(1, 16, 2)
    assert r["steps"] == 4
    assert r["final_capital"] == 16


def test_capital_already_above_meta():
    r = steps_to_target(200, 100, 1.5)
    assert r["steps"] == 0
    assert r["already_met"] is True


def test_cuota_invalid():
    assert steps_to_target(1, 100, 1)["ok"] is False
    assert steps_to_target(1, 100, 0.9)["ok"] is False


def test_risk_levels_reserve():
    c = risk_plan(100, CONSERVADOR)
    m = risk_plan(100, MODERADO)
    a = risk_plan(100, AGRESIVO)
    assert c["reserva_protegida"] == 90
    assert m["reserva_protegida"] == 75
    assert a["reserva_protegida"] == 50
    assert m["label"] == "SIMULACIÓN DE GESTIÓN DE RIESGO"


def test_meta_module_is_simulation():
    r = meta_de_capital(1, 100, 1.5, MODERADO)
    assert r["simulation"] is True
    assert r["recommendation"] is False


def test_ruta_scenarios():
    r = ruta_hacia_la_meta(1, 100, 5)
    assert r["steps_matematicos"] == 3
    assert set(r["scenarios"]) == {CONSERVADOR, MODERADO, AGRESIVO}


def test_popularity_unknown_without_volume():
    a = market_attention({"decimal_odds": 1.5})
    assert a["attention"] == UNKNOWN
    assert a["implies_failure"] is False


def test_popularity_when_share_present():
    a = market_attention({"ticket_share": 0.8})
    assert a["attention"] == "EXTREME"
    assert a["implies_failure"] is False


def test_daily_not_ready():
    d = cuota_del_dia([{"decimal_odds": 1.57}], MODEL_NOT_READY)
    assert d["pick"] is None
    assert d["selection"] == NO_BET
    assert "NO BET TODAY" in d["headline"]
    assert d["predictive"] is False


def test_daily_ready_but_no_quality():
    d = cuota_del_dia([], MODEL_TRAINED)
    assert d["pick"] is None
    assert d["selection"] == NO_BET


def test_construir_not_ready():
    r = construir_cuota([{"decimal_odds": 2.0}], 5, MODEL_NOT_READY)
    assert r["combination"] is None
    assert "MODEL NOT READY" in r["headline"]


def test_construir_no_quality():
    r = construir_cuota([], 5.0, MODEL_TRAINED)
    assert r["ok"] is False
    assert "NO HAY COMBINACIÓN" in r["headline"]


def test_ev_null_without_model():
    assert expected_value(None, 1.9)["ev"] is None


def test_product_line_semantics_untouched():
    from engine.product_line import resolve_product_line
    v, st = resolve_product_line("1010", {"market_name": "Over Under", "catalog_handicap": 2.5, "market_type": "totals"})
    assert v == 2.5
    assert st == "CATALOG_PRODUCT"


def test_integrity_high_excludes():
    from engine.selection import select_opportunity
    row = {"integrity_level": "HIGH", "decimal_odds": 1.8, "phase": "PREMATCH"}
    s = select_opportunity(row)
    assert s["selection"] == NO_BET


def test_integrity_critical_excludes():
    from engine.selection import select_opportunity
    row = {"integrity_level": "CRITICAL", "decimal_odds": 1.8, "phase": "PREMATCH"}
    s = select_opportunity(row)
    assert s["selection"] == NO_BET


def test_correlation_unknown_blocks_combo():
    from engine.combination import combine
    c = combine([
        {"model_probability": 0.6, "market_family": "1X2"},
        {"model_probability": 0.55, "market_family": "OVER_UNDER"},
    ])
    assert c["combined_probability"] is None
    assert c["assumed_independence"] is False


def test_drawdown_field_present():
    r = risk_plan(100, "MODERADO")
    assert r["drawdown_simulado_max"] == 0.25

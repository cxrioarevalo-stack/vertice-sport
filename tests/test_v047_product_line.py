import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.product_line import (
    STATUS_AMBIGUOUS,
    STATUS_MISSING,
    STATUS_NONE,
    STATUS_PRODUCT,
    annotate_product_line,
    resolve_product_line,
)


def test_ou_1010_is_catalog_product_25():
    v, s = resolve_product_line("1010", {
        "market_type": "totals",
        "market_name": "Over Under Full Time",
        "catalog_handicap": 2.5,
    })
    assert v == 2.5 and s == STATUS_PRODUCT


def test_1x2_101_has_no_product_line():
    v, s = resolve_product_line("101", {
        "market_type": "1x2",
        "market_name": "Full Time Result",
        "catalog_handicap": 0.0,
    })
    assert v is None and s == STATUS_NONE


def test_missing_catalog():
    v, s = resolve_product_line("1010", None)
    assert v is None and s == STATUS_MISSING


def test_ah_zero_ambiguous_without_explicit_name():
    v, s = resolve_product_line("10604", {
        "market_type": "spreads",
        "market_name": "Asian Handicap First Half",
        "catalog_handicap": 0.0,
    })
    assert v is None and s == STATUS_AMBIGUOUS


def test_ah_zero_ok_when_name_says_zero():
    v, s = resolve_product_line("10604", {
        "market_type": "spreads",
        "market_name": "Asian Handicap 0",
        "catalog_handicap": 0.0,
    })
    assert v == 0.0 and s == STATUS_PRODUCT


def test_name_handicap_conflict_ambiguous():
    v, s = resolve_product_line("1010", {
        "market_type": "totals",
        "market_name": "Over Under 1.5",
        "catalog_handicap": 2.5,
    })
    assert v is None and s == STATUS_AMBIGUOUS


def test_annotate_never_sets_fixture_line():
    row = {
        "market_id": "1010",
        "market_type": "totals",
        "market_name_official": "Over Under Full Time",
        "catalog_handicap": 2.5,
        "fixture_line": None,
        "line": None,
    }
    out = annotate_product_line(row)
    assert out["product_line"] == 2.5
    assert out["product_line_status"] == STATUS_PRODUCT
    assert out["fixture_line"] is None
    assert row["fixture_line"] is None


def test_eh_and_team_total():
    v, s = resolve_product_line("10137", {
        "market_type": "spreads-european",
        "market_name": "European Handicap",
        "catalog_handicap": 1.0,
    })
    assert v == 1.0 and s == STATUS_PRODUCT
    v, s = resolve_product_line("10226", {
        "market_type": "teamtotals-team1",
        "market_name": "Over Under Team 1",
        "catalog_handicap": 1.5,
    })
    assert v == 1.5 and s == STATUS_PRODUCT

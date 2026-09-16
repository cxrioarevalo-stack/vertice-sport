import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.market_normalize import (
    CONDITIONAL,
    NOT_READY,
    READY,
    market_identity,
    normalize_market,
    parse_decimal_odds,
)
from engine.product_line import STATUS_AMBIGUOUS, STATUS_PRODUCT


def _row(**kw):
    base = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "market_id": "101",
        "outcome_id": "101",
        "market_name_official": "Full Time Result",
        "outcome_name_official": "1",
        "market_type": "1x2",
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 1.90,
        "fixture_line": None,
        "catalog_handicap": None,
        "snapshot_id": 11,
        "match_id": None,
        "observed_at": "2026-09-09T12:00:00+00:00",
        "bookmaker": "betano",
    }
    base.update(kw)
    return base


def test_valid_odds():
    assert parse_decimal_odds(1.90) == 1.90
    n = normalize_market(_row())
    assert n["decimal_odds_valid"] == 1.90
    assert n["implied_probability_source"] == "MARKET"
    assert abs(n["implied_probability"] - 1 / 1.90) < 1e-12


def test_invalid_odds():
    for bad in (None, 0, -2, 1.0, "abc"):
        assert parse_decimal_odds(bad) is None
    n = normalize_market(_row(decimal_odds="nope"))
    assert n["decimal_odds_valid"] is None
    assert n["implied_probability"] is None
    assert n["market_readiness"] == NOT_READY


def test_product_line_not_copied_to_fixture():
    n = normalize_market(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        catalog_handicap=2.5, fixture_line=None,
    ))
    assert n["product_line"] == 2.5
    assert n["product_line_status"] == STATUS_PRODUCT
    assert n["fixture_line"] is None
    assert n["catalog_handicap"] == 2.5


def test_ou_blocked_without_product_line():
    n = normalize_market(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        catalog_handicap=None,
    ))
    assert n["market_readiness"] == NOT_READY


def test_ah_blocked_when_ambiguous():
    n = normalize_market(_row(
        market_id="10604", market_type="spreads",
        market_name_official="Asian Handicap First Half",
        catalog_handicap=0.0, period_official="p1",
    ))
    assert n["product_line_status"] == STATUS_AMBIGUOUS
    assert n["market_readiness"] == NOT_READY


def test_1x2_dc_dnb_btts_ready():
    for typ, mid in (("1x2", "101"), ("doublechance", "101902"),
                     ("drawnobet", "10214"), ("bothteamsscore", "104")):
        n = normalize_market(_row(market_type=typ, market_id=mid, catalog_handicap=0.0))
        assert n["market_readiness"] == READY, typ


def test_period_unknown_blocks():
    n = normalize_market(_row(period_official=None))
    assert n["period_canonical"] == "UNKNOWN"
    assert n["market_readiness"] == NOT_READY


def test_unknown_not_ready():
    n = normalize_market(_row(market_type="11-overs", market_name_official="11 Overs"))
    assert n["market_readiness"] == NOT_READY


def test_player_prop_missing():
    n = normalize_market(_row(market_type="players-shots", player_id=None, catalog_handicap=None))
    assert n["market_readiness"] == NOT_READY


def test_snapshot_and_null_match():
    n = normalize_market(_row(snapshot_id=77, match_id=None))
    assert n["snapshot_id"] == 77
    assert n["match_id"] is None
    assert n["as_of"] == "2026-09-09T12:00:00+00:00"


def test_distinct_market_ids():
    a = normalize_market(_row(market_id="1010", market_type="totals", catalog_handicap=2.5,
                              market_name_official="Over Under Full Time", snapshot_id=1))
    b = normalize_market(_row(market_id="1012", market_type="totals", catalog_handicap=3.5,
                              market_name_official="Over Under Full Time", snapshot_id=2))
    assert market_identity(a) != market_identity(b)
    assert a["market_id"] != b["market_id"]

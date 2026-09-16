import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VERTICE_TZ", "America/New_York")

from engine.market_normalize import (
    FAMILY_1X2,
    FAMILY_ASIAN_HANDICAP,
    FAMILY_BTTS,
    FAMILY_EUROPEAN_HANDICAP,
    FAMILY_OVER_UNDER,
    FAMILY_TEAM_TOTAL,
    FAMILY_UNKNOWN,
    normalize_market,
)
from engine.product_line import STATUS_NONE, STATUS_PRODUCT


def _row(**kw):
    base = {
        "provider_code": "oddspapi",
        "provider_event_id": "fx-1",
        "market_id": "x",
        "outcome_id": "y",
        "market_name_official": None,
        "market_type": None,
        "period_official": "fulltime",
        "phase": "PREMATCH",
        "decimal_odds": 1.9,
        "fixture_line": None,
        "catalog_handicap": None,
        "snapshot_id": 1,
        "match_id": None,
    }
    base.update(kw)
    return base


def test_ou_product_line():
    n = normalize_market(_row(
        market_id="1010", market_type="totals",
        market_name_official="Over Under Full Time",
        catalog_handicap=2.5,
    ))
    assert n["market_family"] == FAMILY_OVER_UNDER
    assert n["product_line"] == 2.5
    assert n["product_line_status"] == STATUS_PRODUCT
    assert n["period_canonical"] == "fulltime"
    assert n["phase"] == "PREMATCH"
    assert n["fixture_line"] is None


def test_team_total_product_line():
    n = normalize_market(_row(
        market_id="10226", market_type="teamtotals-team1",
        market_name_official="Over Under Team 1",
        catalog_handicap=1.5,
    ))
    assert n["market_family"] == FAMILY_TEAM_TOTAL
    assert n["product_line"] == 1.5


def test_ah_product_line():
    n = normalize_market(_row(
        market_id="10600", market_type="spreads",
        market_name_official="Asian Handicap First Half",
        catalog_handicap=-0.5, period_official="p1",
    ))
    assert n["market_family"] == FAMILY_ASIAN_HANDICAP
    assert n["product_line"] == -0.5
    assert n["period_canonical"] == "p1"


def test_eh_product_line():
    n = normalize_market(_row(
        market_id="10137", market_type="spreads-european",
        market_name_official="European Handicap",
        catalog_handicap=1.0,
    ))
    assert n["market_family"] == FAMILY_EUROPEAN_HANDICAP
    assert n["product_line"] == 1.0


def test_1x2_no_product_line():
    n = normalize_market(_row(
        market_id="101", market_type="1x2",
        market_name_official="Full Time Result",
        catalog_handicap=0.0,
    ))
    assert n["market_family"] == FAMILY_1X2
    assert n["product_line"] is None
    assert n["product_line_status"] == STATUS_NONE


def test_btts_no_product_line():
    n = normalize_market(_row(
        market_id="104", market_type="bothteamsscore",
        market_name_official="Both Teams To Score",
        catalog_handicap=0.0,
    ))
    assert n["market_family"] == FAMILY_BTTS
    assert n["product_line"] is None


def test_periods_p1_p2():
    a = normalize_market(_row(market_type="1x2", period_official="p1"))
    b = normalize_market(_row(market_type="1x2", period_official="p2", phase="LIVE"))
    assert a["period_canonical"] == "p1" and a["phase"] == "PREMATCH"
    assert b["period_canonical"] == "p2" and b["phase"] == "LIVE"


def test_unknown_type():
    n = normalize_market(_row(market_type="11-overs", market_name_official="11 Overs"))
    assert n["market_family"] == FAMILY_UNKNOWN
    assert n["market_type_canonical"] == "UNKNOWN"


def test_fixture_line_untouched():
    n = normalize_market(_row(market_type="totals", catalog_handicap=2.5, fixture_line=None))
    assert n["fixture_line"] is None


def test_snapshot_and_null_match_preserved():
    n = normalize_market(_row(snapshot_id=99, match_id=None, market_type="1x2"))
    assert n["snapshot_id"] == 99
    assert n["match_id"] is None
    assert n["provider_event_id"] == "fx-1"

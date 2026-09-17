from providers.odds.oddspapi import parse_market_outcomes, parse_price


def test_parse_price_rejects_invalid_and_non_decimal_values():
    assert parse_price(None) is None
    assert parse_price("") is None
    assert parse_price("not-a-number") is None
    assert parse_price(1.0) is None
    assert parse_price(1.01) == 1.01


def test_parse_market_outcomes_ignores_malformed_nodes():
    market = {
        "bookmakerMarketId": "m-1",
        "outcomes": {
            "home": {"players": {"p1": {"price": "1.80"}, "bad": "invalid"}},
            "away": "invalid",
        },
    }
    rows = parse_market_outcomes("winner", market)
    assert len(rows) == 1
    assert rows[0]["outcome_id"] == "home"
    assert rows[0]["price"] == 1.8


def test_parse_market_outcomes_does_not_infer_missing_price():
    market = {"outcomes": {"home": {"players": {"p1": {"line": 1.5}}}}}
    assert parse_market_outcomes("totals", market) == []

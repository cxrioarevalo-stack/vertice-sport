"""Read-time historical observations from stored snapshots. No writes."""
from __future__ import annotations

from db import get_conn
from engine.settlement import UNKNOWN, settle_observation


def build_observation(row: dict, result: dict | None = None, context: dict | None = None) -> dict:
    ctx = context or {}
    settled = settle_observation(row, result)
    as_of = settled.get("observed_at") or settled.get("as_of") or settled.get("source_updated_at")
    return {
        "sport_key": settled.get("sport_key") or ctx.get("sport_key") or "football",
        "match_id": settled.get("match_id"),
        "provider_event_id": settled.get("provider_event_id"),
        "competition": ctx.get("competition"),
        "home_team": ctx.get("home_team"),
        "away_team": ctx.get("away_team"),
        "kickoff_utc": ctx.get("kickoff_utc"),
        "market_family": settled.get("market_family"),
        "market_type_canonical": settled.get("market_type_canonical"),
        "period_canonical": settled.get("period_canonical"),
        "phase": settled.get("phase"),
        "product_line": settled.get("product_line"),
        "product_line_status": settled.get("product_line_status"),
        "fixture_line": settled.get("fixture_line"),
        "outcome_id": settled.get("outcome_id"),
        "outcome_name": settled.get("outcome_name_official") or settled.get("original_outcome_name"),
        "bookmaker": settled.get("bookmaker"),
        "decimal_odds": settled.get("decimal_odds_valid") or settled.get("decimal_odds"),
        "implied_probability": settled.get("implied_probability"),
        "implied_probability_source": settled.get("implied_probability_source") or "MARKET",
        "market_implied_probability": settled.get("implied_probability"),
        "model_probability": None,
        "ev": None,
        "snapshot_id": settled.get("snapshot_id"),
        "as_of_utc": as_of,
        "settlement_result": settled.get("historical_outcome") or UNKNOWN,
        "settlement_reason": settled.get("settlement_reason"),
        "data_completeness": settled.get("data_completeness") or "DATA_INSUFFICIENT",
        "source": settled.get("provider_code") or "oddspapi",
        "provider_code": settled.get("provider_code"),
        "market_id": settled.get("market_id"),
        "result_used_for": "settlement_only" if result else None,
    }


def load_historical_observations(limit: int | None = None) -> list[dict]:
    from engine.historical_match import load_bbc_match_index, resolve_historical_match

    conn = get_conn()
    try:
        sql = """
            SELECT v.*,
                   e.home_team AS ev_home, e.away_team AS ev_away,
                   e.competition AS ev_comp, e.kickoff_utc AS ev_kickoff
            FROM odds_normalized_v043 v
            LEFT JOIN odds_provider_events e
              ON e.provider_code=v.provider_code AND e.provider_event_id=v.provider_event_id
            ORDER BY v.id
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    bbc_index = load_bbc_match_index()
    resolved_cache: dict[str, dict] = {}
    out = []
    for raw in rows:
        r = dict(raw)
        key = str(r.get("provider_event_id") or "")
        if key not in resolved_cache:
            provider = {
                "home_team": r.get("ev_home"),
                "away_team": r.get("ev_away"),
                "competition": r.get("ev_comp"),
                "kickoff_utc": r.get("ev_kickoff"),
            }
            resolved_cache[key] = resolve_historical_match(provider, bbc_index)
        resolved = resolved_cache[key]
        bbc = resolved.get("bbc") or {}
        result = None
        if bbc.get("home_score") is not None and bbc.get("away_score") is not None:
            result = {"home_score": bbc["home_score"], "away_score": bbc["away_score"]}
        ctx = {
            "home_team": r.get("ev_home") or bbc.get("home_team"),
            "away_team": r.get("ev_away") or bbc.get("away_team"),
            "competition": r.get("ev_comp") or bbc.get("competition"),
            "kickoff_utc": r.get("ev_kickoff") or bbc.get("kickoff_utc"),
            "sport_key": r.get("sport_key"),
        }
        obs = build_observation(r, result, ctx)
        obs["stored_match_id"] = r.get("match_id")
        obs["match_id"] = resolved.get("match_id")
        obs["match_link_state"] = resolved.get("state")
        obs["match_link_reason"] = resolved.get("reason")
        out.append(obs)
    return out

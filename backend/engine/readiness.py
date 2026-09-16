"""Deterministic V1.0 readiness. No training. Settled odds required."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from engine.evaluation import evaluate, odds_bucket
from engine.historical_dataset import load_historical_observations
from engine.odds_match import parse_kickoff

NOT_READY = "NOT_READY"
PARTIALLY_READY = "PARTIALLY_READY"
READY_FOR_MODEL_DEVELOPMENT = "READY_FOR_MODEL_DEVELOPMENT"
READY_FOR_BACKTEST = "READY_FOR_BACKTEST"

MIN_SETTLED_NON_VOID = 200
MIN_DISTINCT_DAYS = 30
MIN_DISTINCT_WEEKS = 4
MIN_MARKET_FAMILIES = 3
MIN_TEAMS = 20
MIN_COMPETITIONS = 5
IMBALANCE_RATIO = 0.95


def _aware(dt):
    return dt


def temporal_from_dates(isos: list[str]) -> dict:
    dts = []
    for raw in isos:
        d = parse_kickoff(raw)
        if d:
            dts.append(d)
    if not dts:
        return {
            "earliest": None,
            "latest": None,
            "distinct_days": 0,
            "distinct_weeks": 0,
            "distinct_months": 0,
        }
    days = {d.date() for d in dts}
    weeks = {(d.isocalendar()[0], d.isocalendar()[1]) for d in dts}
    months = {(d.year, d.month) for d in dts}
    return {
        "earliest": min(dts).isoformat(),
        "latest": max(dts).isoformat(),
        "distinct_days": len(days),
        "distinct_weeks": len(weeks),
        "distinct_months": len(months),
    }


def walk_forward_possible(distinct_days: int, settled: int) -> dict:
    ok = distinct_days >= MIN_DISTINCT_DAYS and settled >= MIN_SETTLED_NON_VOID
    return {
        "possible": ok,
        "method": "chronological",
        "random_split": False,
        "reason": None if ok else "insufficient_temporal_or_settled_data",
    }


def assess_readiness(observations: list[dict] | None = None, finished_meta: dict | None = None) -> dict:
    rows = observations if observations is not None else load_historical_observations()
    ev = evaluate(rows)
    settled_nv = ev["WON"] + ev["LOST"]
    finished_meta = finished_meta or {}

    kickoffs = [r.get("kickoff_utc") for r in rows if r.get("kickoff_utc")]
    as_ofs = [r.get("as_of_utc") for r in rows if r.get("as_of_utc")]
    temp_odds = temporal_from_dates(kickoffs or as_ofs)
    temp_bbc = temporal_from_dates(finished_meta.get("kickoffs") or [])

    families_settled = {}
    for fam, counts in ev.get("by_market_family", {}).items():
        n = counts.get("WON", 0) + counts.get("LOST", 0)
        if n:
            families_settled[fam] = n

    buckets_settled = {}
    for b, counts in ev.get("by_odds_bucket", {}).items():
        n = counts.get("WON", 0) + counts.get("LOST", 0)
        if n:
            buckets_settled[b] = n

    won, lost = ev["WON"], ev["LOST"]
    imbalance = False
    if settled_nv:
        top = max(won, lost) / settled_nv
        imbalance = top >= IMBALANCE_RATIO

    blockers = []
    warnings = []
    if settled_nv < MIN_SETTLED_NON_VOID:
        blockers.append(f"settled_non_void={settled_nv} < {MIN_SETTLED_NON_VOID}")
    if temp_odds["distinct_days"] < MIN_DISTINCT_DAYS and settled_nv:
        blockers.append(f"odds_days={temp_odds['distinct_days']} < {MIN_DISTINCT_DAYS}")
    elif settled_nv == 0:
        blockers.append("no_settled_oddspapi_observations")
    if len(families_settled) < MIN_MARKET_FAMILIES and settled_nv:
        warnings.append(f"settled_families={len(families_settled)} < {MIN_MARKET_FAMILIES}")
    if imbalance:
        warnings.append("OUTCOME_IMBALANCE")
    if finished_meta.get("finished_matches", 0) and settled_nv == 0:
        warnings.append("bbc_finished_exists_but_odds_unsettled")

    if blockers:
        state = NOT_READY
    elif warnings:
        state = PARTIALLY_READY
    else:
        state = READY_FOR_MODEL_DEVELOPMENT

    wf = walk_forward_possible(temp_odds["distinct_days"], settled_nv)

    flags = []
    for r in rows[:0]:
        pass
    if ev["UNKNOWN"] == ev["total"] and ev["total"]:
        flags.append("all_observations_unsettled")

    return {
        "state": state,
        "training_readiness": state,
        "backtest_readiness": READY_FOR_BACKTEST if wf["possible"] else NOT_READY,
        "thresholds": {
            "min_settled_non_void": MIN_SETTLED_NON_VOID,
            "min_distinct_days": MIN_DISTINCT_DAYS,
            "min_distinct_weeks": MIN_DISTINCT_WEEKS,
            "min_market_families": MIN_MARKET_FAMILIES,
            "min_teams": MIN_TEAMS,
            "min_competitions": MIN_COMPETITIONS,
            "imbalance_ratio": IMBALANCE_RATIO,
        },
        "metrics": {
            "finished_matches": finished_meta.get("finished_matches"),
            "unique_teams": finished_meta.get("unique_teams"),
            "unique_competitions": finished_meta.get("unique_competitions"),
            "total_observations": ev["total"],
            "settled_odds_observations": ev["resolved"],
            "resolved_won": ev["WON"],
            "resolved_lost": ev["LOST"],
            "resolved_void": ev["VOID"],
            "unknown_observations": ev["UNKNOWN"],
            "settled_non_void": settled_nv,
            "observations_by_market_family": ev.get("by_market_family"),
            "observations_by_odds_bucket": ev.get("by_odds_bucket"),
            "settled_by_market_family": families_settled,
            "settled_by_odds_bucket": buckets_settled,
        },
        "temporal_coverage_odds": temp_odds,
        "temporal_coverage_bbc": temp_bbc,
        "walk_forward": wf,
        "blockers": blockers,
        "warnings": warnings,
        "flags": flags,
        "feature_groups": {
            "REQUIRED": ["decimal_odds", "implied_probability", "as_of_utc", "settlement"],
            "OPTIONAL": ["goals_history", "form", "rest", "congestion"],
            "UNAVAILABLE": ["xg", "shots", "possession", "corners_event", "cards_event", "injuries", "lineups", "player_stats"],
        },
        "model_probability": None,
        "ev": None,
        "recommended_next_stage": "accumulate_finished_bbc_scores_for_linked_odds_events",
    }


def bbc_finished_meta() -> dict:
    from db import get_conn
    conn = get_conn()
    try:
        fin = conn.execute(
            """SELECT kickoff_utc FROM matches
               WHERE status='FINISHED' AND home_score IS NOT NULL AND away_score IS NOT NULL"""
        ).fetchall()
        teams = conn.execute(
            """SELECT COUNT(DISTINCT team) FROM (
                 SELECT home_team_id AS team FROM matches WHERE status='FINISHED'
                 UNION
                 SELECT away_team_id FROM matches WHERE status='FINISHED')"""
        ).fetchone()[0]
        comps = conn.execute(
            "SELECT COUNT(DISTINCT competition_id) FROM matches WHERE status='FINISHED'"
        ).fetchone()[0]
        kickoffs = [r[0] for r in fin]
        return {
            "finished_matches": len(fin),
            "unique_teams": teams,
            "unique_competitions": comps,
            "kickoffs": kickoffs,
        }
    finally:
        conn.close()


def current_readiness() -> dict:
    return assess_readiness(None, bbc_finished_meta())

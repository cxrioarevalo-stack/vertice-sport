"""Read-time prediction-time features. No estimates, no result leakage, no model."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from engine.odds_match import parse_kickoff
from engine.product_line import STATUS_PRODUCT

FEATURE_VERSION = "v0.9.0"

REAL = "REAL"
MISSING = "MISSING"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
NOT_APPLICABLE = "NOT_APPLICABLE"
AVAILABLE = "AVAILABLE"

MIN_RATE = 3
MIN_FORM3 = 3
MIN_FORM5 = 5
MIN_FORM10 = 10


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_as_of(value: str | None) -> datetime | None:
    return _aware(parse_kickoff(value))


def feat(name: str, value: Any, source: str, as_of: str | None, status: str,
         sample_size: int | None = None) -> dict:
    return {
        "name": name,
        "value": value,
        "source": source,
        "as_of_utc": as_of,
        "status": status,
        "sample_size": sample_size,
        "definition_version": FEATURE_VERSION,
    }


def _fint(v) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def load_finished_matches() -> list[dict]:
    from db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT m.id, m.kickoff_utc, m.home_score, m.away_score,
                   th.name AS home_team, ta.name AS away_team,
                   th.id AS home_team_id, ta.id AS away_team_id,
                   co.name AS competition
            FROM matches m
            JOIN teams th ON th.id=m.home_team_id
            JOIN teams ta ON ta.id=m.away_team_id
            LEFT JOIN competitions co ON co.id=m.competition_id
            WHERE m.status='FINISHED'
              AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def prior_team_matches(team_id: int | None, team_name: str | None,
                       history: list[dict], as_of: datetime,
                       exclude_match_id: int | None) -> list[dict]:
    out = []
    tname = (team_name or "").strip().lower()
    for m in history:
        if exclude_match_id and m.get("id") == exclude_match_id:
            continue
        ko = parse_as_of(m.get("kickoff_utc"))
        if not ko or ko >= as_of:
            continue
        hid, aid = m.get("home_team_id"), m.get("away_team_id")
        hn, an = (m.get("home_team") or "").lower(), (m.get("away_team") or "").lower()
        side = None
        if team_id and hid == team_id:
            side = "home"
        elif team_id and aid == team_id:
            side = "away"
        elif tname and hn == tname:
            side = "home"
        elif tname and an == tname:
            side = "away"
        else:
            continue
        hg, ag = _fint(m.get("home_score")), _fint(m.get("away_score"))
        if hg is None or ag is None:
            continue
        gf, ga = (hg, ag) if side == "home" else (ag, hg)
        if side == "home":
            pts = 3 if hg > ag else (1 if hg == ag else 0)
        else:
            pts = 3 if ag > hg else (1 if hg == ag else 0)
        out.append({
            "id": m.get("id"),
            "kickoff_utc": m.get("kickoff_utc"),
            "kickoff": ko,
            "side": side,
            "gf": gf,
            "ga": ga,
            "pts": pts,
            "btts": hg > 0 and ag > 0,
            "total": hg + ag,
            "home_win": hg > ag,
            "draw": hg == ag,
            "away_win": hg < ag,
        })
    out.sort(key=lambda x: x["kickoff"])
    return out


def _avg(vals: list[float], need: int, name: str, source: str, as_of: str) -> dict:
    if len(vals) < need:
        return feat(name, None, source, as_of, INSUFFICIENT_HISTORY, len(vals))
    return feat(name, sum(vals) / len(vals), source, as_of, AVAILABLE, len(vals))


def _rate(flags: list[bool], need: int, name: str, source: str, as_of: str) -> dict:
    if len(flags) < need:
        return feat(name, None, source, as_of, INSUFFICIENT_HISTORY, len(flags))
    return feat(name, sum(1 for x in flags if x) / len(flags), source, as_of, AVAILABLE, len(flags))


def _window(rows: list[dict], n: int) -> list[dict]:
    return rows[-n:] if rows else []


def team_historical_features(prefix: str, rows: list[dict], as_of: str) -> dict[str, dict]:
    src = "bbc_finished"
    feats = {}
    feats[f"{prefix}_n_prior"] = feat(f"{prefix}_n_prior", len(rows), src, as_of,
                                      AVAILABLE if rows else INSUFFICIENT_HISTORY, len(rows))
    feats[f"{prefix}_goals_scored_avg"] = _avg([r["gf"] for r in rows], MIN_RATE, f"{prefix}_goals_scored_avg", src, as_of)
    feats[f"{prefix}_goals_conceded_avg"] = _avg([r["ga"] for r in rows], MIN_RATE, f"{prefix}_goals_conceded_avg", src, as_of)
    home = [r for r in rows if r["side"] == "home"]
    away = [r for r in rows if r["side"] == "away"]
    feats[f"{prefix}_home_goals_scored_avg"] = _avg([r["gf"] for r in home], MIN_RATE, f"{prefix}_home_goals_scored_avg", src, as_of)
    feats[f"{prefix}_home_goals_conceded_avg"] = _avg([r["ga"] for r in home], MIN_RATE, f"{prefix}_home_goals_conceded_avg", src, as_of)
    feats[f"{prefix}_away_goals_scored_avg"] = _avg([r["gf"] for r in away], MIN_RATE, f"{prefix}_away_goals_scored_avg", src, as_of)
    feats[f"{prefix}_away_goals_conceded_avg"] = _avg([r["ga"] for r in away], MIN_RATE, f"{prefix}_away_goals_conceded_avg", src, as_of)
    feats[f"{prefix}_total_goals_avg"] = _avg([r["total"] for r in rows], MIN_RATE, f"{prefix}_total_goals_avg", src, as_of)
    if prefix == "home":
        feats["home_win_rate"] = _rate([r["home_win"] for r in home], MIN_RATE, "home_win_rate", src, as_of)
        feats["home_draw_rate"] = _rate([r["draw"] for r in home], MIN_RATE, "home_draw_rate", src, as_of)
    if prefix == "away":
        feats["away_win_rate"] = _rate([r["away_win"] for r in away], MIN_RATE, "away_win_rate", src, as_of)
        feats["away_draw_rate"] = _rate([r["draw"] for r in away], MIN_RATE, "away_draw_rate", src, as_of)
    feats[f"{prefix}_btts_rate"] = _rate([r["btts"] for r in rows], MIN_RATE, f"{prefix}_btts_rate", src, as_of)
    feats[f"{prefix}_over_15_rate"] = _rate([r["total"] > 1.5 for r in rows], MIN_RATE, f"{prefix}_over_15_rate", src, as_of)
    feats[f"{prefix}_over_25_rate"] = _rate([r["total"] > 2.5 for r in rows], MIN_RATE, f"{prefix}_over_25_rate", src, as_of)
    feats[f"{prefix}_under_25_rate"] = _rate([r["total"] < 2.5 for r in rows], MIN_RATE, f"{prefix}_under_25_rate", src, as_of)
    for n, need in ((3, MIN_FORM3), (5, MIN_FORM5), (10, MIN_FORM10)):
        w = _window(rows, n)
        pts_name = f"{prefix}_last_{n}_points"
        gf_name = f"{prefix}_last_{n}_goals_for"
        ga_name = f"{prefix}_last_{n}_goals_against"
        if len(rows) < need:
            feats[pts_name] = feat(pts_name, None, src, as_of, INSUFFICIENT_HISTORY, len(rows))
            feats[gf_name] = feat(gf_name, None, src, as_of, INSUFFICIENT_HISTORY, len(rows))
            feats[ga_name] = feat(ga_name, None, src, as_of, INSUFFICIENT_HISTORY, len(rows))
        else:
            feats[pts_name] = feat(pts_name, sum(x["pts"] for x in w), src, as_of, AVAILABLE, n)
            feats[gf_name] = feat(gf_name, sum(x["gf"] for x in w), src, as_of, AVAILABLE, n)
            feats[ga_name] = feat(ga_name, sum(x["ga"] for x in w), src, as_of, AVAILABLE, n)
    if not rows:
        feats[f"{prefix}_days_since_last_match"] = feat(f"{prefix}_days_since_last_match", None, src, as_of, MISSING, 0)
        feats[f"{prefix}_matches_last_7_days"] = feat(f"{prefix}_matches_last_7_days", None, src, as_of, MISSING, 0)
        feats[f"{prefix}_matches_last_14_days"] = feat(f"{prefix}_matches_last_14_days", None, src, as_of, MISSING, 0)
    else:
        last = rows[-1]["kickoff"]
        as_dt = parse_as_of(as_of)
        days = (as_dt - last).total_seconds() / 86400.0 if as_dt else None
        feats[f"{prefix}_days_since_last_match"] = feat(
            f"{prefix}_days_since_last_match", days, src, as_of, AVAILABLE if days is not None else MISSING, 1
        )
        as_dt = parse_as_of(as_of)
        n7 = sum(1 for r in rows if as_dt and (as_dt - r["kickoff"]).total_seconds() <= 7 * 86400)
        n14 = sum(1 for r in rows if as_dt and (as_dt - r["kickoff"]).total_seconds() <= 14 * 86400)
        feats[f"{prefix}_matches_last_7_days"] = feat(f"{prefix}_matches_last_7_days", n7, src, as_of, AVAILABLE, n7)
        feats[f"{prefix}_matches_last_14_days"] = feat(f"{prefix}_matches_last_14_days", n14, src, as_of, AVAILABLE, n14)
    return feats


def context_features(match: dict, as_of: str) -> dict[str, dict]:
    src = "bbc_context"
    def ctx(name, val):
        return feat(name, val, src, as_of, REAL if val not in (None, "") else MISSING)

    return {
        "home_team": ctx("home_team", match.get("home_team")),
        "away_team": ctx("away_team", match.get("away_team")),
        "competition": ctx("competition", match.get("competition")),
        "kickoff_utc": ctx("kickoff_utc", match.get("kickoff_utc")),
        "sport_key": ctx("sport_key", match.get("sport_key") or "football"),
        "match_id": ctx("match_id", match.get("id") or match.get("match_id")),
    }


def market_features(market: dict | None, as_of: str) -> dict[str, dict]:
    m = market or {}
    src = "oddspapi"
    def mk(name, val, status=None):
        st = status or (REAL if val not in (None, "") else MISSING)
        return feat(name, val, src, as_of, st)

    odds = m.get("decimal_odds")
    implied = m.get("implied_probability")
    if implied is None and odds not in (None, "") :
        try:
            o = float(odds)
            implied = 1.0 / o if o > 1 else None
        except (TypeError, ValueError):
            implied = None
    pl = m.get("product_line")
    pl_st = m.get("product_line_status")
    return {
        "decimal_odds": mk("decimal_odds", odds),
        "implied_probability": mk("implied_probability", implied),
        "implied_probability_source": mk("implied_probability_source", "MARKET" if implied is not None else None),
        "market_family": mk("market_family", m.get("market_family")),
        "market_type_canonical": mk("market_type_canonical", m.get("market_type_canonical")),
        "period_canonical": mk("period_canonical", m.get("period_canonical") or m.get("period")),
        "phase": mk("phase", m.get("phase")),
        "product_line": mk("product_line", pl, REAL if pl is not None and pl_st == STATUS_PRODUCT else (MISSING if pl is None else REAL)),
        "product_line_status": mk("product_line_status", pl_st),
        "fixture_line": mk("fixture_line", m.get("fixture_line")),
        "bookmaker": mk("bookmaker", m.get("bookmaker")),
        "snapshot_id": mk("snapshot_id", m.get("snapshot_id")),
        "model_probability": feat("model_probability", None, "none", as_of, NOT_APPLICABLE),
        "ev": feat("ev", None, "none", as_of, NOT_APPLICABLE),
    }


def feature_hash(features: dict[str, dict]) -> str:
    payload = {k: {"value": v.get("value"), "status": v.get("status"), "sample_size": v.get("sample_size")}
               for k, v in sorted(features.items())}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_features(match: dict, as_of_utc: str, market_context: dict | None = None,
                   history: list[dict] | None = None) -> dict:
    as_dt = parse_as_of(as_of_utc)
    if not as_dt:
        raise ValueError("as_of_utc required")
    hist = history if history is not None else load_finished_matches()
    exclude = match.get("id") or match.get("match_id")
    home_rows = prior_team_matches(match.get("home_team_id"), match.get("home_team"), hist, as_dt, exclude)
    away_rows = prior_team_matches(match.get("away_team_id"), match.get("away_team"), hist, as_dt, exclude)
    features = {}
    features.update(context_features(match, as_of_utc))
    features.update(team_historical_features("home", home_rows, as_of_utc))
    features.update(team_historical_features("away", away_rows, as_of_utc))
    features.update(market_features(market_context, as_of_utc))
    return {
        "feature_version": FEATURE_VERSION,
        "feature_hash": feature_hash(features),
        "as_of_utc": as_of_utc,
        "features": features,
        "training_readiness": "NOT_READY",
        "model_probability": None,
        "ev": None,
        "home_prior_n": len(home_rows),
        "away_prior_n": len(away_rows),
    }

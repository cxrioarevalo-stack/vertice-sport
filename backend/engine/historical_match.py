"""Conservative historical BBC ↔ OddsPapi identity. Score is never a matching signal."""
from __future__ import annotations

from datetime import timezone

from engine.odds_match import match_event, norm_name, parse_kickoff

MATCHED = "MATCHED"
AMBIGUOUS = "AMBIGUOUS"
UNMATCHED = "UNMATCHED"

REASON_EXACT = "TEAM_TIME_EXACT"
REASON_TOLERANT = "TEAM_TIME_TOLERANT"
REASON_COMP = "TEAM_COMPETITION_TIME"
REASON_MULTI = "AMBIGUOUS_MULTIPLE_CANDIDATES"
REASON_NO_TEAM = "NO_TEAM_MATCH"
REASON_NO_TIME = "NO_TIME_MATCH"
REASON_MISSING = "MISSING_TEAM_DATA"
REASON_NONE = "NO_CANDIDATE"


def _aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _delta_minutes(a: str | None, b: str | None) -> float | None:
    t1, t2 = _aware(parse_kickoff(a)), _aware(parse_kickoff(b))
    if not t1 or not t2:
        return None
    return abs((t1 - t2).total_seconds()) / 60.0


def classify_pair(bbc: dict, provider: dict, *, exact_min: int = 15, tolerant_min: int = 60) -> tuple[str, str, int | None]:
    mid = bbc.get("id") or bbc.get("match_id")
    h1, a1 = norm_name(bbc.get("home_team")), norm_name(bbc.get("away_team"))
    h2, a2 = norm_name(provider.get("home_team")), norm_name(provider.get("away_team"))
    if not h1 or not a1 or not h2 or not a2:
        return UNMATCHED, REASON_MISSING, None
    ok, _score, why = match_event(bbc, provider, max_minutes=tolerant_min)
    if not ok:
        if "team names" in why or "reversed" in why or "low confidence" in why:
            return UNMATCHED, REASON_NO_TEAM, None
        if "kickoff differs" in why:
            return UNMATCHED, REASON_NO_TIME, None
        if "missing team" in why:
            return UNMATCHED, REASON_MISSING, None
        return UNMATCHED, REASON_NONE, None
    delta = _delta_minutes(bbc.get("kickoff_utc"), provider.get("kickoff_utc"))
    bbc_comp = norm_name(bbc.get("competition"))
    pe_comp = norm_name(provider.get("competition"))
    if delta is not None and delta <= exact_min:
        reason = REASON_COMP if bbc_comp and pe_comp and (bbc_comp in pe_comp or pe_comp in bbc_comp) else REASON_EXACT
        return MATCHED, reason, mid
    if delta is not None and delta <= tolerant_min:
        return MATCHED, REASON_TOLERANT, mid
    return UNMATCHED, REASON_NO_TIME, None


def resolve_historical_match(provider: dict, bbc_matches: list[dict], *, exact_min: int = 15, tolerant_min: int = 60) -> dict:
    hits = []
    for bbc in bbc_matches:
        state, reason, mid = classify_pair(bbc, provider, exact_min=exact_min, tolerant_min=tolerant_min)
        if state == MATCHED:
            hits.append((reason, mid, bbc))
    if len(hits) == 1:
        reason, mid, bbc = hits[0]
        return {
            "state": MATCHED,
            "reason": reason,
            "match_id": mid,
            "bbc": bbc,
        }
    if len(hits) > 1:
        return {
            "state": AMBIGUOUS,
            "reason": REASON_MULTI,
            "match_id": None,
            "candidates": [h[1] for h in hits],
        }
    return {"state": UNMATCHED, "reason": REASON_NONE, "match_id": None, "bbc": None}


def load_bbc_match_index() -> list[dict]:
    from db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT m.id, m.kickoff_utc, m.status, m.home_score, m.away_score,
                   th.name AS home_team, ta.name AS away_team, co.name AS competition
            FROM matches m
            JOIN teams th ON th.id=m.home_team_id
            JOIN teams ta ON ta.id=m.away_team_id
            LEFT JOIN competitions co ON co.id=m.competition_id
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

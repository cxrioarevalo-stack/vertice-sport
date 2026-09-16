"""Official OddsPapi market catalog cache and snapshot mapping.

Catalog metadata (name, period, catalog_handicap) is never treated as the
fixture-specific Betano line.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from db import get_conn
from engine.timeutil import now_utc_iso

TTL_HOURS = float(os.environ.get("ODDS_CATALOG_TTL_HOURS", "24"))
PROVIDER = "oddspapi"
SPORT_KEY = "football"
SPORT_ID = 10


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def catalog_is_fresh(provider_code: str = PROVIDER, sport_key: str = SPORT_KEY, sport_id: int = SPORT_ID) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT fetched_at FROM odds_catalog_meta
               WHERE provider_code=? AND sport_key=? AND sport_id=?""",
            (provider_code, sport_key, sport_id),
        ).fetchone()
        if not row:
            return False
        fetched = _parse_iso(row["fetched_at"])
        if not fetched:
            return False
        age = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
        return age < TTL_HOURS
    finally:
        conn.close()


def persist_catalog(markets: list[dict], *, provider_code: str, sport_key: str, sport_id: int, fetched_at: str) -> int:
    conn = get_conn()
    n = 0
    try:
        for m in markets:
            mid = str(m.get("market_id") or "")
            if not mid:
                continue
            conn.execute(
                """INSERT INTO odds_market_catalog
                   (provider_code, sport_key, sport_id, market_id, market_name, market_type,
                    period, player_prop, catalog_handicap, fetched_at, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider_code, sport_key, market_id) DO UPDATE SET
                     market_name=excluded.market_name,
                     market_type=excluded.market_type,
                     period=excluded.period,
                     player_prop=excluded.player_prop,
                     catalog_handicap=excluded.catalog_handicap,
                     fetched_at=excluded.fetched_at""",
                (
                    provider_code, sport_key, sport_id, mid,
                    m.get("market_name"), m.get("market_type"), m.get("period"),
                    1 if m.get("player_prop") else 0, m.get("catalog_handicap"),
                    fetched_at, provider_code,
                ),
            )
            conn.execute(
                "DELETE FROM odds_market_outcomes WHERE provider_code=? AND sport_key=? AND market_id=?",
                (provider_code, sport_key, mid),
            )
            for oc in m.get("outcomes") or []:
                oid = str(oc.get("outcome_id") or "")
                if not oid:
                    continue
                conn.execute(
                    """INSERT INTO odds_market_outcomes
                       (provider_code, sport_key, market_id, outcome_id, outcome_name)
                       VALUES (?,?,?,?,?)""",
                    (provider_code, sport_key, mid, oid, oc.get("outcome_name")),
                )
            n += 1
        conn.execute(
            """INSERT INTO odds_catalog_meta (provider_code, sport_key, sport_id, fetched_at, market_count)
               VALUES (?,?,?,?,?)
               ON CONFLICT(provider_code, sport_key, sport_id) DO UPDATE SET
                 fetched_at=excluded.fetched_at, market_count=excluded.market_count""",
            (provider_code, sport_key, sport_id, fetched_at, n),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return n


def _lookup(conn, raw_id: str, provider_code: str, sport_key: str) -> dict | None:
    raw_id = str(raw_id)
    market = conn.execute(
        """SELECT * FROM odds_market_catalog
           WHERE provider_code=? AND sport_key=? AND market_id=?""",
        (provider_code, sport_key, raw_id),
    ).fetchone()
    if market:
        return {"market": dict(market), "via": "market_id"}
    parent = conn.execute(
        """SELECT c.* FROM odds_market_outcomes o
           JOIN odds_market_catalog c
             ON c.provider_code=o.provider_code AND c.sport_key=o.sport_key AND c.market_id=o.market_id
           WHERE o.provider_code=? AND o.sport_key=? AND o.outcome_id=?""",
        (provider_code, sport_key, raw_id),
    ).fetchone()
    if parent:
        return {"market": dict(parent), "via": "outcome_id"}
    return None


def _outcome_name(conn, provider_code: str, sport_key: str, market_id: str, outcome_id: str | None) -> tuple[str | None, str | None]:
    if not outcome_id:
        return None, None
    row = conn.execute(
        """SELECT outcome_id, outcome_name FROM odds_market_outcomes
           WHERE provider_code=? AND sport_key=? AND market_id=? AND outcome_id=?""",
        (provider_code, sport_key, market_id, str(outcome_id)),
    ).fetchone()
    if row:
        return row["outcome_id"], row["outcome_name"]
    row = conn.execute(
        """SELECT outcome_id, outcome_name FROM odds_market_outcomes
           WHERE provider_code=? AND sport_key=? AND outcome_id=?""",
        (provider_code, sport_key, str(outcome_id)),
    ).fetchone()
    if row:
        return row["outcome_id"], row["outcome_name"]
    return str(outcome_id), None


def map_scan_snapshots(scan_id: int | None, *, provider_code: str = PROVIDER, sport_key: str = SPORT_KEY) -> dict:
    conn = get_conn()
    mapped = unmapped = 0
    try:
        if scan_id is None:
            snaps = conn.execute(
                "SELECT * FROM odds_snapshots WHERE provider_code=? ORDER BY id",
                (provider_code,),
            ).fetchall()
        else:
            snaps = conn.execute(
                "SELECT * FROM odds_snapshots WHERE scan_id=? AND provider_code=? ORDER BY id",
                (scan_id, provider_code),
            ).fetchall()
        now = now_utc_iso()
        for s in snaps:
            raw_mid = str(s["market_code"] or "")
            raw_oid = None if s["selection"] in (None, "unlabeled") else str(s["selection"])
            found = _lookup(conn, raw_mid, provider_code, sport_key)
            fixture_line = s["line"]
            if not found:
                conn.execute(
                    """INSERT INTO odds_unmapped_markets
                       (snapshot_id, scan_id, match_id, sport_key, provider_code, provider_event_id,
                        bookmaker, raw_market_id, raw_outcome_id, fixture_line, decimal_odds, phase,
                        reason, observed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        s["id"], s["scan_id"], s["match_id"], sport_key, provider_code,
                        s["provider_event_id"], s["bookmaker"], raw_mid, raw_oid,
                        fixture_line, s["decimal_odds"], s["phase"], "catalog_miss", now,
                    ),
                )
                unmapped += 1
                continue
            market = found["market"]
            oid, oname = _outcome_name(conn, provider_code, sport_key, market["market_id"], raw_oid or raw_mid)
            conn.execute(
                """INSERT INTO odds_mapped_snapshots
                   (snapshot_id, scan_id, match_id, sport_key, provider_code, provider_event_id,
                    bookmaker, market_id, market_name_official, market_type, period_official,
                    outcome_id, outcome_name_official, fixture_line, catalog_handicap,
                    decimal_odds, phase, data_status, mapped, source_updated_at, observed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                (
                    s["id"], s["scan_id"], s["match_id"], sport_key, provider_code,
                    s["provider_event_id"], s["bookmaker"], market["market_id"],
                    market["market_name"], market["market_type"], market["period"],
                    oid, oname, fixture_line, market["catalog_handicap"],
                    s["decimal_odds"], s["phase"], s["data_status"] or "REAL",
                    s["source_updated_at"], s["observed_at"],
                ),
            )
            mapped += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"mapped": mapped, "unmapped": unmapped}


def mapped_for_match(match_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM odds_mapped_snapshots WHERE match_id=?
               ORDER BY observed_at DESC, id DESC""",
            (match_id,),
        ).fetchall()
        from engine.market_normalize import normalize_market
        return [normalize_market(dict(r)) for r in rows]
    finally:
        conn.close()


def persist_normalized_v043(rows: list[dict], scan_id: int | None, id_to_match: dict[str, int],
                            provider_code: str = PROVIDER, sport_key: str = SPORT_KEY) -> dict:
    conn = get_conn()
    mapped = unmapped = 0
    try:
        for r in rows:
            fid = str(r.get("provider_event_id") or "")
            mid_match = id_to_match.get(fid)
            market_id = str(r.get("market_code") or r.get("market_id") or "")
            outcome_id = r.get("outcome_id")
            if outcome_id is not None:
                outcome_id = str(outcome_id)
            found = _lookup(conn, market_id, provider_code, sport_key) if market_id else None
            official_name = official_type = official_period = catalog_hcap = None
            oname = None
            is_mapped = 0
            if found:
                market = found["market"]
                official_name = market.get("market_name")
                official_type = market.get("market_type")
                official_period = market.get("period")
                catalog_hcap = market.get("catalog_handicap")
                is_mapped = 1
                if outcome_id:
                    _oid, oname = _outcome_name(conn, provider_code, sport_key, market["market_id"], outcome_id)
                    if oname is None and _oid != outcome_id:
                        oname = None
            else:
                unmapped += 1
            if is_mapped:
                mapped += 1
            fixture_line = r.get("line")
            conn.execute(
                """INSERT INTO odds_normalized_v043
                   (snapshot_id, scan_id, match_id, sport_key, provider_code, provider_event_id,
                    bookmaker, market_id, bookmaker_market_id, market_name_official, market_type,
                    period_official, outcome_id, bookmaker_outcome_id, outcome_name_official,
                    player_id, player_name, fixture_line, catalog_handicap, decimal_odds, phase,
                    mapped, data_status, source_updated_at, observed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r.get("snapshot_id"), scan_id, mid_match, sport_key, provider_code, fid,
                    r.get("bookmaker"), market_id, r.get("bookmaker_market_id"),
                    official_name, official_type, official_period, outcome_id,
                    r.get("bookmaker_outcome_id"), oname, r.get("player_id"), r.get("player_name"),
                    fixture_line, catalog_hcap, r["decimal_odds"], r.get("phase"),
                    is_mapped, r.get("data_status") or "REAL",
                    r.get("source_updated_at"), r.get("observed_at"),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"mapped": mapped, "unmapped": unmapped}

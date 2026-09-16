from __future__ import annotations

import json
import os

from db import get_conn
from engine.odds_match import match_event
from engine.timeutil import now_utc_iso

_SECRET_KEYS = {"apikey", "api_key", "authorization", "token", "secret"}


def capture_raw_odds_enabled() -> bool:
    return os.environ.get("VERTICE_CAPTURE_RAW_ODDS", "1").strip() not in {"0", "false", "off", "no"}


def sanitize_payload(obj, secret: str | None = None):
    """Drop credential keys; redact secret substrings. Structure otherwise unchanged."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower().replace("-", "_") in _SECRET_KEYS:
                continue
            out[k] = sanitize_payload(v, secret)
        return out
    if isinstance(obj, list):
        return [sanitize_payload(v, secret) for v in obj]
    if isinstance(obj, str) and secret and secret in obj:
        return obj.replace(secret, "[REDACTED]")
    return obj


def persist_raw_captures(items: list[dict], scan_id: int | None, secret: str | None = None) -> int:
    if not capture_raw_odds_enabled() or not items:
        return 0
    conn = get_conn()
    n = 0
    try:
        for item in items:
            payload = sanitize_payload(item.get("payload"), secret)
            blob = json.dumps(payload, ensure_ascii=False, default=str)
            if secret and secret in blob:
                blob = blob.replace(secret, "[REDACTED]")
            conn.execute(
                """INSERT INTO odds_raw_captures
                   (scan_id, provider_code, provider_event_id, bookmaker, captured_at, purpose, payload_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    scan_id,
                    item.get("provider_code") or "oddspapi",
                    item.get("provider_event_id"),
                    item.get("bookmaker"),
                    item.get("captured_at") or now_utc_iso(),
                    "debug_raw_odds",
                    blob,
                ),
            )
            n += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return n


PROVIDER_EVENT_BATCH = 25


def persist_provider_events(events: list[dict], fetched_at: str) -> None:
    conn = get_conn()
    try:
        pending: list[dict] = []

        def flush(batch: list[dict]) -> None:
            if not batch:
                return
            for ev in batch:
                conn.execute(
                    """INSERT INTO odds_provider_events
                       (provider_code, provider_event_id, sport_key, home_team, away_team,
                        competition, kickoff_utc, raw_status, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(provider_code, provider_event_id) DO UPDATE SET
                         home_team=excluded.home_team, away_team=excluded.away_team,
                         competition=excluded.competition, kickoff_utc=excluded.kickoff_utc,
                         raw_status=excluded.raw_status, fetched_at=excluded.fetched_at""",
                    (
                        ev["provider_code"], ev["provider_event_id"], "football",
                        ev.get("home_team"), ev.get("away_team"), ev.get("competition"),
                        ev.get("kickoff_utc"), ev.get("raw_status"), fetched_at,
                    ),
                )
            conn.commit()

        for ev in events:
            pending.append(ev)
            if len(pending) >= PROVIDER_EVENT_BATCH:
                flush(pending)
                pending = []
        flush(pending)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


MAP_BATCH_SIZE = 25


def _pair_events(bbc_matches: list[dict], provider_events: list[dict], now: str) -> tuple[list[dict], list[dict]]:
    mapped = []
    unmatched = []
    used_bbc = set()
    for pev in provider_events:
        best = None
        for bm in bbc_matches:
            mid = bm.get("match_id") or bm.get("id")
            if mid in used_bbc:
                continue
            ok, conf, reason = match_event(bm, pev)
            if ok and (best is None or conf > best[0]):
                best = (conf, reason, bm)
        if not best:
            unmatched.append({
                "provider_code": pev.get("provider_code"),
                "provider_event_id": pev.get("provider_event_id"),
                "home_team": pev.get("home_team"),
                "away_team": pev.get("away_team"),
                "kickoff_utc": pev.get("kickoff_utc"),
                "reason": "no confident BBC match",
            })
            continue
        conf, reason, bm = best
        mid = bm.get("match_id") or bm.get("id")
        used_bbc.add(mid)
        mapped.append({
            "match_id": mid,
            "provider_event_id": pev.get("provider_event_id"),
            "provider_code": pev.get("provider_code"),
            "confidence": conf,
            "reason": reason,
        })
    return mapped, unmatched


def map_events(bbc_matches: list[dict], provider_events: list[dict]) -> dict:
    """Match in memory, then persist in small commits. No network is done here."""
    now = now_utc_iso()
    mapped, unmatched = _pair_events(bbc_matches, provider_events, now)
    persist_error = None
    persist_ok = True
    conn = get_conn()
    try:
        pending = unmatched + [{"_kind": "map", **m} for m in mapped]
        batch: list[dict] = []

        def flush(items: list[dict]) -> None:
            if not items:
                return
            for item in items:
                if item.get("_kind") == "map":
                    conn.execute(
                        """INSERT INTO odds_event_map
                           (match_id, provider_code, provider_event_id, confidence, method, reason, created_at)
                           VALUES (?,?,?,?,?,?,?)
                           ON CONFLICT(provider_code, provider_event_id) DO UPDATE SET
                             match_id=excluded.match_id, confidence=excluded.confidence,
                             method=excluded.method, reason=excluded.reason""",
                        (item["match_id"], item.get("provider_code"), item["provider_event_id"],
                         item["confidence"], "name+kickoff", item["reason"], now),
                    )
                else:
                    conn.execute(
                        """INSERT INTO odds_unmatched
                           (provider_code, provider_event_id, home_team, away_team, kickoff_utc, reason, observed_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (item.get("provider_code"), item.get("provider_event_id"), item.get("home_team"),
                         item.get("away_team"), item.get("kickoff_utc"), item.get("reason"), now),
                    )
            conn.commit()

        for row in pending:
            batch.append(row)
            if len(batch) >= MAP_BATCH_SIZE:
                flush(batch)
                batch = []
        flush(batch)
    except Exception as exc:
        persist_ok = False
        persist_error = str(exc)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()
    return {
        "matched": mapped,
        "unmatched": unmatched,
        "persist_ok": persist_ok,
        "persist_error": persist_error,
    }


def persist_odds_rows(rows: list[dict], scan_id: int | None, id_to_match: dict[str, int]) -> int:
    conn = get_conn()
    n = 0
    try:
        for r in rows:
            mid = id_to_match.get(str(r.get("provider_event_id")))
            cur = conn.execute(
                """INSERT INTO odds_snapshots
                   (scan_id, match_id, provider_code, provider_event_id, bookmaker, market_code,
                    market_name, selection, line, decimal_odds, raw_odds, phase, data_status,
                    source_updated_at, observed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    scan_id, mid, r.get("provider_code") or "odds_api_io", r.get("provider_event_id"),
                    r["bookmaker"], r["market_code"], r.get("market_name"), r["selection"],
                    r.get("line"), r["decimal_odds"], r.get("raw_odds"), r["phase"],
                    r.get("data_status") or "REAL", r.get("source_updated_at"), r["observed_at"],
                ),
            )
            r["snapshot_id"] = cur.lastrowid
            n += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return n


def odds_for_match(match_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM odds_snapshots WHERE match_id=?
               ORDER BY observed_at DESC, id DESC""",
            (match_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def log_request(provider: str, endpoint: str, http_status: int | None, ok: bool, error: str | None) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO odds_request_log (provider_code, endpoint, http_status, ok, error, observed_at)
               VALUES (?,?,?,?,?,?)""",
            (provider, endpoint, http_status, 1 if ok else 0, error, now_utc_iso()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

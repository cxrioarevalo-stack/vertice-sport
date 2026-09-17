from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import init_db, get_conn, db_path
from engine.integrity import assess
from engine.markets import empty_markets
from engine.quality import completeness, quality_for_match
from engine.odds_catalog import mapped_for_match
from engine.odds_ingest import ingest_odds_for_matches
from engine.odds_store import odds_for_match
from engine.store import load_latest_scan, load_match, upsert_matches
from engine.timeutil import app_timezone_name, now_utc_iso, today_in_app_tz, to_display
from providers.bbc import ProviderParseError, fetch_today

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vertice")

FRONTEND = ROOT.parent / "frontend"
SPORT_KEY = "football"

app = FastAPI(title="VÉRTICE SPORT", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


def _decorate(m: dict) -> dict:
    integ = assess(m)
    out = {
        **m,
        "integrity_level": integ["level"],
        "integrity_note": integ["note"],
        "fields": completeness(m),
        "conflicts": [],
        "markets": empty_markets(),
        "odds_status": "MISSING",
        "recommendation": "NO BET — INSUFFICIENT DATA",
        "recommendation_reason": "Reliable bookmaker odds and sufficient statistical context are not available in V0.3.1.",
        "venue_status": "MISSING" if not m.get("venue") else "REAL",
        "form_status": "MISSING",
        "injuries_status": "MISSING",
        "suspensions_status": "MISSING",
        "lineups_status": "MISSING",
        "news": [],
        "kickoff_display": to_display(m.get("kickoff_utc")),
        "field_statuses": {
            "home_team": "REAL" if m.get("home_team") else "MISSING",
            "away_team": "REAL" if m.get("away_team") else "MISSING",
            "status": "REAL" if m.get("status") else "MISSING",
            "score": "REAL" if m.get("home_score") is not None else "MISSING",
            "minute": "REAL" if m.get("minute") else "MISSING",
            "venue": "REAL" if m.get("venue") else "MISSING",
            "odds": "MISSING",
        },
    }
    out["data_quality"] = quality_for_match(out)
    mid = out.get("match_id") or out.get("id")
    if mid:
        snaps = odds_for_match(int(mid))
        mapped = mapped_for_match(int(mid))
        out["odds_records"] = snaps
        out["odds_mapped"] = mapped
        out["odds_status"] = "REAL" if snaps else out.get("odds_status") or "MISSING"
    else:
        out["odds_records"] = []
    return out


def _payload_from_db() -> dict:
    loaded = load_latest_scan(SPORT_KEY)
    if not loaded:
        return {
            "matches": [],
            "message": "No scan yet",
            "db_path": str(db_path()),
            "timezone": app_timezone_name(),
        }
    scan = loaded["scan"]
    matches = [_decorate(m) for m in loaded["matches"]]
    return {
        "matches": matches,
        "fetched_at": scan.get("finished_at") or scan.get("started_at"),
        "date": scan.get("date_local"),
        "timezone": scan.get("timezone") or app_timezone_name(),
        "count": len(matches),
        "scan_id": scan.get("id"),
        "scan_status": scan.get("status"),
        "persist_ok": bool(scan.get("persist_ok")),
        "persist_error": scan.get("persist_error"),
        "sources_ok": (scan.get("sources_ok") or "").split(",") if scan.get("sources_ok") else [],
        "sources_fail": (scan.get("sources_fail") or "").split(",") if scan.get("sources_fail") else [],
        "db_path": str(db_path()),
        "recommendation": "NO BET TODAY",
        "recommendation_detail": "NO BET TODAY — model_probability is NULL (training_readiness NOT_READY). EV and picks are disabled.",
        "model_status": "NOT_READY",
        "model_probability": None,
        "ev": None,
    }



def _market_rows_today(limit: int = 3000) -> list[dict]:
    """Read real OddsPapi/Betano observations captured for today from SQLite.
    No network call. Used by market-mode UI before the VÉRTICE model is trained.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from engine.market_normalize import normalize_market

    tz = ZoneInfo(app_timezone_name())
    now_local = datetime.now(timezone.utc).astimezone(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_utc = start_local.astimezone(timezone.utc).isoformat()
    end_utc = end_local.astimezone(timezone.utc).isoformat()

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT v.*, e.home_team, e.away_team, e.competition, e.kickoff_utc, e.raw_status
               FROM odds_normalized_v043 v
               LEFT JOIN odds_provider_events e
                 ON e.provider_code=v.provider_code AND e.provider_event_id=v.provider_event_id
               WHERE v.provider_code='oddspapi'
                 AND v.bookmaker='betano'
                 AND v.observed_at >= ? AND v.observed_at <= ?
               ORDER BY v.observed_at DESC, v.id DESC
               LIMIT ?""",
            (start_utc, end_utc, int(limit)),
        ).fetchall()
        out=[]
        seen=set()
        for row in rows:
            r=normalize_market(dict(row))
            # Keep one current-ish quote per exact event/market/outcome to avoid
            # flooding the UI with historical duplicates from the same scan day.
            key=(r.get('provider_event_id'), r.get('market_id'), r.get('outcome_id'), r.get('period_canonical'))
            if key in seen:
                continue
            seen.add(key)
            r['event_label']=f"{r.get('home_team') or '?'} vs {r.get('away_team') or '?'}"
            r['competition']=r.get('competition')
            r['kickoff_utc']=r.get('kickoff_utc')
            r['raw_status']=r.get('raw_status')
            out.append(r)
        return out
    finally:
        conn.close()


def _market_mode_candidates(min_odds: float = 1.50) -> list[dict]:
    rows=_market_rows_today()
    candidates=[]
    for r in rows:
        odds=r.get('decimal_odds_valid')
        if odds is None or odds < min_odds:
            continue
        if r.get('phase') == 'LIVE':
            # Live odds are not currently available from the free Betano access path.
            continue
        if r.get('market_readiness') == 'NOT_READY':
            continue
        # Market-mode probability is explicitly the implied market probability.
        r['market_probability']=r.get('implied_probability')
        r['probability_source']='MARKET'
        candidates.append(r)
    candidates.sort(key=lambda x: (x.get('market_probability') or 0, -(x.get('decimal_odds') or 999)), reverse=True)
    return candidates

@app.get("/api/readiness")
def readiness():
    from engine.readiness import current_readiness
    return current_readiness()


@app.get("/api/history/evaluation")
def history_evaluation(
    market_family: str | None = None,
    market_type: str | None = None,
    competition: str | None = None,
    product_line: str | None = None,
    odds_bucket: str | None = None,
    period: str | None = None,
    settlement: str | None = None,
):
    from engine.evaluation import evaluate
    from engine.historical_dataset import load_historical_observations

    rows = load_historical_observations()
    filters = {
        "market_family": market_family,
        "market_type": market_type,
        "competition": competition,
        "odds_bucket": odds_bucket,
        "period_canonical": period,
        "settlement": settlement,
    }
    if product_line not in (None, ""):
        try:
            filters["product_line"] = float(product_line)
        except ValueError:
            filters["product_line"] = product_line
    return evaluate(rows, filters=filters)


@app.get("/api/model/status")
def api_model_status():
    from engine.model import model_status
    return model_status()


@app.get("/api/analysis")
def api_analysis():
    from engine.pipeline import analyze_match_bundle
    from engine.timeutil import now_utc_iso
    loaded = load_latest_scan(SPORT_KEY)
    if not loaded:
        return {"headline": "NO BET TODAY", "matches": [], "model_status": "NOT_READY"}
    out = []
    for m in loaded["matches"][:40]:
        out.append(analyze_match_bundle(m, [], now_utc_iso()))
    return {
        "headline": "NO BET TODAY",
        "model_status": "NOT_READY",
        "model_probability": None,
        "ev": None,
        "count": len(out),
        "matches": out,
    }


@app.get("/api/features")
def api_features(match_id: int | None = None):
    from engine.features import build_features
    from engine.future_features import future_feature_bundle
    from engine.timeutil import now_utc_iso
    if match_id is None:
        return {"error": "match_id required", "future_slots": future_feature_bundle()}
    m = load_match(str(match_id))
    if not m:
        raise HTTPException(404, "match not found")
    as_of = m.get("kickoff_utc") or now_utc_iso()
    return build_features(m, as_of)


@app.get("/api/history")
def api_history():
    from engine.evaluation import evaluate
    from engine.historical_dataset import load_historical_observations
    rows = load_historical_observations()
    ev = evaluate(rows)
    sample = []
    for r in rows[:25]:
        sample.append({
            "date": r.get("kickoff_utc") or r.get("as_of_utc"),
            "market_family": r.get("market_family"),
            "product_line": r.get("product_line"),
            "decimal_odds": r.get("decimal_odds"),
            "implied_probability": r.get("implied_probability"),
            "model_probability": None,
            "settlement": r.get("settlement_result"),
            "snapshot_id": r.get("snapshot_id"),
            "feature_version": r.get("feature_version"),
            "source": r.get("provider_code"),
        })
    return {"evaluation": ev, "sample": sample, "model_probability": None}


@app.get("/api/daily")
def api_daily():
    from engine.daily import cuota_del_dia
    rows=_market_mode_candidates()
    # If the predictive model is ready, retain the existing model path. Otherwise
    # provide a real market-only observation, never a fake model prediction.
    from engine.model import model_status
    st=model_status().get("model_status")
    result=cuota_del_dia([], st)
    if st in {"TRAINED", "EVALUATED", "CALIBRATED"}:
        return cuota_del_dia(rows, st)
    if rows:
        best=rows[0]
        return {
            "module":"CUOTA_DEL_DIA", "mode":"MODO_MERCADO",
            "model_status":st, "predictive":False,
            "selection":"MARKET_OBSERVATION",
            "headline":"CUOTA DEL DÍA · MODO MERCADO",
            "pick":best,
            "market_probability":best.get("market_probability"),
            "probability_source":"MARKET",
            "market_attention":"UNKNOWN",
            "note":"Probabilidad implícita de OddsPapi/Betano. No es probabilidad propia de VÉRTICE ni una garantía."
        }
    return {**result, "mode":"MODO_MERCADO", "available_markets":0,
            "headline":"NO HAY MERCADOS REALES DISPONIBLES AHORA",
            "note":"No se encontró una cuota real elegible en el histórico del día."}


@app.get("/api/popularity")
def api_popularity():
    from engine.popularity import market_attention
    return market_attention({})


@app.get("/api/capital")
def api_capital(capital: float = 1, meta: float = 100, cuota: float = 1.5, nivel: str = "MODERADO"):
    from engine.capital import meta_de_capital
    return meta_de_capital(capital, meta, cuota, nivel)


@app.get("/api/ruta")
def api_ruta(capital: float = 1, meta: float = 100, cuota: float = 5):
    from engine.capital import ruta_hacia_la_meta
    return ruta_hacia_la_meta(capital, meta, cuota)


@app.get("/api/construir")
def api_construir(target: float = 5):
    from engine.target_odds import construir_cuota, build_market_target
    from engine.model import model_status
    st=model_status().get("model_status")
    rows=_market_mode_candidates()
    if st in {"TRAINED", "EVALUATED", "CALIBRATED"}:
        return construir_cuota(rows, target, st)
    return build_market_target(rows, target)


@app.get("/api/health")
def health():
    return {
        "system": "VÉRTICE SPORT",
        "version": "0.10.1",
        "status": "ready",
        "model_status": "NOT_READY",
        "sport_active": SPORT_KEY,
        "planned_modules": ["tennis", "basketball", "baseball"],
        "betano": "odds_provider_persisted_and_live_access_depends_on_plan",
        "timezone": app_timezone_name(),
        "today_app_tz": today_in_app_tz(),
        "time_utc": now_utc_iso(),
        "db_path": str(db_path()),
    }


def _record_scan(**fields):
    """Best-effort scan_runs write. Never swallow; never pretend success."""
    import sqlite3
    conn = get_conn()
    try:
        cols = ", ".join(fields)
        qs = ", ".join("?" for _ in fields)
        cur = conn.execute(
            f"INSERT INTO scan_runs ({cols}) VALUES ({qs})",
            tuple(fields.values()),
        )
        conn.commit()
        return cur.lastrowid, None
    except sqlite3.Error as exc:
        conn.rollback()
        log.exception("scan_runs insert failed")
        return None, str(exc)
    finally:
        conn.close()


def _touch_scan(scan_id: int | None, **fields) -> str | None:
    import sqlite3
    if scan_id is None:
        return "no scan_id"
    conn = get_conn()
    try:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE scan_runs SET {sets} WHERE id=?", (*fields.values(), scan_id))
        conn.commit()
        return None
    except sqlite3.Error as exc:
        conn.rollback()
        log.exception("scan_runs update failed")
        return str(exc)
    finally:
        conn.close()


@app.post("/api/scan")
def scan():
    target = today_in_app_tz()
    tz = app_timezone_name()
    scan_id, insert_err = _record_scan(
        started_at=now_utc_iso(),
        date_local=target,
        timezone=tz,
        sport_key=SPORT_KEY,
        status="STARTED",
        persist_ok=0,
    )

    sources_ok = []
    sources_fail = []
    persist_error = None
    persist_ok = False
    persist_stats = {}
    odds_status_block = {"odds_available": False, "error": None, "error_kind": "not_run"}
    matches = []
    final_status = "FAILED"

    meta_err = insert_err
    touch = _touch_scan(scan_id, status="FETCHING")
    if touch:
        meta_err = meta_err or touch
    try:
        bbc = fetch_today(target)
        sources_ok.append({"code": "bbc", "count": bbc["count"], "fetched_at": bbc["fetched_at"], "url": bbc["url"]})
        matches = bbc["matches"]
        touch = _touch_scan(scan_id, status="PARSED")
        if touch:
            meta_err = meta_err or touch
    except ProviderParseError as exc:
        sources_fail.append({"code": "bbc", "error": f"parse: {exc}"})
        final_status = "FAILED"
        log.exception("BBC parse failed")
    except Exception as exc:
        sources_fail.append({"code": "bbc", "error": f"fetch: {exc}"})
        final_status = "FAILED"
        log.exception("BBC fetch failed")

    sources_fail.append({
        "code": "betano",
        "error": "Public access restricted (geo/compliance). No Betano odds ingested.",
    })

    enriched = [_decorate(m) for m in matches]
    if matches:
        touch = _touch_scan(scan_id, status="PERSISTING")
        if touch:
            meta_err = meta_err or touch
        try:
            persist_stats = upsert_matches(enriched, scan_id, sport_key=SPORT_KEY)
            persist_ok = True
            odds_status_block = ingest_odds_for_matches(enriched, scan_id)

        except Exception as exc:
            persist_ok = False
            persist_error = str(exc)
            log.exception("Persistence failed")

    if persist_ok and matches:
        final_status = "COMPLETED"
    elif persist_ok and not matches and any(s.get("code") == "bbc" and "error" in s for s in sources_fail):
        final_status = "FAILED"
    elif persist_ok and not matches:
        final_status = "COMPLETED"
    elif matches and not persist_ok:
        final_status = "FAILED"

    finish_err = _touch_scan(
        scan_id,
        finished_at=now_utc_iso(),
        matches_found=len(enriched),
        sources_ok=",".join(s["code"] for s in sources_ok),
        sources_fail=",".join(s["code"] for s in sources_fail),
        persist_ok=1 if persist_ok else 0,
        persist_error=persist_error,
        status=final_status,
    )
    if finish_err:
        meta_err = meta_err or finish_err
        log.error("Could not finalize scan_runs row: %s", finish_err)

    db_payload = _payload_from_db() if persist_ok else {"matches": enriched}
    counts = {
        "LIVE": sum(1 for m in (db_payload.get("matches") or enriched) if m.get("status") == "LIVE"),
        "UPCOMING": sum(1 for m in (db_payload.get("matches") or enriched) if m.get("status") == "UPCOMING"),
        "FINISHED": sum(1 for m in (db_payload.get("matches") or enriched) if m.get("status") == "FINISHED"),
        "SUSPENDED": sum(1 for m in (db_payload.get("matches") or enriched) if m.get("status") == "SUSPENDED"),
    }
    return {
        **db_payload,
        "scan_id": scan_id,
        "scan_status": final_status,
        "date": target,
        "timezone": tz,
        "count": len(db_payload.get("matches") or enriched),
        "counts": counts,
        "sources_ok": sources_ok,
        "sources_fail": sources_fail,
        "persist_ok": persist_ok,
        "persist_error": persist_error,
        "persist_stats": persist_stats,
        "persisted": persist_ok,
        "db_path": str(db_path()),
        "fetched_at": now_utc_iso() if not db_payload.get("fetched_at") else db_payload.get("fetched_at"),
        "recommendation": "NO BET TODAY",
        "recommendation_detail": "No selection is issued because bookmaker odds and statistical layers are not connected yet.",
        "warning": None if persist_ok else "Matches were fetched but NOT persisted.",
        "scan_meta_error": meta_err,
        "odds": odds_status_block,
    }


@app.get("/api/scan")
def get_scan():
    return _payload_from_db()


@app.get("/api/matches/{match_key}")
def match_detail(match_key: str):
    found = load_match(match_key)
    if not found:
        raise HTTPException(404, "Match not found in database")
    decorated = _decorate(found)
    return {
        **decorated,
        "statistics": {"data_status": "MISSING", "note": "Advanced stats not ingested in V0.3.1."},
        "injuries": [],
        "suspensions": [],
        "lineups": [],
        "recent_form": {"data_status": "MISSING"},
        "home_away_splits": {"data_status": "MISSING"},
    }


@app.get("/api/markets")
def markets():
    rows=_market_mode_candidates()
    return {
        "mode":"MARKET", "odds_provider":"oddspapi", "betano":"available_from_persisted_data" if rows else "no_persisted_quotes_today",
        "count":len(rows), "items":rows[:200],
        "note":"Probabilidad = 1/cuota y está etiquetada como MARKET; no es model_probability."
    }


@app.get("/api/best150")
def best150():
    rows=_market_mode_candidates(1.50)
    return {"status":"MARKET_MODE", "message":"Ranking por probabilidad implícita de mercado (cuota >= 1.50).", "items":rows[:50]}


@app.get("/api/build-odds")
def build_odds(target: float = 5.0):
    from engine.target_odds import build_market_target
    return build_market_target(_market_mode_candidates(), target)


@app.get("/manifest.json")
def manifest():
    return FileResponse(FRONTEND / "manifest.json")


@app.get("/sw.js")
def sw():
    return FileResponse(FRONTEND / "sw.js")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

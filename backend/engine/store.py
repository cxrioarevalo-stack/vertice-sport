from __future__ import annotations

from engine.timeutil import now_utc_iso
from db import get_conn


TRACKED_FIELDS = ("status", "home_score", "away_score", "minute", "kickoff_utc")


def sport_row(conn, sport_key: str = "football"):
    row = conn.execute(
        "SELECT id, sport_key FROM sports WHERE sport_key=?",
        (sport_key,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Unknown sport_key={sport_key}")
    return row


def get_or_create_team(conn, sport_id: int, name: str) -> int:
    row = conn.execute(
        "SELECT id FROM teams WHERE sport_id=? AND name=?",
        (sport_id, name),
    ).fetchone()
    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO teams (sport_id, name) VALUES (?,?)",
        (sport_id, name),
    )
    return cur.lastrowid


def get_or_create_competition(conn, sport_id: int, name: str) -> int:
    row = conn.execute(
        "SELECT id FROM competitions WHERE sport_id=? AND name=?",
        (sport_id, name),
    ).fetchone()
    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO competitions (sport_id, name) VALUES (?,?)",
        (sport_id, name),
    )
    return cur.lastrowid


def source_id(conn, code: str = "bbc") -> int:
    row = conn.execute(
        "SELECT id FROM sources WHERE code=?",
        (code,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Unknown source {code}")
    return row["id"]


def upsert_matches(
    normalized: list[dict],
    scan_id: int,
    sport_key: str = "football",
) -> dict:
    conn = get_conn()
    try:
        sport = sport_row(conn, sport_key)
        sid = source_id(conn, "bbc")
        now = now_utc_iso()
        ids = []
        new = updated = unchanged = 0
        seen_ext = set()

        for m in normalized:
            ext = m.get("external_id")
            if not ext:
                raise RuntimeError(
                    "Refusing to persist a match without external_id"
                )

            if ext in seen_ext:
                continue

            seen_ext.add(ext)

            home_id = get_or_create_team(
                conn,
                sport["id"],
                m["home_team"],
            )

            away_id = get_or_create_team(
                conn,
                sport["id"],
                m["away_team"],
            )

            comp_id = (
                get_or_create_competition(
                    conn,
                    sport["id"],
                    m["competition"],
                )
                if m.get("competition")
                else None
            )

            existing = conn.execute(
                "SELECT * FROM matches WHERE source_code=? AND external_id=?",
                ("bbc", ext),
            ).fetchone()

            presence = "NEW"

            if existing:
                changed = any(
                    str(
                        existing[f]
                        if existing[f] is not None
                        else ""
                    )
                    != str(
                        m.get(f)
                        if m.get(f) is not None
                        else ""
                    )
                    for f in TRACKED_FIELDS
                )

                presence = "UPDATED" if changed else "UNCHANGED"
                mid = existing["id"]

                conn.execute(
                    """UPDATE matches SET
                       sport_id=?,
                       sport_key=?,
                       competition_id=?,
                       home_team_id=?,
                       away_team_id=?,
                       source_code=?,
                       external_urn=?,
                       kickoff_utc=?,
                       venue=?,
                       status=?,
                       minute=?,
                       home_score=?,
                       away_score=?,
                       data_quality=?,
                       integrity_level=?,
                       integrity_note=?,
                       presence=?,
                       last_seen_scan_id=?,
                       updated_at=?
                       WHERE id=?""",
                    (
                        sport["id"],
                        sport_key,
                        comp_id,
                        home_id,
                        away_id,
                        "bbc",
                        m.get("external_urn"),
                        m.get("kickoff_utc"),
                        m.get("venue"),
                        m.get("status"),
                        m.get("minute"),
                        m.get("home_score"),
                        m.get("away_score"),
                        m.get("data_quality"),
                        m.get("integrity_level"),
                        m.get("integrity_note"),
                        presence,
                        scan_id,
                        now,
                        mid,
                    ),
                )

                if changed:
                    updated += 1
                else:
                    unchanged += 1

            else:
                cur = conn.execute(
                    """INSERT INTO matches (
                         sport_id,
                         sport_key,
                         competition_id,
                         home_team_id,
                         away_team_id,
                         source_code,
                         external_id,
                         external_urn,
                         kickoff_utc,
                         venue,
                         status,
                         minute,
                         home_score,
                         away_score,
                         data_quality,
                         integrity_level,
                         integrity_note,
                         presence,
                         last_seen_scan_id,
                         created_at,
                         updated_at
                       ) VALUES (
                         ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                       )""",
                    (
                        sport["id"],
                        sport_key,
                        comp_id,
                        home_id,
                        away_id,
                        "bbc",
                        ext,
                        m.get("external_urn"),
                        m.get("kickoff_utc"),
                        m.get("venue"),
                        m.get("status"),
                        m.get("minute"),
                        m.get("home_score"),
                        m.get("away_score"),
                        m.get("data_quality"),
                        m.get("integrity_level"),
                        m.get("integrity_note"),
                        "NEW",
                        scan_id,
                        now,
                        now,
                    ),
                )

                mid = cur.lastrowid
                new += 1

            m["match_id"] = mid
            m["presence"] = presence
            ids.append(mid)

            for field in TRACKED_FIELDS:
                val = m.get(field)

                conn.execute(
                    """INSERT INTO match_observations
                       (
                         match_id,
                         scan_id,
                         source_id,
                         field_name,
                         field_value,
                         data_status,
                         confidence,
                         observed_at
                       )
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        mid,
                        scan_id,
                        sid,
                        field,
                        None if val is None else str(val),
                        "REAL" if val is not None else "MISSING",
                        None,
                        m.get("fetched_at") or now,
                    ),
                )

        disappeared = []

        rows = conn.execute(
            """SELECT id, external_id
               FROM matches
               WHERE sport_key=?
                 AND source_code='bbc'
                 AND (
                     last_seen_scan_id IS NULL
                     OR last_seen_scan_id != ?
                 )
                 AND presence != 'DISAPPEARED_FROM_SOURCE'""",
            (sport_key, scan_id),
        ).fetchall()

        for row in rows:
            conn.execute(
                "UPDATE matches SET presence=?, updated_at=? WHERE id=?",
                (
                    "DISAPPEARED_FROM_SOURCE",
                    now,
                    row["id"],
                ),
            )
            disappeared.append(row["external_id"])

        conn.commit()

        return {
            "ok": True,
            "match_ids": ids,
            "new": new,
            "updated": updated,
            "unchanged": unchanged,
            "disappeared": len(disappeared),
            "disappeared_ids": disappeared,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def update_existing_match_results(normalized: list[dict]) -> dict:
    """Update results for BBC matches already stored in SQLite.

    This function deliberately does NOT:
    - create new matches,
    - delete matches,
    - mark matches as disappeared,
    - change bookmaker observations.

    It only updates the result/status fields of an existing BBC match.
    """

    conn = get_conn()

    try:
        found = 0
        updated = 0

        for m in normalized:
            ext = m.get("external_id")

            if not ext:
                continue

            existing = conn.execute(
                """SELECT id, status, home_score, away_score, minute,
                          kickoff_utc
                   FROM matches
                   WHERE source_code=? AND external_id=?""",
                ("bbc", ext),
            ).fetchone()

            if not existing:
                continue

            found += 1

            changed = any(
                str(
                    existing[field]
                    if existing[field] is not None
                    else ""
                )
                != str(
                    m.get(field)
                    if m.get(field) is not None
                    else ""
                )
                for field in TRACKED_FIELDS
            )

            if not changed:
                continue

            conn.execute(
                """UPDATE matches
                   SET status=?,
                       home_score=?,
                       away_score=?,
                       minute=?,
                       kickoff_utc=?,
                       updated_at=?
                   WHERE id=?""",
                (
                    m.get("status"),
                    m.get("home_score"),
                    m.get("away_score"),
                    m.get("minute"),
                    m.get("kickoff_utc"),
                    now_utc_iso(),
                    existing["id"],
                ),
            )

            updated += 1

        conn.commit()

        return {
            "ok": True,
            "found": found,
            "updated": updated,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def load_latest_scan(sport_key: str = "football") -> dict | None:
    conn = get_conn()

    try:
        scan = conn.execute(
            """SELECT *
               FROM scan_runs
               WHERE sport_key=?
                 AND status='COMPLETED'
               ORDER BY id DESC
               LIMIT 1""",
            (sport_key,),
        ).fetchone()

        if not scan:
            scan = conn.execute(
                "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if not scan:
            return None

        matches = []

        rows = conn.execute(
            """SELECT m.*,
                      th.name AS home_team,
                      ta.name AS away_team,
                      c.name AS competition
               FROM matches m
               LEFT JOIN teams th
                 ON th.id=m.home_team_id
               LEFT JOIN teams ta
                 ON ta.id=m.away_team_id
               LEFT JOIN competitions c
                 ON c.id=m.competition_id
               WHERE m.sport_key=?
                 AND m.last_seen_scan_id=?
               ORDER BY m.kickoff_utc""",
            (sport_key, scan["id"]),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                """SELECT m.*,
                          th.name AS home_team,
                          ta.name AS away_team,
                          c.name AS competition
                   FROM matches m
                   LEFT JOIN teams th
                     ON th.id=m.home_team_id
                   LEFT JOIN teams ta
                     ON ta.id=m.away_team_id
                   LEFT JOIN competitions c
                     ON c.id=m.competition_id
                   WHERE m.sport_key=?
                     AND m.presence != 'DISAPPEARED_FROM_SOURCE'
                   ORDER BY m.kickoff_utc""",
                (sport_key,),
            ).fetchall()

        for r in rows:
            matches.append(dict(r))

        return {
            "scan": dict(scan),
            "matches": matches,
        }

    finally:
        conn.close()


def load_match(match_key: str) -> dict | None:
    conn = get_conn()

    try:
        row = conn.execute(
            """SELECT m.*,
                      th.name AS home_team,
                      ta.name AS away_team,
                      c.name AS competition
               FROM matches m
               LEFT JOIN teams th
                 ON th.id=m.home_team_id
               LEFT JOIN teams ta
                 ON ta.id=m.away_team_id
               LEFT JOIN competitions c
                 ON c.id=m.competition_id
               WHERE m.external_id=?
                  OR CAST(m.id AS TEXT)=?""",
            (match_key, match_key),
        ).fetchone()

        return dict(row) if row else None

    finally:
        conn.close()

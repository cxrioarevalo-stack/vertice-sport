import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = ROOT / "data" / "vertice.db"


def db_path() -> Path:
    override = os.environ.get("VERTICE_DB")
    if override:
        return Path(override)
    return DEFAULT_DB


def get_conn() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timeout_ms = int(os.environ.get("VERTICE_BUSY_TIMEOUT_MS", "10000"))
    conn = sqlite3.connect(str(path), timeout=max(timeout_ms / 1000.0, 1.0))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:
        pass
    try:
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        pass
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _add_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    if col not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _apply_schema_text(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _apply_alters(conn: sqlite3.Connection) -> None:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "matches" in names:
        _add_column(conn, "matches", "sport_key", "TEXT NOT NULL DEFAULT 'football'")
        _add_column(conn, "matches", "source_code", "TEXT")
        _add_column(conn, "matches", "external_id", "TEXT")
        _add_column(conn, "matches", "external_urn", "TEXT")
        _add_column(conn, "matches", "presence", "TEXT")
        _add_column(conn, "matches", "last_seen_scan_id", "INTEGER")
    if "match_observations" in names:
        _add_column(conn, "match_observations", "scan_id", "INTEGER")
    if "scan_runs" in names:
        _add_column(conn, "scan_runs", "timezone", "TEXT")
        _add_column(conn, "scan_runs", "sport_key", "TEXT DEFAULT 'football'")
        _add_column(conn, "scan_runs", "status", "TEXT")
        _add_column(conn, "scan_runs", "persist_ok", "INTEGER")
        _add_column(conn, "scan_runs", "persist_error", "TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_source_ext "
        "ON matches(source_code, external_id) WHERE external_id IS NOT NULL"
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES ('0.3.1', datetime('now'))"
    )


def migrate(conn: sqlite3.Connection) -> None:
    try:
        _apply_schema_text(conn)
        _apply_alters(conn)
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "disk I/O error" not in str(exc):
            raise
        # Some sandboxed filesystems reject large executescript in-place.
        dest = db_path()
        tmp = Path(tempfile.mkstemp(suffix=".db")[1])
        tconn = sqlite3.connect(tmp)
        try:
            _apply_schema_text(tconn)
            _apply_alters(tconn)
            tconn.commit()
        finally:
            tconn.close()
        conn.close()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp, dest)
        tmp.unlink(missing_ok=True)


def init_db() -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        migrate(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

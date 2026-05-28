import sqlite3

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """스키마 생성 + 후방 호환 마이그레이션."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id    INTEGER NOT NULL,
                guild_id   INTEGER NOT NULL,
                voice      TEXT    NOT NULL DEFAULT 'ko-KR-SunHiNeural',
                speed      TEXT    NOT NULL DEFAULT '+0%',
                use_cloned INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS play_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                guild_id  INTEGER NOT NULL,
                text      TEXT    NOT NULL,
                voice     TEXT    NOT NULL,
                played_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
            )
        """)

        # ── Tier 등록 확장 ──
        _add_column_if_missing(conn, "user_settings", "tier",         "INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(conn, "user_settings", "refs_json",    "TEXT NOT NULL DEFAULT '[]'")
        _add_column_if_missing(conn, "user_settings", "ckpt_path",    "TEXT")
        _add_column_if_missing(conn, "user_settings", "tier3_status", "TEXT")
        _add_column_if_missing(conn, "user_settings", "updated_at",   "TEXT")

        # ── Tier 3 학습 작업 큐 ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tier3_jobs (
                job_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                guild_id      INTEGER NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'queued',   -- queued · training · ready · failed
                wav_count     INTEGER NOT NULL DEFAULT 0,
                wav_dir       TEXT,
                ckpt_path     TEXT,
                error         TEXT,
                submitted_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
                started_at    TEXT,
                completed_at  TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tier3_user ON tier3_jobs (user_id, guild_id, status)")
        conn.commit()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

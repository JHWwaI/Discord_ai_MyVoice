import sqlite3

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # 동시 읽기/쓰기 성능 향상
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
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
        conn.commit()

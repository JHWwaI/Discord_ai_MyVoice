from db.database import get_connection


class LogService:
    def record(self, user_id: int, guild_id: int, text: str, voice: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO play_log (user_id, guild_id, text, voice) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, text, voice),
            )
            conn.commit()

    def get_recent(self, user_id: int, guild_id: int, limit: int = 10) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT text, voice, played_at
                FROM play_log
                WHERE user_id=? AND guild_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, guild_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

from db.database import get_connection
from models.user_settings import UserSettings
from config import TTS_VOICE_DEFAULT, TTS_SPEED_DEFAULT


class UserSettingsService:
    """사용자별 TTS 설정을 SQLite에서 조회/저장한다."""

    def get(self, user_id: int, guild_id: int) -> UserSettings:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_settings WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ).fetchone()
        if row:
            return UserSettings(
                user_id=row["user_id"],
                guild_id=row["guild_id"],
                voice=row["voice"],
                speed=row["speed"],
                use_cloned_voice=bool(row["use_cloned"]),
            )
        return UserSettings(
            user_id=user_id,
            guild_id=guild_id,
            voice=TTS_VOICE_DEFAULT,
            speed=TTS_SPEED_DEFAULT,
        )

    def upsert(self, user_id: int, guild_id: int, **kwargs) -> UserSettings:
        current = self.get(user_id, guild_id)
        updated = UserSettings(
            user_id=user_id,
            guild_id=guild_id,
            voice=kwargs.get("voice", current.voice),
            speed=kwargs.get("speed", current.speed),
            use_cloned_voice=kwargs.get("use_cloned_voice", current.use_cloned_voice),
        )
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (user_id, guild_id, voice, speed, use_cloned)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    voice=excluded.voice,
                    speed=excluded.speed,
                    use_cloned=excluded.use_cloned
                """,
                (
                    user_id,
                    guild_id,
                    updated.voice,
                    updated.speed,
                    int(updated.use_cloned_voice),
                ),
            )
            conn.commit()
        return updated

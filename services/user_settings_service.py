import json

from config import TTS_VOICE_DEFAULT, TTS_SPEED_DEFAULT
from db.database import get_connection
from models.user_settings import UserSettings


class UserSettingsService:
    """사용자별 TTS 설정 + Tier 등록 정보를 SQLite에서 조회/저장한다."""

    # ── Read ───────────────────────────────────────────────────────────────
    def get(self, user_id: int, guild_id: int) -> UserSettings:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_settings WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ).fetchone()

        if row:
            keys = row.keys()
            refs: list[str] = []
            if "refs_json" in keys:
                try:
                    refs = json.loads(row["refs_json"] or "[]")
                except Exception:
                    refs = []
            return UserSettings(
                user_id=row["user_id"],
                guild_id=row["guild_id"],
                voice=row["voice"],
                speed=row["speed"],
                use_cloned_voice=bool(row["use_cloned"]),
                tier=row["tier"] if "tier" in keys else 1,
                refs=refs,
                ckpt_path=row["ckpt_path"] if "ckpt_path" in keys else None,
                tier3_status=row["tier3_status"] if "tier3_status" in keys else None,
            )

        return UserSettings(
            user_id=user_id,
            guild_id=guild_id,
            voice=TTS_VOICE_DEFAULT,
            speed=TTS_SPEED_DEFAULT,
        )

    # ── Write ──────────────────────────────────────────────────────────────
    def upsert(self, user_id: int, guild_id: int, **kwargs) -> UserSettings:
        current = self.get(user_id, guild_id)

        updated = UserSettings(
            user_id=user_id,
            guild_id=guild_id,
            voice=kwargs.get("voice", current.voice),
            speed=kwargs.get("speed", current.speed),
            use_cloned_voice=kwargs.get("use_cloned_voice", current.use_cloned_voice),
            tier=kwargs.get("tier", current.tier),
            refs=kwargs.get("refs", current.refs),
            ckpt_path=kwargs.get("ckpt_path", current.ckpt_path),
            tier3_status=kwargs.get("tier3_status", current.tier3_status),
        )

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (
                    user_id, guild_id, voice, speed, use_cloned,
                    tier, refs_json, ckpt_path, tier3_status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                        strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    voice         = excluded.voice,
                    speed         = excluded.speed,
                    use_cloned    = excluded.use_cloned,
                    tier          = excluded.tier,
                    refs_json     = excluded.refs_json,
                    ckpt_path     = excluded.ckpt_path,
                    tier3_status  = excluded.tier3_status,
                    updated_at    = excluded.updated_at
                """,
                (
                    user_id, guild_id,
                    updated.voice,
                    updated.speed,
                    int(updated.use_cloned_voice),
                    updated.tier,
                    json.dumps(updated.refs, ensure_ascii=False),
                    updated.ckpt_path,
                    updated.tier3_status,
                ),
            )
            conn.commit()
        return updated

    # ── Tier helpers ───────────────────────────────────────────────────────
    def set_tier(self, user_id: int, guild_id: int, tier: int, refs: list[str]) -> UserSettings:
        """Tier 1·2 — 참조 WAV 경로 저장 + use_cloned 자동 활성화."""
        return self.upsert(
            user_id, guild_id,
            tier=tier, refs=refs, use_cloned_voice=True,
        )

    def set_tier3_ready(self, user_id: int, guild_id: int, ckpt_path: str) -> UserSettings:
        """Tier 3 학습 완료 — 어댑터 경로 활성화."""
        return self.upsert(
            user_id, guild_id,
            tier=3, ckpt_path=ckpt_path,
            tier3_status="ready", use_cloned_voice=True,
        )

    def set_tier3_status(self, user_id: int, guild_id: int, status: str) -> None:
        self.upsert(user_id, guild_id, tier3_status=status)

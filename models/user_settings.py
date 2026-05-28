from dataclasses import dataclass, field


@dataclass
class UserSettings:
    user_id: int
    guild_id: int
    voice: str = "ko-KR-SunHiNeural"
    speed: str = "+0%"
    use_cloned_voice: bool = False

    # ── Tier 등록 ──
    tier: int = 1                            # 1 Instant · 2 Enhanced · 3 Pro
    refs: list[str] = field(default_factory=list)  # WAV 절대 경로들 (Tier 1: 1개, Tier 2: 5~15개)
    ckpt_path: str | None = None             # Tier 3 — fine-tuned 체크포인트 경로
    tier3_status: str | None = None          # queued · training · ready · failed

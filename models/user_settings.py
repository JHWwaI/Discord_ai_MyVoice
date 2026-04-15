from dataclasses import dataclass


@dataclass
class UserSettings:
    user_id: int
    guild_id: int
    voice: str = "ko-KR-SunHiNeural"
    speed: str = "+0%"
    use_cloned_voice: bool = False

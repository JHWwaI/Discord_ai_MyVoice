import glob
import os
import shutil

from dotenv import load_dotenv

load_dotenv()

# ── 일반 설정 ──
TTS_VOICE_DEFAULT: str = os.getenv("TTS_VOICE_DEFAULT", "ko-KR-SunHiNeural")
TTS_SPEED_DEFAULT: str = os.getenv("TTS_SPEED_DEFAULT", "+0%")
TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
DB_PATH: str = os.getenv("DB_PATH", "voicebridge.db")
IDLE_TIMEOUT: int = int(os.getenv("IDLE_TIMEOUT", "60"))
CLONED_VOICE_URL: str = os.getenv("CLONED_VOICE_URL", "")
ERROR_WEBHOOK_URL: str = os.getenv("ERROR_WEBHOOK_URL", "")

# ── Tier 등록 ──
VOICE_DATA_DIR: str = os.getenv("VOICE_DATA_DIR", "voice_data")
TIER2_MIN_REFS: int = int(os.getenv("TIER2_MIN_REFS", "5"))
TIER2_MAX_REFS: int = int(os.getenv("TIER2_MAX_REFS", "15"))
TIER3_MIN_WAVS: int = int(os.getenv("TIER3_MIN_WAVS", "100"))
TIER3_MAX_WAVS: int = int(os.getenv("TIER3_MAX_WAVS", "400"))

# ── Discord 토큰 — 봇 실행 시에만 필요 (lazy) ──
DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")


def require_discord_token() -> str:
    """봇 시작 직전에 호출 — 토큰 없으면 그때 에러."""
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
    return DISCORD_BOT_TOKEN


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    matches = glob.glob(
        os.path.join(winget_base, "Gyan.FFmpeg*", "**", "ffmpeg.exe"),
        recursive=True,
    )
    if matches:
        return matches[0]
    return ""  # 없으면 빈 문자열 — 봇 실행 시점에 체크


FFMPEG_PATH: str = _find_ffmpeg()


def require_ffmpeg() -> str:
    if not FFMPEG_PATH:
        raise FileNotFoundError(
            "ffmpeg를 찾을 수 없습니다. ffmpeg를 설치하거나 PATH에 추가해 주세요."
        )
    return FFMPEG_PATH

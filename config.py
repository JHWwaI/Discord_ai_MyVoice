import glob
import os
import shutil

from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")

TTS_VOICE_DEFAULT: str = os.getenv("TTS_VOICE_DEFAULT", "ko-KR-SunHiNeural")
TTS_SPEED_DEFAULT: str = os.getenv("TTS_SPEED_DEFAULT", "+0%")
TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
DB_PATH: str = os.getenv("DB_PATH", "voicebridge.db")
IDLE_TIMEOUT: int = int(os.getenv("IDLE_TIMEOUT", "60"))  # 초 단위
CLONED_VOICE_URL: str = os.getenv("CLONED_VOICE_URL", "")  # Kaggle ngrok URL
ERROR_WEBHOOK_URL: str = os.getenv("ERROR_WEBHOOK_URL", "")  # Discord 에러 알림 웹훅


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
    raise FileNotFoundError(
        "ffmpeg를 찾을 수 없습니다. ffmpeg를 설치하거나 PATH에 추가해주세요."
    )


FFMPEG_PATH: str = _find_ffmpeg()

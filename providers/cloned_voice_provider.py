import aiohttp

from config import CLONED_VOICE_URL
from providers.base import TTSProvider


class ClonedVoiceProvider(TTSProvider):
    """Kaggle XTTS v2 서버에 HTTP 요청해 개인 음성으로 합성한다."""

    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str
    ) -> None:
        if not CLONED_VOICE_URL:
            raise RuntimeError(
                "CLONED_VOICE_URL이 설정되지 않았습니다. "
                ".env에 Kaggle ngrok URL을 추가하세요."
            )

        url = CLONED_VOICE_URL.rstrip("/") + "/synthesize"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"text": text},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                resp.raise_for_status()
                audio_bytes = await resp.read()

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

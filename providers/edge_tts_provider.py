import edge_tts

from providers.base import CloneRequest, TTSProvider


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge TTS 기반 프로바이더."""

    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str,
        clone: CloneRequest | None = None,
    ) -> None:
        # Edge TTS는 clone 정보 무시 (일반 voice·speed만 사용)
        communicate = edge_tts.Communicate(text, voice, rate=speed)
        await communicate.save(output_path)

import edge_tts

from providers.base import TTSProvider


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge TTS 기반 프로바이더."""

    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str
    ) -> None:
        communicate = edge_tts.Communicate(text, voice, rate=speed)
        await communicate.save(output_path)

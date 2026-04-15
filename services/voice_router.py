from models.user_settings import UserSettings
from providers.base import TTSProvider
from providers.cloned_voice_provider import ClonedVoiceProvider
from providers.edge_tts_provider import EdgeTTSProvider


class VoiceRouter:
    """
    사용자 설정에 따라 적절한 TTS 프로바이더를 선택한다.
    향후 voice cloning 구현 시 분기 로직만 수정하면 된다.
    """

    def __init__(self) -> None:
        self._edge = EdgeTTSProvider()
        self._cloned = ClonedVoiceProvider()

    def get_provider(self, settings: UserSettings) -> TTSProvider:
        if settings.use_cloned_voice:
            return self._cloned
        return self._edge

    async def synthesize(
        self, text: str, settings: UserSettings, output_path: str
    ) -> None:
        provider = self.get_provider(settings)
        await provider.synthesize(text, settings.voice, settings.speed, output_path)

from models.user_settings import UserSettings
from providers.base import CloneRequest, TTSProvider
from providers.cloned_voice_provider import ClonedVoiceProvider
from providers.edge_tts_provider import EdgeTTSProvider


class VoiceRouter:
    """
    사용자 설정에 따라 적절한 TTS 프로바이더를 선택하고
    Tier 1·2·3 컨텍스트를 ClonedVoiceProvider에 전달한다.
    """

    def __init__(self) -> None:
        self._edge = EdgeTTSProvider()
        self._cloned = ClonedVoiceProvider()

    def get_provider(self, settings: UserSettings) -> TTSProvider:
        if not settings.use_cloned_voice:
            return self._edge
        # Tier 3 학습 완료 여부 확인
        if settings.tier == 3 and not (settings.tier3_status == "ready" and settings.ckpt_path):
            # 학습 완료 안 됨 → Edge로 fallback
            return self._edge
        return self._cloned

    def _build_clone_request(self, settings: UserSettings) -> CloneRequest | None:
        if not settings.use_cloned_voice:
            return None
        if not settings.refs and not settings.ckpt_path:
            return None
        return CloneRequest(
            tier=settings.tier,
            refs=settings.refs,
            ckpt_path=settings.ckpt_path,
            language="ko",
        )

    async def synthesize(
        self, text: str, settings: UserSettings, output_path: str
    ) -> None:
        provider = self.get_provider(settings)
        clone_req = self._build_clone_request(settings) if isinstance(provider, ClonedVoiceProvider) else None
        await provider.synthesize(
            text, settings.voice, settings.speed, output_path, clone=clone_req,
        )

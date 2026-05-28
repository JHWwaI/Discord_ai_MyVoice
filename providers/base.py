from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CloneRequest:
    """ClonedVoiceProvider용 확장 컨텍스트.

    합성 호출 시 사용자별 Tier 등록 정보를 함께 넘긴다.
    Provider는 tier에 따라 다른 페이로드를 GPU 서버에 보낸다.
    """
    tier: int = 1                          # 1 Instant · 2 Enhanced · 3 Pro
    refs: list[str] = field(default_factory=list)  # Tier 1·2 — 참조 WAV 절대 경로들
    ckpt_path: str | None = None           # Tier 3 — fine-tuned 어댑터 경로
    language: str = "ko"


class TTSProvider(ABC):
    """
    TTS 프로바이더 인터페이스.
    새 TTS 엔진 추가 시 이 클래스를 상속하고 synthesize만 구현하면 된다.
    """

    @abstractmethod
    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str,
        clone: CloneRequest | None = None,
    ) -> None:
        """텍스트를 음성 파일로 변환한다.

        clone이 주어지면 음성 복제 모드 (Tier 1·2·3).
        clone이 None이면 일반 TTS (예: Edge TTS).
        """
        ...

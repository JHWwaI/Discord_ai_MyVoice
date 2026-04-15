from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """
    TTS 프로바이더 인터페이스.
    새 TTS 엔진 추가 시 이 클래스를 상속하고 synthesize만 구현하면 된다.
    """

    @abstractmethod
    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str
    ) -> None:
        """텍스트를 음성 파일(mp3)로 변환한다."""
        ...

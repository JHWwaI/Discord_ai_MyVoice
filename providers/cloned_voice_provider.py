import os

import aiohttp

from config import CLONED_VOICE_URL
from providers.base import CloneRequest, TTSProvider


class ClonedVoiceProvider(TTSProvider):
    """원격 XTTS v2 서버(Kaggle/Colab)에 HTTP 요청해 음성 복제 합성.

    Payload (tier에 따라 분기):
      tier=1 · refs=[ref.wav]               → 단일 참조 zero-shot
      tier=2 · refs=[r1.wav, r2.wav, ...]   → 다중 참조 평균 (Enhanced)
      tier=3 · ckpt_path=/path/to/best.pth  → 사용자 fine-tuned 어댑터 로드
    """

    async def synthesize(
        self, text: str, voice: str, speed: str, output_path: str,
        clone: CloneRequest | None = None,
        user_id: int | None = None,
    ) -> None:
        if not CLONED_VOICE_URL:
            raise RuntimeError(
                "CLONED_VOICE_URL이 설정되지 않았습니다. "
                ".env에 Kaggle/Colab ngrok URL을 추가하세요."
            )

        url = CLONED_VOICE_URL.rstrip("/") + "/synthesize"

        # ── 기본 payload ──
        payload: dict[str, object] = {
            "text": text,
            "language": (clone.language if clone else "ko"),
            "tier": (clone.tier if clone else 1),
        }
        if user_id is not None:
            payload["user_id"] = str(user_id)
        # ── Tier별 추가 필드 ──
        if clone is not None:
            if clone.tier in (1, 2):
                # 서버가 파일 경로(서버 측 마운트) 또는 base name으로 식별하도록 전달
                payload["refs"] = [os.path.basename(p) for p in clone.refs]
            elif clone.tier == 3 and clone.ckpt_path:
                payload["ckpt"] = os.path.basename(clone.ckpt_path)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=180),  # Tier 3은 어댑터 로드 시간 ↑
            ) as resp:
                resp.raise_for_status()
                audio_bytes = await resp.read()

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

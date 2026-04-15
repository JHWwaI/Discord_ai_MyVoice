# ============================================================
# Yourvoice Bot — Kaggle XTTS v2 서버
# Kaggle Notebook에 이 파일 내용을 셀 단위로 붙여넣어 실행하세요.
# ============================================================

# ── Cell 1: 패키지 설치 ─────────────────────────────────────
# !pip install -q TTS fastapi uvicorn pyngrok nest-asyncio

# ── Cell 2: 임포트 ──────────────────────────────────────────
import os
import tempfile
import threading

import nest_asyncio
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pngrok import ngrok          # pip install pyngrok
from pydantic import BaseModel
from TTS.api import TTS

nest_asyncio.apply()

# ── Cell 3: 모델 로드 ────────────────────────────────────────
# GPU 사용 가능 여부 자동 감지 (Kaggle T4 → cuda)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}")

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(DEVICE)

# ── Cell 4: 음성 샘플 경로 설정 ──────────────────────────────
# Kaggle에 Dataset으로 업로드한 본인 음성 파일 경로
# (Add Data → 직접 업로드 → /kaggle/input/<dataset-name>/<file>.wav)
SPEAKER_WAV = "/kaggle/input/my-voice-sample/sample.wav"

if not os.path.exists(SPEAKER_WAV):
    raise FileNotFoundError(
        f"음성 샘플 파일을 찾을 수 없습니다: {SPEAKER_WAV}\n"
        "Kaggle 데이터셋으로 WAV 파일을 업로드하고 경로를 수정하세요."
    )

# ── Cell 5: FastAPI 앱 ───────────────────────────────────────
app = FastAPI()


class SynthRequest(BaseModel):
    text: str
    language: str = "ko"


@app.post("/synthesize")
async def synthesize(req: SynthRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text is empty")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name

    try:
        tts.tts_to_file(
            text=req.text,
            speaker_wav=SPEAKER_WAV,
            language=req.language,
            file_path=out_path,
        )
        with open(out_path, "rb") as f:
            audio = f.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

    return Response(content=audio, media_type="audio/wav")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Cell 6: ngrok + 서버 시작 ────────────────────────────────
# ngrok 무료 계정 토큰: https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_TOKEN = "여기에_ngrok_토큰_입력"

ngrok.set_auth_token(NGROK_TOKEN)
public_url = ngrok.connect(8000)
print(f"\n{'='*50}")
print(f"Public URL: {public_url}")
print(f"이 URL을 .env의 CLONED_VOICE_URL에 입력하세요")
print(f"{'='*50}\n")

config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)

# Notebook에서는 await로 실행
await server.serve()

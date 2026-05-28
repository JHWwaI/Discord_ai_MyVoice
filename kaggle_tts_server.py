# ============================================================
# VoiceBridge — Kaggle / Colab XTTS v2 서버
# Tier 1·2·3 지원: 단일/다중 참조 zero-shot + fine-tuned 어댑터 로드
# ============================================================

# ── Cell 1: 패키지 설치 ─────────────────────────────────────
!pip install -q git+https://github.com/idiap/coqui-ai-TTS fastapi "uvicorn[standard]" pyngrok nest-asyncio soundfile python-multipart

# ── Cell 2: 임포트 ──────────────────────────────────────────
import glob
import os
import tempfile

import nest_asyncio
import shutil
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from pyngrok import ngrok
from TTS.api import TTS
from typing import List

nest_asyncio.apply()

# ── Cell 3: 경로 설정 ────────────────────────────────────────
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {DEVICE}")

# 사용자별 WAV 폴더 (Drive 또는 Kaggle dataset 마운트)
#   Tier 1·2: {VOICE_ROOT}/user_{user_id}/tier{N}/*.wav
#   Tier 3:   {CKPT_ROOT}/{filename}.pth
VOICE_ROOT = os.environ.get("VOICE_ROOT", "/content/voice_data")
CKPT_ROOT  = os.environ.get("CKPT_ROOT",  "/content/checkpoints")

# 기본 모델 (Tier 1·2)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(DEVICE)

# Tier 3 — 어댑터 캐시 (사용자별 fine-tuned 모델)
_tuned_cache: dict[str, "Xtts"] = {}


def _resolve_refs(refs: list[str]) -> list[str]:
    """파일명만 받았으면 VOICE_ROOT에서 절대 경로 찾기."""
    out = []
    for r in refs:
        if os.path.isabs(r) and os.path.exists(r):
            out.append(r); continue
        # base name만 받았을 때 — voice_data 전체에서 검색
        found = glob.glob(os.path.join(VOICE_ROOT, "**", r), recursive=True)
        if found:
            out.append(found[0])
    return out


def _load_tuned(ckpt_name: str):
    """Tier 3 — 사용자 fine-tuned 체크포인트 로드 (캐시됨)."""
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    if ckpt_name in _tuned_cache:
        return _tuned_cache[ckpt_name]

    ckpt_path = ckpt_name if os.path.isabs(ckpt_name) else os.path.join(CKPT_ROOT, ckpt_name)
    if not os.path.exists(ckpt_path):
        raise FileNotFoundError(f"checkpoint not found: {ckpt_path}")
    cfg_path = os.path.join(os.path.dirname(ckpt_path), "config.json")

    cfg = XttsConfig(); cfg.load_json(cfg_path)
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_path=ckpt_path)
    model.to(DEVICE).eval()
    _tuned_cache[ckpt_name] = model
    print(f"loaded fine-tuned: {ckpt_path}")
    return model


# ── Cell 4: FastAPI 앱 ───────────────────────────────────────
app = FastAPI()


class SynthRequest(BaseModel):
    text: str
    language: str = "ko"
    tier:     int = 1
    refs:     list[str] = []     # Tier 1·2 — WAV 파일명들
    ckpt:     str | None = None  # Tier 3 — 체크포인트 파일명


@app.post("/synthesize")
async def synthesize(req: SynthRequest):
    if not req.text.strip():
        raise HTTPException(400, "text is empty")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name

    try:
        # ── Tier 1·2 — zero-shot (단일/다중 참조) ──
        if req.tier in (1, 2):
            refs = _resolve_refs(req.refs)
            if not refs:
                raise HTTPException(400, "no valid reference WAVs found")
            tts.tts_to_file(
                text=req.text,
                speaker_wav=refs if len(refs) > 1 else refs[0],   # 다중이면 list 전달
                language=req.language,
                file_path=out_path,
            )

        # ── Tier 3 — fine-tuned 어댑터 + 참조 ──
        elif req.tier == 3:
            if not req.ckpt:
                raise HTTPException(400, "ckpt required for tier 3")
            model = _load_tuned(req.ckpt)
            from TTS.tts.configs.xtts_config import XttsConfig
            cfg = XttsConfig(); cfg.load_json(os.path.join(CKPT_ROOT, "config.json"))
            ref = _resolve_refs(req.refs)[0] if req.refs else None
            out = model.synthesize(
                req.text, cfg,
                speaker_wav=ref, language=req.language,
                gpt_cond_len=3, temperature=0.7,
            )
            sf.write(out_path, out["wav"], samplerate=24000)
        else:
            raise HTTPException(400, f"unknown tier: {req.tier}")

        with open(out_path, "rb") as f:
            audio = f.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

    return Response(content=audio, media_type="audio/wav")


@app.post("/upload_refs")
async def upload_refs(
    user_id: str = Form(...),
    tier:    int = Form(...),
    files:   List[UploadFile] = File(...),
):
    """봇 /api/register 가 자동 전송 — 참조 WAV 를 VOICE_ROOT 에 저장.

    저장 위치: {VOICE_ROOT}/user_{user_id}/tier{N}/
    기존 파일은 비움 (재등록 안전).
    """
    if tier not in (1, 2, 3):
        raise HTTPException(400, f"unknown tier {tier}")
    save_dir = os.path.join(VOICE_ROOT, f"user_{user_id}", f"tier{tier}")
    if os.path.isdir(save_dir):
        for f in os.listdir(save_dir):
            try: os.remove(os.path.join(save_dir, f))
            except OSError: pass
    os.makedirs(save_dir, exist_ok=True)

    stored = []
    for i, up in enumerate(files, 1):
        # 봇 측에서 이미 24kHz mono WAV 로 변환됐다고 가정
        out_name = f"{i:03d}.wav"
        out_path = os.path.join(save_dir, out_name)
        with open(out_path, "wb") as fout:
            shutil.copyfileobj(up.file, fout)
        stored.append(out_name)
    return {"ok": True, "tier": tier, "user_id": user_id,
            "stored": stored, "dir": save_dir}


class LoadCkptRequest(BaseModel):
    ckpt: str   # 절대경로 또는 CKPT_ROOT 하위 파일명


@app.post("/load_ckpt")
async def load_ckpt(req: LoadCkptRequest):
    """Tier 3 어댑터 사전 로드 — 첫 합성 지연 제거 용.

    tier3_worker.py --mark-ready --notify-server 가 호출.
    """
    try:
        _load_tuned(req.ckpt)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"load failed: {e}")
    return {"ok": True, "loaded": list(_tuned_cache.keys())}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "tier3_loaded": list(_tuned_cache.keys()),
    }


# ── Cell 5: ngrok + 서버 시작 ────────────────────────────────
NGROK_TOKEN = os.environ.get("NGROK_TOKEN", "")  # Kaggle Secrets 또는 직접 입력
if not NGROK_TOKEN:
    raise RuntimeError("NGROK_TOKEN 환경변수가 필요합니다 (https://dashboard.ngrok.com)")

ngrok.set_auth_token(NGROK_TOKEN)
public_url = ngrok.connect(8000)
print(f"\n{'='*60}")
print(f"Public URL: {public_url}")
print(f"이 URL을 .env의 CLONED_VOICE_URL에 입력하세요")
print(f"{'='*60}\n")

config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
server = uvicorn.Server(config)
await server.serve()

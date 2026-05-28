# VoiceBridge — Tier 3 Fine-tune 전문가 운영 가이드

> 본인 음성 300문장(30~45분 녹음) → 2~4시간 Colab 학습 →
> Discord 음성 채널에서 본인 전용 fine-tuned 모델로 발화하는 **end-to-end 가이드**.
>
> 일반 사용자는 Tier 1(6초) / Tier 2(1~3분)로 충분. 본 문서는 **본인·콘텐츠 제작자·시연용**.

---

## 0. 준비물

| 항목 | 비고 |
|---|---|
| **로컬 PC** | Windows/macOS, Python 3.11+, ffmpeg |
| **Discord 봇** | `python main.py` 로 실행 중 |
| **Discord 식별 정보** | User / Guild / Voice Channel ID (개발자 모드 ON) |
| **Google 계정 + Drive** | 음성 데이터·체크포인트 저장 (10GB 이상 권장) |
| **Colab Free or Pro** | T4 GPU. Free 도 가능 (2~4시간 anti-idle) |
| **ngrok 계정** | 추론 서버 노출용 (Free OK) |
| **마이크** | USB 콘덴서 또는 정숙한 환경의 노트북 마이크 |

선택:
- `rclone` — Drive ↔ 로컬 동기화 자동화
- Audacity / Reaper — 녹음 + 정규화

---

## 1. 전체 데이터 흐름

```
[로컬: 녹음]
  └─ tuning/1_data/recording_script.md (300문장)
       │
       │ 24kHz · 16-bit · mono · 잡음↓
       ▼
  voice_data/user_<id>/tier3/001.wav ... 300.wav
       │
       │ ① 웹 UI ④ 카드 또는 /api/register tier=3
       ▼
[로컬: HTTP Bridge]
  ├─ ffmpeg 변환·검증
  ├─ DB: tier3_jobs INSERT (status=queued)
  └─ job_id 응답
       │
       │ ② tier3_worker --watch 가 감지 → SOP 출력
       ▼
[운영자: 수동]
  ├─ rclone copy voice_data/user_<id>/tier3 gdrive:xtts_personal/job_<id>/my_voice
  ├─ python tuning/1_data/prepare_personal.py ...
  └─ rclone copy ./tuning/manifest_<id>/* gdrive:xtts_personal/job_<id>/manifest
       │
       │ ③ Colab 노트북 열기 → fit (2~4시간)
       ▼
[Colab T4 GPU]
  └─ /content/drive/MyDrive/xtts_personal/job_<id>/runs/.../best_model.pth
       │
       │ ④ tier3_worker --mark-ready --ckpt <path> --notify-server
       ▼
[추론 서버: kaggle_tts_server]
  ├─ POST /load_ckpt → _tuned_cache 사전 로드
  └─ user_settings.tier=3, ckpt_path 갱신
       │
       │ ⑤ Discord /say 또는 웹 ③ 카드
       ▼
[Discord 음성 채널]
  └─ 본인 fine-tuned 음성으로 발화 🔊
```

---

## 2. Step-by-step

### Step 1. 봇 + 추론 서버 띄우기 (5분)

**로컬 봇:**
```powershell
cd C:\Users\dolch\OneDrive\Desktop\2026\취준\프로젝트\Yourvoice_bot
.\venv\Scripts\activate
python main.py
# → "HTTP bridge → http://0.0.0.0:8090" 확인
```

**Colab 추론 서버:**
1. https://colab.research.google.com → 새 노트북 → T4 GPU
2. `kaggle_tts_server.py` 셀별 복붙
3. `os.environ["NGROK_TOKEN"] = "..."` 입력
4. 마지막 셀 실행 → `Public URL: https://xxxx.ngrok-free.app`
5. 로컬 `.env`:
   ```
   CLONED_VOICE_URL=https://xxxx.ngrok-free.app
   ```
6. 봇 재시작 (`Ctrl+C` → `python main.py`)

### Step 2. 녹음 (30~45분)

`tuning/1_data/recording_script.md` 열고 1~300번 문장을 순서대로 녹음.

| 항목 | 권장 |
|---|---|
| 파일명 | `001.wav` ... `300.wav` |
| 포맷 | 24kHz · 16-bit · mono WAV |
| 환경 | 에어컨/팬 끄기, 자연스러운 평소 톤 |
| 마이크 거리 | 일정 (15~30cm) |
| 문장 사이 | 0.5~1초 침묵 OK (자동 trim 됨) |
| 발음 | 또박또박, 일상 톤. 연기 톤 X |

녹음 후 → `voice_data/user_<your_discord_id>/tier3/` 폴더에 모두 넣기.

### Step 3. 웹에서 학습 신청

1. http://localhost:8090 접속
2. ① 식별정보 — User ID / Guild ID 입력
3. ④ Tier 3 카드 → "WAV 파일 다중 선택" → 100~400개 선택
4. "📤 학습 신청" → 응답:
   ```json
   { "ok": true, "tier": 3, "stored": 300, "job_id": 1 }
   ```
5. 카드가 10초마다 자동 폴링 시작 → 🟡 queued 표시

### Step 4. Worker 데몬으로 SOP 받기

별도 터미널에서:
```powershell
python tier3_worker.py --watch
```

신청이 감지되면 즉시 다음 명령들을 인쇄해줌:
```
📥 신규 학습 신청 — Job #1
   user_id=... · guild_id=... · wavs=300
   wav_dir=C:\...\voice_data\user_<id>\tier3
다음 단계:
  1) rclone copy "C:\...\tier3" gdrive:xtts_personal/job_1/my_voice
  2) python tuning/1_data/prepare_personal.py --wav-dir ...
  3) Colab 노트북 열기 ...
  4) python tier3_worker.py --mark-training 1
  5) python tier3_worker.py --mark-ready 1 --ckpt ... --notify-server
```

### Step 5. Manifest 생성 (로컬, 1분)

```powershell
python tuning/1_data/prepare_personal.py `
    --wav-dir voice_data/user_<id>/tier3 `
    --script tuning/1_data/recording_script.md `
    --out tuning/manifest_1 `
    --normalize
```

출력:
- `tuning/manifest_1/metadata_train.csv` (95%)
- `tuning/manifest_1/metadata_val.csv` (5%)
- 통계 (총 시간, 평균 길이, 누락 수)

### Step 6. Drive 업로드

**옵션 A — rclone (자동):**
```powershell
rclone copy voice_data/user_<id>/tier3 gdrive:xtts_personal/job_1/my_voice
rclone copy tuning/manifest_1 gdrive:xtts_personal/job_1/manifest
```

**옵션 B — 수동:**
- Drive 웹에서 `MyDrive/xtts_personal/job_1/my_voice/`, `MyDrive/xtts_personal/job_1/manifest/` 폴더 만들고 업로드.

### Step 7. Colab 학습 (2~4시간)

1. `tuning/2_train/train_personal_colab.ipynb` Colab 에 업로드
2. T4 GPU 선택
3. **셀 3 (Drive 마운트) 수정**:
   ```python
   DRIVE_ROOT = '/content/drive/MyDrive/xtts_personal/job_1'  # ← job ID 반영
   ```
4. 셀 0 ~ 9 순차 실행
5. **셀 2 anti-idle 반드시 켜기** (Free 90분 자동 끊김 방지)
6. 학습 시작 직후 로컬에서:
   ```powershell
   python tier3_worker.py --mark-training 1
   ```
7. 셀 8 (`trainer.fit()`) 완료 대기 — 약 2~4시간
8. 셀 9 출력:
   ```
   Best: /content/drive/MyDrive/xtts_personal/job_1/runs/xtts_personal-<timestamp>/best_model.pth
   ```

### Step 8. 어댑터 등록

로컬에서:
```powershell
python tier3_worker.py --mark-ready 1 `
    --ckpt /content/drive/MyDrive/xtts_personal/job_1/runs/.../best_model.pth `
    --notify-server
```

내부 동작:
1. `tier3_jobs.status = ready`
2. `user_settings.tier = 3`, `ckpt_path` 저장
3. 추론 서버 `POST /load_ckpt` 호출 → `_tuned_cache` 사전 로드
4. UI ④ 카드가 자동 폴링으로 🟢 ready 표시

⚠️ `--notify-server` 가 동작하려면 `.env` 의 `CLONED_VOICE_URL` 이 살아있고
   추론 서버가 학습한 ckpt 파일에 **접근 가능** 해야 함.
   → Colab에서 같은 노트북으로 추론 서버를 띄웠으면 자동으로 같은 Drive 경로 접근 가능.

### Step 9. Discord 라이브 합성

```
/join
/say text:안녕하세요, 이것은 본인 fine-tuned 모델로 합성한 음성입니다.
```

또는 웹 ③ 카드 → "📨 Discord로 전송".

내부 라우팅:
```
VoiceRouter.route(user)
  → settings.tier == 3 AND tier3_status == "ready"
  → ClonedVoiceProvider
       payload: {tier:3, ckpt:"best_model.pth", refs:["001.wav"]}
  → kaggle_tts_server /synthesize
       _tuned_cache["best_model.pth"] 사용 (사전 로드됨)
  → WAV bytes
  → Discord voice channel ffmpeg 스트림
```

---

## 3. 운영 시나리오

### 3.1 학습이 실패하면

**OOM (Out Of Memory):**
- 셀 6 에서 `config.batch_size = 1`, `config.grad_accum_steps = 8` 로 조정
- `config.mixed_precision = True` (이미 True 인지 확인)

**데이터 부족 / NaN:**
- 100개 미만이면 zero-shot 보다 못한 결과 가능. 200개 이상 권장.
- 녹음 품질 확인 — `librosa` 로 SNR 측정.

```powershell
python tier3_worker.py --mark-failed 1 --error "OOM at step 12000"
```

### 3.2 학습 중간 Colab 끊김

Trainer 가 `restore_path` 로 자동 resume. 마지막 checkpoint 부터 재개.
1. Colab 새로 띄우기
2. 셀 0~7 다시 실행 → 셀 7 의 `restore = ckpts[-1]` 가 자동 감지
3. 셀 8 `trainer.fit()` 다시 실행

### 3.3 다른 사용자가 또 신청

현 단계는 **순차 처리**. `--watch` 가 다음 queued 를 안내하면 같은 순서로 처리.
다중 GPU 워커 풀이 필요하면 RunPod/Vast.ai + 메시지 큐 (Redis) 로 확장.

### 3.4 어댑터 캐시 메모리 정리

추론 서버 재시작 (Colab 셀 다시 실행) — `_tuned_cache` 초기화.
또는 코드에 LRU 추가:
```python
from functools import lru_cache
@lru_cache(maxsize=3)
def _load_tuned(ckpt_name): ...
```

---

## 4. 품질 검증

학습 직후 청취 비교 (Colab 셀 10):
- Base zero-shot (6초 참조)
- Fine-tuned

객관 지표 (Whisper CER):
```bash
# Base
python tuning/3_eval/run_eval.py \
    --speaker voice_data/user_<id>/tier3/001.wav \
    --model base --out base.json

# Fine-tuned
python tuning/3_eval/run_eval.py \
    --ckpt /content/drive/.../best_model.pth \
    --model finetuned --out tuned.json

# 비교 리포트
python tuning/3_eval/compare.py --base base.json --tuned tuned.json \
    --out comparison.md
```

목표:
| 지표 | Base | Fine-tuned 목표 |
|---|---|---|
| CER mean | 12~18% | < 8% |
| CER p95 | ~30% | < 15% |
| Latency | 2~3s | 2~3s (동일) |

---

## 5. 보안·법적 고려

| 항목 | 처리 |
|---|---|
| 사용자 음성 데이터 보관 | `voice_data/` 는 로컬만. Drive 업로드 시 본인 계정 한정. |
| 학습 모델 공유 | **금지** — 본인 외 사용 불가 (음성 권리). |
| 모델 라이선스 | Coqui Public Model License — **비상업 한정**. |
| 데이터 라이선스 (KSS 사전학습 변형) | CC BY-NC-SA 4.0 — 비상업 한정. |
| 사용자 동의 | 본인 음성 학습 → 본인 사용 한정으로만 유지. |

상업화하려면 Coqui Enterprise License 필요.

---

## 6. 자주 막히는 지점

| 증상 | 원인 | 해결 |
|---|---|---|
| `/api/register` 가 `tier 3 requires 100~400 wavs` 거부 | 파일 부족 / 초과 | `.env` 의 `TIER3_MIN_WAVS`, `TIER3_MAX_WAVS` 조정 가능 |
| Colab `nvidia-smi: command not found` | CPU 런타임 | 런타임 → 유형 변경 → GPU (T4) |
| `assert os.path.exists(f'{MANIFEST}/metadata_train.csv')` 실패 | Drive 업로드 누락 | manifest 폴더 확인 |
| `trainer.fit()` 첫 step 매우 느림 | XTTS gpt_cond 캐싱 워밍업 | 정상 — 두 번째 epoch 부터 빠름 |
| `--notify-server` 가 timeout | ngrok URL 만료 (12h Free) | URL 재발급 후 재시도 또는 첫 `/synthesize` 시 lazy load |
| Discord 봇이 여전히 edge-tts 로 발화 | `tier3_status != "ready"` 또는 `ckpt_path` 미설정 | `python tier3_worker.py --mark-ready` 재실행 |

---

## 7. 한 줄 정리 — "왜 이 구조인가"

> Fine-tune 은 **사용자별 GPU 2~4시간 + 운영자 개입** 이 필요한 고비용 작업이므로
> 동기 API 로 약속하지 않고 **SQLite job queue + 운영자 CLI + 추론 서버 lazy 로드**
> 로 비동기 처리. 학습 완료 전엔 라우터가 Tier 1 으로 자동 fallback 해
> **서비스 가용성을 유지** 한다.

이게 본 시스템의 핵심 설계 결정.

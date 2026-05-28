# VoiceBridge E2E 검증 — 4단계 시연 가이드

`.env` 에 `DISCORD_BOT_TOKEN`·`CLONED_VOICE_URL` 둘 다 들어 있는 상태 기준.

---

## Phase 1 — Discord 봇 띄우기 (5분)

### 1-1. 의존성 확인
```powershell
cd C:\Users\dolch\OneDrive\Desktop\2026\취준\프로젝트\Yourvoice_bot
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 1-2. ffmpeg 확인
```powershell
where.exe ffmpeg
# 없으면:
winget install Gyan.FFmpeg
```

### 1-3. 봇 시작
```powershell
python main.py
```

### ✅ 성공 시 출력
```
Logged in as VoiceBridge (ID: ...)
Slash commands synced.
```

### ❌ 실패하면
- `DISCORD_BOT_TOKEN is not set` → `.env` 토큰 확인
- `ffmpeg를 찾을 수 없습니다` → ffmpeg 설치
- `intents` 에러 → Discord Developer Portal → Bot → Privileged Intents (Message Content) ON

---

## Phase 2 — XTTS GPU 서버 (Colab Free, 10분 설정 + 모델 다운로드)

### 2-1. Colab 새 노트북 만들기
1. https://colab.research.google.com → 새 노트북
2. **런타임 → 런타임 유형 변경 → GPU (T4)** 선택

### 2-2. kaggle_tts_server.py 셀별로 복사
`Yourvoice_bot/kaggle_tts_server.py` 파일 열어서 `# ── Cell N` 주석 단위로 셀에 붙여넣기.

### 2-3. ngrok 토큰 설정 (Cell 1 또는 별도 셀에서)
```python
import os
os.environ["NGROK_TOKEN"] = "여기에_ngrok_토큰"
```
ngrok 토큰: https://dashboard.ngrok.com/get-started/your-authtoken

### 2-4. 사용자 음성 데이터 업로드
**옵션 A — Google Drive 마운트 (재사용 편함)**:
```python
from google.colab import drive
drive.mount('/content/drive')
# Drive에 xtts_data/user_<your_id>/tier1/sample.wav 미리 업로드
os.environ["VOICE_ROOT"] = "/content/drive/MyDrive/xtts_data"
```

**옵션 B — Colab에 직접 업로드**:
```python
from google.colab import files
files.upload()   # 6초 본인 음성 WAV 선택
!mkdir -p /content/voice_data/user_test/tier1
!mv *.wav /content/voice_data/user_test/tier1/
```

### 2-5. 셀 전부 실행 → ngrok URL 확인
출력 마지막에:
```
Public URL: https://xxxx-xx-xx-xx-xx.ngrok-free.app
```

### 2-6. URL을 봇 .env에 반영
로컬 PowerShell:
```powershell
notepad .env
# CLONED_VOICE_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app 로 갱신
```

봇 재시작:
```powershell
# Ctrl+C로 봇 종료 후
python main.py
```

### ✅ 성공 확인
```powershell
curl https://xxxx-xx-xx-xx-xx.ngrok-free.app/health
# {"status":"ok","device":"cuda","tier3_loaded":[]}
```

---

## Phase 3 — 실제 음성 합성 (Tier 1·2 청취 확인)

### 3-1. Discord에서 봇 초대
1. Discord Developer Portal → 본인 봇 → OAuth2 → URL Generator
2. **Scopes**: `bot`, `applications.commands`
3. **Bot Permissions**: Connect, Speak, Send Messages, Use Slash Commands
4. 생성된 URL로 본인 서버에 봇 초대

### 3-2. 음성 채널 입장
```
/join
```

### 3-3. Tier 1 등록 (6초)
```
/register voice tier:1
```
봇이 안내:
> WAV 파일 1~1개를 메시지로 첨부해 주세요. 120초 내. 마지막에 `done`.

**6초짜리 본인 음성 WAV 파일 첨부** → `done` 입력

### 3-4. 합성 테스트
```
/say text:안녕하세요, 테스트 음성입니다.
```

### ✅ 성공 확인
- Discord 음성 채널에서 본인 목소리(zero-shot)로 발화
- 봇 콘솔 로그에 `synthesize` 호출 + `200 OK` 표시

### 3-5. Tier 2 등록 (다중 참조)
```
/register voice tier:2
```
WAV 5~15개 첨부 (한 번에 여러 개 가능) → `done`

```
/say text:긴 문장으로 테스트해보겠습니다, 한국어 발음이 어떻게 들리는지 확인하기 위함입니다.
```

Tier 1 vs Tier 2 청취 비교 가능.

### 3-6. /tier_status 확인
```
/tier_status
```
> **현재 등급**: Tier 2  
> **참조 파일**: 8개  
> **Cloned 사용**: on

---

## Phase 4 — Tier 3 Fine-tune (Colab 2~4시간)

### 4-1. 음성 녹음 (가장 오래 걸림 — 30~45분)
`Yourvoice_bot/tuning/1_data/recording_script.md` 의 300문장을 차례로 녹음.
- 파일명: `001.wav` `002.wav` ... `300.wav`
- 24kHz · 16-bit · mono WAV
- 조용한 환경, 일정 거리

### 4-2. Manifest 생성 (로컬, 1분)
```powershell
cd Yourvoice_bot\tuning
pip install librosa soundfile
python 1_data\prepare_personal.py `
    --wav-dir .\my_voice `
    --script .\1_data\recording_script.md `
    --out .\manifest `
    --normalize
```

### 4-3. Drive 업로드
Drive `xtts_personal/my_voice` + `xtts_personal/manifest` 폴더에 업로드.

### 4-4. Colab에서 학습 (2~4시간)
1. `tuning/2_train/train_personal_colab.ipynb` Colab에 열기
2. 런타임 → GPU (T4)
3. 셀 0 → 9 순차 실행
4. **세션 안 꺼지게 anti-idle 셀 켜둠 (셀 1)**
5. 완료까지 대기

### 4-5. 학습 완료 후 ckpt 경로 확인
```
Best: /content/drive/MyDrive/xtts_personal/runs/xtts_personal_<timestamp>/best_model.pth
```

### 4-6. 봇 측 — Tier 3 신청 (Phase 3과 동일 흐름)
```
/register voice tier:3
```
WAV 100~400개 첨부 → `done`
→ `Job #1 신청 완료`

### 4-7. tier3_worker로 ready 마킹
```powershell
cd C:\Users\dolch\OneDrive\Desktop\2026\취준\프로젝트\Yourvoice_bot
python tier3_worker.py --list
# Job #1 user=... wavs=120 ...

python tier3_worker.py --mark-training 1
# 학습이 완료된 후:
python tier3_worker.py --mark-ready 1 --ckpt /content/drive/.../best_model.pth
```

### 4-8. Kaggle 서버에 어댑터 위치 알리기
Colab 학습한 노트북에서 그대로 inference 서버를 다시 띄우면 `CKPT_ROOT` 환경변수가 학습 결과 폴더를 가리키도록:

```python
import os
os.environ["CKPT_ROOT"] = "/content/drive/MyDrive/xtts_personal/runs/xtts_personal_<timestamp>"
# 그 다음 kaggle_tts_server.py 셀 다시 실행
```

### 4-9. Discord에서 Tier 3 합성 테스트
```
/tier_status      ← Tier 3, status: ready 확인
/say text:긴 문장으로 본인 fine-tuned 음성을 들어봅시다.
```

### ✅ 성공 확인
- Base Tier 1 음성보다 본인 말투·억양이 더 강하게 묻어남
- /tier_status에 ckpt_path 표시됨

---

## 시연 영상/스크린샷 캡처 포인트

| 캡처 | 내용 |
|---|---|
| **시작 화면** | `python main.py` 콘솔 — Slash commands synced |
| **DB 상태** | `sqlite3 voicebridge.db ".tables"` — `user_settings`, `tier3_jobs` |
| **Discord 등록** | `/register voice tier:1` 첨부 + ✅ 반응 |
| **합성 결과** | `/say` 입력 → Discord 음성 채널 화면 녹화 |
| **Tier 비교** | Tier 1 vs Tier 2 vs Tier 3 청취 (오디오 파일 첨부) |
| **Colab 학습 로그** | trainer.fit 출력 + loss 그래프 |
| **/tier_status** | 등급별 출력 |

---

## 문제 발생 시

### Discord 봇 응답 없음
- 봇이 음성 채널에 들어가 있는지 확인 (`/join`)
- 봇 권한: Connect + Speak

### XTTS 서버 timeout
- ngrok URL이 살아있는지: `/health` 호출
- Free 플랜 12시간 만료 후 URL 재발급 필요

### Tier 3 학습 OOM
- batch_size=2 → 1, grad_accum 4 → 8 로 조정
- 데이터 5,000개 → 3,000개로 축소

### 봇 콘솔에 `cache get failed` 경고
- Redis 안 띄워서 (정상 — 캐시만 우회)

---

## 최소 시연 (시간 부족할 때)

면접 영상 30분 안에 다 보여주기 어려우면 **Phase 1 + 3 (Tier 1·2)만**:
- Phase 1: 봇 시작 (1분)
- Phase 3: Tier 1 등록 + /say (3분)
- Phase 3.5: Tier 2 등록 + /say 비교 (3분)
- 총 **7분** — Tier 3은 README로 설명만

이 정도로 충분히 "구현 + 실서비스 동작" 어필 가능.

<div align="center">

# VoiceBridge

[![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)](.)
[![discord.py](https://img.shields.io/badge/discord.py-5865F2?style=flat-square&logo=discord&logoColor=white)](.)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](.)
[![XTTS v2](https://img.shields.io/badge/XTTS_v2-zero--shot-00B4D8?style=flat-square)](.)

</div>

---

텍스트를 입력하면 내 목소리로 Discord 음성 채널에서 대신 발화해주는 AI TTS 봇입니다.

단순 TTS에 그치지 않고, **사용자마다 다른 목소리**로 발화하면서 **여러 명이 동시에 요청해도 충돌 없이 순서대로 재생**되어야 한다는 두 가지 요구사항에서 시작했습니다.

음성 복제는 등록 시간이 길수록 품질이 좋지만, 사용자 입장에서 30분 강제 녹음은 포기 트리거입니다. **3단계 등록 구조**로 사용자 선택권을 줍니다.

| Tier | 등록 시간 | 품질 | 사용자 비중 (가설) |
|---|---|---|---|
| **1 · Instant** | 6초 | 70% | 80% (기본) |
| **2 · Enhanced** | 1~3분 | 80% | 15% (선택) |
| **3 · Pro** | 30분 + 학습 2~4h | 95%+ | 5% (본인·데모) |

자세한 설계는 [`TIER_DESIGN.md`](./TIER_DESIGN.md).

---

## 어떻게 동작하나요

```
/say 텍스트 입력
      │
      ▼
asyncio.Queue 등록    ← 동시 요청 충돌 방지
      │
      ▼
Queue Worker (순차 처리)
  ├─ SQLite에서 사용자 설정 조회 (목소리·언어·속도)
  ├─ Kaggle TTS 서버로 HTTP 요청
  │     └─ XTTS v2로 음성 합성 (zero-shot 복제)
  ├─ WAV 수신 → 임시 파일 저장
  ├─ Discord 음성 채널 재생
  └─ 임시 파일 삭제
```

**왜 asyncio.Queue인가**

여러 유저가 동시에 `/say`를 입력하면 음성이 겹쳐서 재생됩니다. Queue에 순서대로 쌓고 Worker가 하나씩 처리해서 충돌을 막았습니다.

**왜 Kaggle GPU인가**

XTTS v2는 GPU 없이 실행하면 합성이 너무 느립니다. Kaggle T4 GPU를 무료로 활용하고 pyngrok으로 외부에서 접근 가능하게 했습니다.

---

## 폴더 구조

```
VoiceBridge/
├── main.py                        # 봇 진입점, 의존성 주입
├── config.py
├── kaggle_tts_server.py           # Kaggle용 XTTS v2 FastAPI 서버
├── commands/
│   ├── voice_commands.py          # /join /leave /say /stop
│   ├── info_commands.py           # /ping /queue
│   └── settings_commands.py      # /setvoice /setlang
├── services/
│   ├── queue_manager.py           # asyncio.Queue 기반 큐 관리
│   ├── voice_router.py            # TTS 프로바이더 라우팅
│   ├── playback_service.py        # Discord 음성 재생
│   └── user_settings_service.py
├── providers/
│   ├── base.py                    # TTSProvider 인터페이스
│   ├── edge_tts_provider.py
│   └── cloned_voice_provider.py   # XTTS v2
├── db/
│   └── database.py
└── requirements.txt
```

---

## 설치 및 실행

```bash
pip install -r requirements.txt
winget install ffmpeg
cp .env.example .env
# .env에 DISCORD_BOT_TOKEN, TTS_SERVER_URL 입력
python main.py
```

Kaggle TTS 서버는 `kaggle_tts_server.py`를 Notebook 셀에 순서대로 실행하면 됩니다. 생성된 ngrok URL을 `.env`의 `TTS_SERVER_URL`에 입력하세요.

---

## 슬래시 커맨드

| 커맨드 | 설명 |
|---|---|
| `/join` | 음성 채널 입장 |
| `/leave` | 퇴장 + 큐 초기화 |
| `/say text:...` | TTS 재생 (현재 등록된 tier로) |
| `/stop` | 재생 중단 |
| `/queue` | 대기열 확인 |
| `/setvoice` | **Tier 1** — 6초 음성 등록 (즉시 사용) |
| `/setvoice enhanced` | **Tier 2** — 15문장 다중 샘플 등록 (1~3분) |
| `/setvoice pro` | **Tier 3** — 30분 fine-tune 신청 (2~4시간 학습) |

---

## 기술스택

| | |
|---|---|
| Discord Bot | discord.py |
| TTS 모델 | XTTS v2 (Coqui TTS, zero-shot 복제) |
| TTS 서버 | FastAPI + uvicorn |
| 터널링 | pyngrok (Kaggle → 외부 URL) |
| 비동기 처리 | Python asyncio.Queue |
| DB | SQLite (사용자 설정) |
| GPU | Kaggle T4 |

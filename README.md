# VoiceBridge — Discord AI 음성봇 (내 목소리 TTS)

> **Discord 음성 채널에서 슬래시 커맨드로 입력한 텍스트를, Edge TTS 또는 XTTS v2로 클로닝한 '내 목소리'로 합성·재생하는 Python 음성봇 — 무료 Kaggle GPU로 개인 음성 클로닝 파이프라인까지 구축**

![Python](https://img.shields.io/badge/Python-discord.py_2.4-3776AB) ![TTS](https://img.shields.io/badge/TTS-Edge_TTS%20%7C%20XTTS_v2-orange) ![GPU](https://img.shields.io/badge/Voice_Cloning-Kaggle_T4_%2B_FastAPI_%2B_ngrok-76B900) ![DB](https://img.shields.io/badge/SQLite-WAL-blue)

---

## 🏗 아키텍처 & 기술 스택

```
Discord ── 슬래시 커맨드 12종 (/say /join /voice clone …)
   ▼
discord.py 2.4 봇 (Cog 구조, DI 조립)
   ├── commands/  voice · info · settings (3개 Cog)
   ├── services/  QueueManager(길드별 asyncio 큐) · VoiceRouter · Playback(FFmpeg)
   ├── providers/ TTSProvider 인터페이스
   │      ├── EdgeTTSProvider (ko-KR Neural 3종, 속도 4단계)
   │      └── ClonedVoiceProvider ──HTTP──▶ Kaggle T4: XTTS v2 + FastAPI + ngrok
   ├── db/ SQLite (WAL) ── user_settings · play_log
   └── watchdog.py ── 자동 재시작 + Discord 웹훅 크래시 알림
```

**기술 선택 이유**

- **Provider 추상화**: TTS 엔진을 인터페이스 뒤로 숨겨 Edge TTS ↔ 음성 클로닝을 사용자 설정 한 줄로 전환
- **Kaggle + ngrok**: GPU 비용 0원으로 XTTS v2 음성 클로닝 서버 운영 — 무료 인프라 조합 설계
- **SQLite WAL**: 별도 DB 서버 없이 동시 읽기/쓰기 성능 확보, `ON CONFLICT DO UPDATE` upsert로 설정 영속화
- **asyncio.Queue 길드별 분리**: 서버 간 재생이 서로를 막지 않는 동시성 구조

## ⭐ 핵심 기여 및 성과 (STAR)

### 1. 개인 음성 클로닝 파이프라인 — GPU 비용 ₩0
- **Task**: 내 목소리로 말하는 봇을 만들고 싶지만 GPU 서버 비용이 부담
- **Action**: Kaggle Notebook(T4)에서 **XTTS v2 + FastAPI + ngrok 터널**로 합성 서버 구성, 봇은 `POST /synthesize`(timeout 120s) HTTP 클라이언트로 호출. 음성 샘플 1개(wav)로 화자 클로닝
- **Result**: **월 0원**으로 개인 음성 TTS 운영, `/voice clone` 커맨드로 사용자별 on/off

### 2. 길드별 비동기 재생 큐 + 자동 퇴장
- **Task**: 여러 서버·여러 사용자의 동시 요청이 재생을 충돌시키는 문제
- **Action**: 길드마다 독립 `asyncio.Queue` + worker task, 재생 후 임시 mp3 정리, 큐 소진 **60초 후 자동 퇴장**(idle timeout)
- **Result**: 서버 간 간섭 없는 동시 재생 + 음성 채널 점유 리소스 자동 회수

### 3. 무인 운영을 위한 Watchdog 설계
- **Task**: 봇 크래시 시 수동 재시작 전까지 서비스 중단
- **Action**: 비정상 종료 감지 → **10초 후 자동 재시작**, 30초 내 재크래시를 "빠른 크래시"로 판정해 **5회 연속 시 중단**(무한 루프 방지), Discord 웹훅으로 크래시/재시작 실시간 알림
- **Result**: 무인 상태에서도 자가 복구되는 운영 체계 + 장애 즉시 인지

### 4. 사용자별 설정 영속화
- **Action**: SQLite `user_settings`(PK: user_id+guild_id) upsert로 음성(3종)·속도(4단계)·클로닝 사용 여부 저장, `play_log`로 최근 10건 `/history` 제공
- **Result**: 재시작 후에도 유지되는 **개인화된 TTS 경험**

## 🔧 Troubleshooting

**1. Windows에서 FFmpeg를 못 찾아 재생 실패**
- 원인: winget 설치 시 PATH 미등록 환경 존재
- 해결: `config.py`가 PATH 실패 시 **winget 패키지 경로를 glob으로 직접 탐색**하는 fallback 구현 → 설치 방식과 무관하게 동작

**2. 자동 퇴장 타이머 레이스 컨디션**
- 원인: disconnect 후 잠들어 있던 idle 타이머가 깨어나 이미 끊긴 연결을 다시 조작
- 해결: **"타이머 취소를 disconnect보다 먼저"** 하는 순서 보장 + `cancel_idle`/`start_idle_timer` 분리 설계로 상태 전이를 명시화

## 🚀 Quick Start

```bash
pip install -r requirements.txt
winget install ffmpeg          # Windows
cp .env.example .env           # DISCORD_TOKEN 등 설정
python main.py                 # 또는 python watchdog.py (자동 재시작 모드)
```

| 커맨드 | 기능 |
|---|---|
| `/join` `/leave` | 음성 채널 입·퇴장 |
| `/say <text>` | TTS 재생 (최대 200자) |
| `/queue` `/stop` `/history` | 큐 확인 · 중지 · 최근 기록 |
| `/voice set\|speed\|clone\|show\|reset` | 목소리 · 속도 · 클로닝 설정 |

# VoiceBridge

Discord 음성 채널에서 텍스트를 TTS로 변환해 재생하는 AI 음성봇.

## 폴더 구조

```
Yourvoice_bot/
├── main.py
├── config.py
├── commands/
│   ├── voice_commands.py   # /join /leave /say /stop
│   └── info_commands.py    # /ping /queue
├── services/
│   ├── queue_manager.py    # 길드별 재생 큐
│   ├── voice_router.py     # TTS 프로바이더 라우팅
│   ├── playback_service.py # Discord 음성 재생
│   └── user_settings_service.py
├── providers/
│   ├── base.py             # TTSProvider 인터페이스
│   ├── edge_tts_provider.py
│   └── cloned_voice_provider.py  # stub (향후 구현)
├── models/
│   ├── queue_item.py
│   └── user_settings.py
├── db/
│   └── database.py         # SQLite 초기화
├── temp/                   # TTS 임시 파일 (자동 생성)
├── .env
└── requirements.txt
```

## 설치

```bash
pip install -r requirements.txt
winget install ffmpeg  # FFmpeg 설치 (최초 1회)
```

## 실행

```bash
cp .env.example .env
# .env에 DISCORD_BOT_TOKEN 입력 후:
python main.py
```

## 슬래시 커맨드

| 커맨드 | 설명 |
|---|---|
| `/ping` | 봇 상태 확인 |
| `/join` | 내 음성 채널에 봇 입장 |
| `/leave` | 봇 퇴장 + 큐 초기화 |
| `/say text:...` | TTS 재생 |
| `/queue` | 대기열 확인 |
| `/stop` | 재생 중단 + 대기열 비우기 |

## Voice Cloning 확장

`providers/cloned_voice_provider.py`의 `synthesize` 메서드를 구현하고,
사용자 설정에서 `use_cloned_voice=True`로 설정하면 자동 전환.

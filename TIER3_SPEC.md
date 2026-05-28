# VoiceBridge — Tier 3 Fine-tune 운영 사양

> 본 문서는 **기획 → 설계 → 구현 → 운영** 을 한 번에 매핑한 Tier 3 단일 소스 사양서다.
> Tier 1·2(zero-shot) 와 함께 `TIER_DESIGN.md` 의 3-Tier 전략을 구현 레벨로 풀어낸 것.

---

## 1. 기획 (Why)

### 문제
- XTTS v2 zero-shot 은 6초 참조만으로도 음색을 흉내내지만, 한국어 억양·말투까지는 잡지 못한다.
- 일부 사용자(콘텐츠 제작자·본인 시연용)는 더 높은 충실도를 원한다.
- 그러나 **모든 사용자에게 30분 녹음을 강제하면 80%는 이탈한다.** (Tier 설계의 핵심 가설)

### 결정
Tier 3 는 **Opt-in · 비동기 · 큐 기반** 으로만 제공한다.
- 즉시 합성 결과를 약속하지 않는다 → 학습 큐에 등록하고 백그라운드 처리.
- 학습 비용을 사용자에게 명시한다 ("2~4시간 소요").
- 학습 결과가 준비되면 Tier 3 합성으로 자동 승격, 그 전까지는 Tier 1 로 fallback.

### Non-goals
- 멀티 사용자 동시 학습 (현 단계는 single-GPU Colab Free 가정).
- 자동 트리거 학습 (사람이 Colab 노트북을 실행).
- 학습 중간 retry / resume 자동화 (수동 SOP 로 처리).

---

## 2. 설계 (Architecture)

### 2.1 전체 흐름

```
┌──────────────┐  ① 100~400 WAV 업로드      ┌───────────────────┐
│  웹 UI / 봇   │ ────────────────────────▶ │  HTTP Bridge       │
│  (브라우저)   │                            │  /api/register     │
└──────────────┘                            │   tier=3           │
                                            └─────────┬─────────┘
                                                      │
                                ② ffmpeg 24kHz mono   │
                                   변환 + 검증         │
                                                      ▼
                                            ┌───────────────────┐
                                            │ voice_data/       │
                                            │  user_<id>/tier3/ │
                                            │   001.wav ...     │
                                            └─────────┬─────────┘
                                                      │ ③ Tier3Repository.submit
                                                      ▼
                                            ┌───────────────────┐
                                            │  SQLite           │
                                            │  tier3_jobs       │
                                            │   status=queued   │
                                            └─────────┬─────────┘
                                                      │
                          ④ tier3_worker --list / Colab 노트북 실행 (사람)
                                                      │
                                                      ▼
                                            ┌───────────────────┐
                                            │  Colab T4 GPU      │
                                            │  train_personal_   │
                                            │  colab.ipynb       │
                                            │   2~4 시간          │
                                            └─────────┬─────────┘
                                                      │ ⑤ best_model.pth
                                                      ▼
                                            ┌───────────────────┐
                                            │  Drive / CKPT_ROOT │
                                            └─────────┬─────────┘
                                                      │
                          ⑥ tier3_worker --mark-ready --ckpt <path>
                                                      ▼
                                            ┌───────────────────┐
                                            │ user_settings     │
                                            │  tier=3           │
                                            │  ckpt_path=...    │
                                            │  tier3_status=    │
                                            │   "ready"         │
                                            └─────────┬─────────┘
                                                      │
                          ⑦ /say → VoiceRouter → ClonedVoiceProvider
                                                      ▼
                                            ┌───────────────────┐
                                            │ kaggle_tts_server  │
                                            │   /synthesize      │
                                            │   tier=3, ckpt=... │
                                            └───────────────────┘
```

### 2.2 컴포넌트 매핑

| 컴포넌트 | 파일 | 역할 |
|---|---|---|
| HTTP 신청 엔드포인트 | `services/http_bridge.py::_register` | 멀티 WAV 수신·변환·큐 등록 |
| HTTP 폴링 엔드포인트 | `services/http_bridge.py::_tier3_jobs` | 최신 학습 상태 조회 |
| 학습 작업 저장소 | `services/tier3_repo.py` | tier3_jobs CRUD |
| 운영자 CLI | `tier3_worker.py` | queued 목록 / 상태 천이 / ckpt 등록 |
| 학습 노트북 | `tuning/2_train/train_personal_colab.ipynb` | XTTS v2 fine-tune (Colab Free) |
| 추론 서버 | `kaggle_tts_server.py` | 어댑터 동적 로드 + 합성 |
| 합성 라우터 | `services/voice_router.py` | tier3_status≠ready 시 Tier 1 fallback |
| TTS Provider | `providers/cloned_voice_provider.py` | tier=3 payload 송신 |
| 사용자 상태 | `models/user_settings.py` + `services/user_settings_service.py` | tier · ckpt_path · tier3_status |

### 2.3 데이터 모델

```sql
-- 학습 작업 큐
CREATE TABLE tier3_jobs (
    job_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    guild_id     INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',   -- queued · training · ready · failed
    wav_count    INTEGER NOT NULL DEFAULT 0,
    wav_dir      TEXT,
    ckpt_path    TEXT,
    error        TEXT,
    submitted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
    started_at   TEXT,
    completed_at TEXT
);
CREATE INDEX idx_tier3_user ON tier3_jobs (user_id, guild_id, status);

-- 사용자 설정 확장
ALTER TABLE user_settings ADD COLUMN tier         INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_settings ADD COLUMN refs_json    TEXT NOT NULL DEFAULT '[]';
ALTER TABLE user_settings ADD COLUMN ckpt_path    TEXT;
ALTER TABLE user_settings ADD COLUMN tier3_status TEXT;  -- queued · training · ready · failed
ALTER TABLE user_settings ADD COLUMN updated_at   TEXT;
```

### 2.4 상태 머신

```
        ┌────────┐  worker --mark-training  ┌──────────┐
  ──▶   │ queued │ ───────────────────────▶ │ training │
        └────┬───┘                          └─────┬────┘
             │                                    │
             │ worker --mark-failed               │ worker --mark-ready --ckpt
             ▼                                    ▼
        ┌────────┐                          ┌────────┐
        │ failed │                          │ ready  │
        └────────┘                          └────────┘
                                                  │
                                                  │ user_settings.tier=3, ckpt_path 설정
                                                  ▼
                                            합성 시 ClonedVoiceProvider 가
                                            tier=3, ckpt=<basename> 송신
```

전이 규칙:
- `queued → training`: 운영자가 학습을 시작했음을 표시.
- `training → ready`: best_model.pth 경로와 함께. `user_settings.ckpt_path` 동기화.
- `*  → failed`: 에러 메시지 저장. 사용자는 다시 신청 가능.

---

## 3. API 계약

### 3.1 POST `/api/register` (tier=3)

```
Content-Type: multipart/form-data
fields:
  tier      = "3"
  user_id   = "<discord snowflake>"
  guild_id  = "<discord snowflake>"
  wavs      = file[] (100~400개)

success 200:
{
  "ok": true,
  "tier": 3,
  "stored": 217,
  "user_id":  "469878308318740491",
  "guild_id": "469885581145669652",
  "job_id":   42
}

error 400:
{ "error": "tier 3 requires 100~400 wavs (got 50)" }
```

### 3.2 GET `/api/tier3/jobs?user_id=&guild_id=`

```
success 200 (found):
{
  "found": true,
  "job_id": 42,
  "status": "training",
  "wav_count": 217,
  "wav_dir": "C:/.../voice_data/user_<id>/tier3",
  "ckpt_path": null,
  "error": null,
  "submitted_at": "2026-05-28 12:34:56",
  "started_at":   "2026-05-28 12:40:01",
  "completed_at": null
}

success 200 (not found):
{ "found": false }
```

### 3.3 운영자 CLI

```powershell
python tier3_worker.py --list
# #42  user=469878308318740491  guild=...  wavs=217  dir=...  submitted=...

python tier3_worker.py --mark-training 42
python tier3_worker.py --mark-ready    42 --ckpt /content/drive/.../best_model.pth
python tier3_worker.py --mark-failed   42 --error "OOM at step 12000"
```

### 3.4 추론 서버 페이로드 (Tier 3)

```json
POST /synthesize
{
  "text": "안녕하세요",
  "language": "ko",
  "tier": 3,
  "refs": ["001.wav"],
  "ckpt": "best_model.pth"
}
```

---

## 4. 구현 현황

| 항목 | 상태 | 비고 |
|---|---|---|
| DB 스키마 (`tier3_jobs`, `user_settings` 확장) | ✅ 구현 | `db/database.py` 마이그레이션 |
| Tier3Repository (submit / update / latest / queued) | ✅ 구현 | `services/tier3_repo.py` |
| HTTP 신청 (`/api/register` tier=3) | ✅ 구현 | 검증·ffmpeg 변환·큐 등록 |
| HTTP 폴링 (`/api/tier3/jobs`) | ✅ 구현 | 본 PR 추가 |
| 운영자 CLI (`tier3_worker.py`) | ✅ 구현 | `--list`/`--mark-*` |
| Discord 슬래시 명령 (`/register voice tier:3`) | ✅ 구현 | `commands/tier_commands.py` |
| 웹 UI 신청 카드 | ✅ 구현 | 본 PR 추가 — 다중 업로드 + 10초 폴링 |
| 학습 노트북 (Colab Free 최적화) | ✅ 작성 | `tuning/2_train/train_personal_colab.ipynb` |
| 추론 서버 어댑터 동적 로드 | ✅ 구현 | `kaggle_tts_server.py::_load_tuned` |
| Provider tier-aware payload | ✅ 구현 | `providers/cloned_voice_provider.py` |
| Router fallback (ready 전엔 Tier 1) | ✅ 구현 | `services/voice_router.py` |
| **실제 학습 실행** | ❌ 미수행 | 사용자가 Colab GPU 2~4시간 직접 돌려야 함 |
| 자동 학습 트리거 | ❌ 의도적 제외 | Non-goal (현 단계) |
| Drive ↔ Colab 자동 동기화 | ❌ 의도적 제외 | 데모 단계에선 수동 |

---

## 5. 운영 SOP

### 5.1 학습 1회 사이클

1. 사용자가 웹 UI ④ 카드에서 WAV 100~400개 선택 → "학습 신청".
2. 응답 `job_id` 확인. UI 가 10초 간격으로 자동 폴링.
3. 운영자(=본인)가 로컬에서 큐 확인:
   ```powershell
   python tier3_worker.py --list
   ```
4. WAV 디렉토리(`voice_data/user_<id>/tier3/`)를 Drive `xtts_personal/<job_id>/wavs` 로 업로드 + manifest 생성:
   ```powershell
   python tuning/1_data/prepare_personal.py `
       --wav-dir voice_data/user_<id>/tier3 `
       --script tuning/1_data/recording_script.md `
       --out tuning/manifest --normalize
   ```
5. Colab `train_personal_colab.ipynb` 실행:
   - 셀 0~1: 환경 + anti-idle
   - 셀 2~3: 데이터 마운트
   - 셀 4~8: trainer 구성 + fit
   - 셀 9: best_model.pth 경로 출력
6. 학습 시작 직후:
   ```powershell
   python tier3_worker.py --mark-training <job_id>
   ```
7. 완료 후:
   ```powershell
   python tier3_worker.py --mark-ready <job_id> --ckpt /content/drive/.../best_model.pth
   ```
8. UI 폴링이 자동으로 "🟢 완료" 상태로 갱신.
9. 추론 서버(`kaggle_tts_server.py`)에 `CKPT_ROOT` 가 해당 경로의 부모를 가리키는지 확인.

### 5.2 실패 처리

- OOM / 데이터 부족 / config 오류 등 발생 시:
  ```powershell
  python tier3_worker.py --mark-failed <job_id> --error "OOM at step 12000"
  ```
- `user_settings.tier3_status = "failed"` 로 갱신됨.
- 사용자는 데이터 보강 후 재신청.

### 5.3 다중 사용자 대응 (현 한계)

- 현 구현은 **순차 처리** 만 가정. 동시 신청이 들어와도 큐만 쌓일 뿐 자동 픽업은 없음.
- 확장 시 옵션:
  1. Worker 데몬화 (`tier3_worker.py` 를 폴링 루프로 전환) + Colab 자동 트리거.
  2. RunPod/Vast.ai 같은 외부 GPU 큐로 위임.
  3. AWS SageMaker / GCP Vertex AI 같은 매니지드 학습.

---

## 6. 한계 / 다음 단계

| 한계 | 대응 안 |
|---|---|
| Colab Free 12시간 세션 제한 | anti-idle 셀 + checkpoint resume 로 회피 |
| 사용자 음성 데이터 PII | Law-Lens 의 PII 마스킹 + AES-256 컬럼 암호화 패턴 차용 가능 |
| Drive ↔ 추론 서버 파일 동기화 수동 | 1차: rclone 스크립트, 2차: S3 게이트웨이 |
| 어댑터 캐시 메모리 누적 | LRU 캐시로 교체 (`_tuned_cache` → `functools.lru_cache` or 명시 LRU) |
| 다중 사용자 동시 학습 | 별도 GPU 워커 풀 + 메시지 큐 (Redis/RabbitMQ) |
| 학습 품질 자동 검증 | `tuning/3_eval/run_eval.py` 를 학습 끝에 자동 실행, CER 임계 미달 시 failed 처리 |

---

## 7. 면접 어필 포인트

> "음성 복제 품질과 사용자 부담 사이의 트레이드오프를 단일 모델로 풀 수 없다고 판단해
> 6초·1~3분·30분+ 3-Tier 로 분리했습니다. Tier 3 는 비용 큰 fine-tune 이므로
> 동기 응답을 약속하지 않고 SQLite 기반 작업 큐 + 운영자 CLI 로 비동기 처리합니다.
> 학습 완료 전엔 라우터가 Tier 1 로 자동 fallback 해, 신청 직후에도 서비스가 끊기지 않습니다.
> 단일 XTTS v2 추론 서버 위에서 어댑터 동적 로딩으로 3 tier 를 모두 서비스합니다."

핵심 키워드:
- **트레이드오프 의식 적 설계** — 모든 사용자에게 같은 비용을 강요하지 않음.
- **비동기 큐 + 상태 머신** — queued/training/ready/failed.
- **Graceful fallback** — 학습 진행 중에도 Tier 1 으로 합성.
- **운영성** — CLI · 폴링 API · 상태 가시화.
- **확장 경로 명시** — 다중 사용자 / 외부 GPU 큐 / 자동 검증.

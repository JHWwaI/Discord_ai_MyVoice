# VoiceBridge — Multi-Tier Voice Registration Design

> 사용자의 음성을 학습해 Discord에서 본인 목소리로 발화하는 봇.
> **30분 강제 녹음은 일반 사용자가 포기하는 트리거** → 다단계 등록 구조로 해결.

---

## 핵심 가설

| | 가설 |
|---|---|
| **A** | 사용자의 80%는 1분 이내 등록만 견딘다. |
| **B** | 5~10%만 더 좋은 결과를 위해 추가 시간을 투자한다. |
| **C** | 1% 미만이 30분+ 본격 학습을 한다 (Pro·데모 목적). |

→ 한 가지 등록 방식만 강제하면 80%를 잃거나, 1%의 품질을 포기해야 함. **Tier 설계로 양쪽 다 잡는다.**

---

## 3-Tier 등록 구조

```
┌──────────────────────────────────────────────────────────────┐
│  Tier 1 — Instant       (모두 · 기본)                          │
│  6초 zero-shot · /setvoice                                    │
│  품질 ★★★☆☆  ·  Friction 거의 0                              │
├──────────────────────────────────────────────────────────────┤
│  Tier 2 — Enhanced      (선택 · 무료)                          │
│  1~3분 다중 샘플 zero-shot · /setvoice enhanced               │
│  품질 ★★★★☆  ·  Friction 낮음                                │
├──────────────────────────────────────────────────────────────┤
│  Tier 3 — Pro           (소수 · 본인·데모)                     │
│  30분 fine-tune · 등록 신청 후 백엔드 학습 · /setvoice pro     │
│  품질 ★★★★★  ·  Friction 큼                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Tier 1 — Instant (기본 등록)

### 사용자 흐름
```
/setvoice
  → 봇이 "6초간 평소 목소리로 다음 문장을 읽어주세요" 안내
  → 사용자가 음성 파일 첨부 또는 봇의 음성 채널에서 직접 녹음
  → 즉시 사용 가능
```

### 백엔드
- XTTS v2 zero-shot, pretrained 그대로
- 등록 데이터: 사용자별 6초 reference WAV 1개 (SQLite + Drive 저장)
- 합성 시 `speaker_wav=ref.wav` 전달

### 한계
- 영어 발음 잘됨 / 한국어 살짝 어색
- 사용자 말투·억양 반영 약함
- 짧은 문장은 자연스럽지만 긴 문장은 톤 흔들림

### 측정 지표
- 등록까지 평균 시간 (목표: <60초)
- 합성 평균 시간 (목표: <3초)
- 사용자 청취 만족도 (자체 설문)

---

## Tier 2 — Enhanced (선택 등록)

### 사용자 흐름
```
/setvoice enhanced
  → 봇이 15개 짧은 문장을 차례로 표시 (한 문장당 5~10초)
  → 사용자가 한 문장씩 녹음 (총 1~3분)
  → 봇이 모든 샘플의 임베딩을 평균 또는 다중 참조 합성
```

### 백엔드
- XTTS v2 zero-shot, 단 `gpt_cond_len` 증가 + 다중 참조
- 등록 데이터: 사용자별 WAV N개 (5~15개)
- 합성 시 여러 참조 음성을 평균한 conditioning latent 사용

### 개선 효과 (가설)
- 음운 다양성 ↑ → 한국어 발음 어색함 감소
- 톤 안정성 ↑ → 긴 문장에서도 흔들림 적음
- CER 약 15~20% 감소 (Tier 1 대비)

### 트리거 메시지
사용자가 Tier 1에서 합성 결과에 만족 못 할 때 봇이 자동 안내:
```
"발음이 어색하신가요? /setvoice enhanced 로 1~3분 더 등록하시면 품질이 향상됩니다."
```

---

## Tier 3 — Pro (Fine-tune)

### 사용자 흐름
```
/setvoice pro
  → 봇: "약 30분간 300문장을 녹음해주세요. 학습은 백그라운드로 진행됩니다."
  → 사용자가 recording_script.md 기반 300문장 녹음
  → 봇이 받아서 검증 + 큐에 등록
  → 백엔드 GPU 서버에서 fine-tune (2~4시간)
  → 학습 완료 시 봇이 사용자에게 DM으로 알림
  → 이후 합성은 사용자 전용 fine-tuned 모델 사용
```

### 백엔드
- `tuning/2_train/train_personal_colab.ipynb` 기반 fine-tune
- 사용자별 별도 어댑터 또는 별도 체크포인트
- 합성 시 어댑터 동적 로드

### 한계 명시
- 운영 비용 큼 (사용자당 GPU 2~4시간)
- 신청 큐잉 필요
- 본인이 직접 데이터 수집해야 함

### 사용 시나리오
- 본인 전용 봇 운영자
- 데모·시연용 (포트폴리오·발표)
- 음성 콘텐츠 제작자

---

## 비교 표

| | Tier 1 Instant | Tier 2 Enhanced | Tier 3 Pro |
|---|---|---|---|
| 등록 시간 | 6초 | 1~3분 | 30~45분 |
| 학습 필요? | ❌ | ❌ | ✅ (2~4시간) |
| 합성 지연 | 2~3초 | 2~3초 | 2~3초 |
| 한국어 품질 | 70% | 80% | 95%+ |
| 사용자 말투 반영 | ❌ | 약간 | 완전 |
| 운영 비용 | 거의 0 | 거의 0 | GPU 시간 |
| 사용자 비중 (가설) | 80% | 15% | 5% |

---

## Provider 인터페이스 (코드 측면)

기존 `providers/base.py` 인터페이스에 tier 개념 추가:

```python
class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, user_id: int, tier: int) -> bytes:
        """tier 1/2/3에 따라 다른 경로로 합성"""

class XttsZeroShotProvider(TTSProvider):
    """Tier 1·2 — 단일/다중 참조 zero-shot"""

class XttsFineTunedProvider(TTSProvider):
    """Tier 3 — 사용자별 fine-tuned 모델 로드"""
```

사용자 등록 정보(SQLite):
```sql
CREATE TABLE user_voice (
    user_id   INTEGER PRIMARY KEY,
    tier      INTEGER DEFAULT 1,
    refs      JSON,          -- Tier 1·2: WAV 경로 목록
    ckpt_path TEXT,          -- Tier 3: fine-tuned 체크포인트 경로
    status    TEXT,          -- pending · ready · failed
    updated_at TIMESTAMP
);
```

---

## 측정·검증 계획

각 tier마다 동일한 평가셋 30문장(`tuning/3_eval/eval_set.jsonl`)으로 측정:

| Tier | Whisper CER | 청취 MOS | 등록 시간 |
|---|---|---|---|
| 1 (목표) | <15% | 3.5/5 | <60초 |
| 2 (목표) | <10% | 4.0/5 | <3분 |
| 3 (목표) | <5%  | 4.5/5 | 30분 + 2~4h |

CER 측정은 `run_eval.py`로, MOS는 자체 설문(소수 인원).

---

## 면접 어필 메시지

> "음성 복제는 품질과 사용자 부담 사이 트레이드오프가 명확합니다.
> 단일 방식 강제는 80%의 사용자를 잃거나 1%의 품질을 포기해야 합니다.
> VoiceBridge는 6초·3분·30분 3단계로 분리해 사용자 선택권을 줍니다.
> 동일한 XTTS v2 모델 위에 zero-shot 다중 참조 → fine-tune 어댑터 로딩으로
> 단일 추론 서버에서 3개 tier를 모두 서비스합니다."

---

## 한계 / 다음 단계

- Tier 3은 GPU 서버 큐잉 시스템 추가 필요 (현재 봇은 단일 사용자 가정)
- 다중 사용자가 동시에 Tier 3 신청 시 학습 큐 관리 필요
- Tier 2의 다중 참조 합성 품질이 실제로 Tier 1보다 좋은지 ablation 필요
- 사용자 음성 데이터 PII 처리 (저장 기간·암호화) 필요 → Law-Lens의 PII 마스킹 + AES-256 패턴 차용 가능

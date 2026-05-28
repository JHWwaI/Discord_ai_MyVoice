<div align="center">

# XTTS v2 Fine-Tuning — Tier 3 (Pro)

[![XTTS v2](https://img.shields.io/badge/XTTS_v2-fine--tune-00B4D8?style=flat-square)](.)
[![Tier 3](https://img.shields.io/badge/Tier-3_Pro-9B59B6?style=flat-square)](.)
[![Whisper](https://img.shields.io/badge/Eval-Whisper_CER-FF6B00?style=flat-square)](.)

</div>

---

VoiceBridge 봇의 **Tier 3 (Pro)** 음성 등록 경로. 사용자 음성 30~45분을 학습해 **개별 high-fidelity 모델**을 생성한다.

> ⚠️ 일반 사용자는 **Tier 1 (6초)** 또는 **Tier 2 (1~3분 다중 참조)** 로 충분하다.
> 본 폴더의 fine-tune은 **소수 사용자(본인·데모 목적)** 용. 전체 등급 구조는 [`../TIER_DESIGN.md`](../TIER_DESIGN.md) 참조.

---

## 가설

> XTTS v2는 영문 중심으로 학습되어 한국어 발음 품질이 떨어진다.
> 한국어 단일 화자 데이터로 GPT 백본을 fine-tune하면 CER이 유의하게 감소할 것이다.

---

## 측정 방법

- **데이터셋**: KSS 12,853문장 (12시간) — train/val = 95/5 split
- **평가셋**: 학습에 사용하지 않은 30문장 (`3_eval/eval_set.jsonl`)
  - daily / tech / name / number / long / short / foreign / emotion / command 카테고리
- **지표**: Whisper large-v3 STT로 합성 음성 인식 → 원문과 CER 측정
  - **CER mean**: 평균 글자 오류율 (낮을수록 좋음)
  - **CER p95**: 상위 5% 어려운 케이스의 CER
  - **Latency**: 합성 시간

---

## 폴더 구조

```
tuning/
├── 1_data/
│   ├── recording_script.md       녹음용 300문장 스크립트 (8개 카테고리)
│   ├── prepare_personal.py       본인 녹음 → metadata 생성 (스크립트 매칭 / Whisper STT)
│   ├── download_kss.py           [참고용] KSS 다운로드 — 다화자 방식
│   └── prepare_manifest.py       [참고용] KSS manifest 생성
├── 2_train/
│   ├── train_personal_colab.ipynb  ⭐ 본인 음성 fine-tune (현재 방식)
│   └── train_xtts_colab.ipynb      [참고용] KSS 다화자 fine-tune
└── 3_eval/
    ├── eval_set.jsonl              30 케이스 (10 카테고리)
    ├── run_eval.py                 합성 → Whisper STT → CER 측정
    ├── compare.py                  Base vs Fine-tuned 비교 리포트
    └── requirements.txt
```

---

## 진행 순서

### A. 본인 음성 녹음 (30~45분)

```bash
# 1) recording_script.md 열고 300문장을 차례로 녹음
#    파일명: 001.wav, 002.wav, ..., 300.wav
#    포맷: 24kHz · 16-bit · mono WAV
#    → my_voice/ 폴더에 저장

# 2) Manifest 생성 (스크립트 매칭 방식, ffmpeg 정규화 포함)
python 1_data/prepare_personal.py \
    --wav-dir ./my_voice \
    --script ./1_data/recording_script.md \
    --out ./manifest \
    --normalize

# 또는 Whisper STT 방식 (스크립트 없이 자유 녹음)
python 1_data/prepare_personal.py \
    --wav-dir ./my_voice \
    --whisper \
    --out ./manifest
```

### B. Drive 업로드

`my_voice/`(또는 `my_voice_24k/`)와 `manifest/`를 Google Drive `xtts_personal/`에 업로드.

### C. Colab 학습

```
2_train/train_personal_colab.ipynb 열기 → 셀 0~9 순차 실행
→ /content/drive/MyDrive/xtts_personal/runs/.../best_model.pth
```

### D. 평가

```bash
# Base (zero-shot, 본인 음성 6초 참조)
python 3_eval/run_eval.py --speaker ref.wav --model base --out base.json

# Fine-tuned
python 3_eval/run_eval.py --speaker ref.wav --model finetuned --ckpt best.pth --out tuned.json

# 비교
python 3_eval/compare.py --base base.json --tuned tuned.json --out comparison.md
```

---

## 학습 설정

- **모델**: `coqui/XTTS-v2` (GPT 백본 + DVAE)
- **학습 대상**: GPT 백본 부분 (DVAE는 동결)
- **Optimizer**: AdamW, lr=5e-6, weight_decay=1e-2
- **Scheduler**: MultiStepLR (milestones=[2, 4], gamma=0.5)
- **Batch size**: 2 (Colab Free T4), grad accumulation 4 → effective batch 8
- **Mixed precision**: fp16 (T4 VRAM 절약)
- **Epochs**: 3 (Free 시간 한계 고려)
- **데이터**: 5,000건 subset (전체 12K 중)
- **추적**: Coqui Trainer 기본 로그 + Colab Drive 저장

`lr=5e-6`은 의도적으로 낮춤 — 베이스 모델의 다국어 성능을 망가뜨리지 않기 위함 (catastrophic forgetting 방지).

---

## 예상 결과 (가설)

| | Base | Fine-tuned (목표) |
|---|---|---|
| CER mean | ~12~18% (한국어 약함) | **5~8%** |
| CER p95  | ~30% | < 15% |
| Latency mean | ~2.5s | ~2.5s (동일) |

수치는 가설이며 실제 결과로 갱신.

---

## 라이선스

- **모델**: Coqui Public Model License (비상업 한정)
- **데이터**: KSS — CC BY-NC-SA 4.0 (비상업 한정)
- 본 fine-tuned 모델은 **포트폴리오·PoC 한정 비상업 사용**

---

## 한계 / 다음 단계

- 단일 화자 데이터 — 다양한 화자 일반화 한계 → AI Hub 한국어 다화자 데이터셋 추가
- 5 epoch fine-tune — overfit 위험. validation loss로 early stopping 보강 필요
- MOS(주관 평가) 미반영 — 청취 평가 추후 수행
- 감정·말투 fine-tune은 별도 단계 (KSS는 단조로운 톤)

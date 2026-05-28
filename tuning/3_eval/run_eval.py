"""
XTTS 합성 음성의 한국어 발음 품질 평가.

평가 흐름:
  1. eval_set.jsonl의 각 텍스트를 XTTS로 합성 → WAV
  2. Whisper (large-v3)로 STT → 인식 텍스트
  3. 원본 vs 인식 텍스트의 CER (Character Error Rate) 측정
  4. Base 모델 vs Fine-tuned 모델 비교 (각각 따로 실행 후 합산)

CER이 낮을수록 발음 명료. 0% = 완벽.

사용:
    # Base 모델 평가
    python run_eval.py --speaker ref.wav --model base --out base_report.json
    # Fine-tuned 모델 평가 (학습 후 다른 노트북에서)
    python run_eval.py --speaker ref.wav --model finetuned --ckpt /path/to/best.pth --out tuned_report.json
"""
import argparse
import json
import statistics
import time
from pathlib import Path


def cer(reference: str, hypothesis: str) -> float:
    """Character-level edit distance / len(reference)."""
    def edit(a, b):
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1): dp[i][0] = i
        for j in range(n + 1): dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        return dp[m][n]
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return edit(reference, hypothesis) / len(reference)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker",  required=True, help="참조 화자 WAV (6초 이상)")
    ap.add_argument("--model",    default="base", choices=["base", "finetuned"])
    ap.add_argument("--ckpt",     help="finetuned 시 체크포인트 경로")
    ap.add_argument("--cases",    default=str(Path(__file__).parent / "eval_set.jsonl"))
    ap.add_argument("--out",      default="report.json")
    ap.add_argument("--tmp-dir",  default="./tmp_wav")
    args = ap.parse_args()

    # ──── Lazy import — heavy deps ────
    from TTS.api import TTS
    import whisper

    tmp_dir = Path(args.tmp_dir)
    tmp_dir.mkdir(exist_ok=True)

    print(f"Loading TTS ({args.model}) ...")
    if args.model == "base":
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
    else:
        # Finetuned checkpoint 로드 — XTTS API 직접 사용
        from TTS.tts.models.xtts import Xtts
        from TTS.tts.configs.xtts_config import XttsConfig
        cfg_path = str(Path(args.ckpt).parent / "config.json")
        config = XttsConfig(); config.load_json(cfg_path)
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_path=args.ckpt)
        model.cuda().eval()
        tts = ("custom", model, config)

    print("Loading Whisper large-v3 ...")
    asr = whisper.load_model("large-v3")

    cases = [json.loads(l) for l in Path(args.cases).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"eval cases: {len(cases)}")

    results = []
    cers, latencies = [], []
    for c in cases:
        wav_path = tmp_dir / f"{c['id']}_{args.model}.wav"
        started = time.time()
        if isinstance(tts, TTS):
            tts.tts_to_file(text=c["text"], file_path=str(wav_path),
                            speaker_wav=args.speaker, language="ko")
        else:
            _, model, config = tts
            out = model.synthesize(c["text"], config, speaker_wav=args.speaker, language="ko",
                                   gpt_cond_len=3, temperature=0.7)
            import soundfile as sf
            sf.write(str(wav_path), out["wav"], samplerate=24000)
        synth_ms = int((time.time() - started) * 1000)

        # STT
        asr_result = asr.transcribe(str(wav_path), language="ko", fp16=True)
        hyp = asr_result["text"].strip()
        c_err = cer(c["text"], hyp)
        cers.append(c_err)
        latencies.append(synth_ms)

        results.append({
            "id": c["id"], "ref": c["text"], "hyp": hyp,
            "cer": round(c_err, 4), "latency_ms": synth_ms,
        })
        print(f"  {c['id']}  cer={c_err:.3f}  lat={synth_ms}ms")

    summary = {
        "model": args.model,
        "n": len(cases),
        "cer_mean": round(statistics.mean(cers), 4),
        "cer_p95":  round(sorted(cers)[int(len(cers) * 0.95) - 1], 4),
        "latency_mean_ms": int(statistics.mean(latencies)),
        "latency_p95_ms":  sorted(latencies)[int(len(latencies) * 0.95) - 1],
        "results": results,
    }

    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("="*60)
    print(f"Model: {args.model}")
    print(f"CER  mean={summary['cer_mean']:.3%}  p95={summary['cer_p95']:.3%}")
    print(f"Lat  mean={summary['latency_mean_ms']}ms  p95={summary['latency_p95_ms']}ms")
    print(f"Report saved → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

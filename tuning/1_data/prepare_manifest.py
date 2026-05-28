"""
KSS transcript → XTTS 학습용 metadata.csv 변환.

XTTS는 LJSpeech 형식을 받는다:
    wav_filename|text|speaker_id

KSS transcript.v.1.4.txt 포맷:
    1/1_0000.wav|그는 괜찮은 척하려고 애쓰는 것 같았다.|...|...

본 스크립트는 다음을 수행:
1. transcript 파싱 → (wav, text) 쌍 추출
2. 텍스트 정규화 (앞뒤 공백, 특수문자 정리)
3. 길이 분포 분석 (너무 짧/긴 샘플 제외)
4. train/val split (95/5)
5. metadata_train.csv · metadata_val.csv 작성
"""
import argparse
import re
import random
import statistics
from pathlib import Path

random.seed(20260527)


def normalize_text(text: str) -> str:
    text = text.strip()
    # 중복 공백 정리
    text = re.sub(r"\s+", " ", text)
    # 따옴표·특수 문장 부호 정리
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kss-dir", required=True, help="KSS root (transcript + 1/ 2/ ... 폴더 포함)")
    ap.add_argument("--out", default="./manifest", help="metadata 출력 위치")
    ap.add_argument("--min-chars", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=180)
    ap.add_argument("--val-ratio", type=float, default=0.05)
    ap.add_argument("--limit", type=int, default=0,
                    help="총 사용 샘플 수 제한 (0이면 전부). Colab Free 빠른 학습 시 5000 권장")
    args = ap.parse_args()

    kss = Path(args.kss_dir)
    transcript_path = next(kss.rglob("transcript.v.*.txt"), None)
    if transcript_path is None:
        print("ERROR: transcript.v.*.txt not found")
        return 1

    samples = []
    with transcript_path.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) < 2:
                continue
            wav_rel, text = parts[0], parts[1]
            text = normalize_text(text)
            wav_full = kss / wav_rel
            if not wav_full.exists():
                # KSS sometimes has files in flat structure
                wav_full = next(kss.rglob(Path(wav_rel).name), None)
                if wav_full is None or not wav_full.exists():
                    continue
            if not (args.min_chars <= len(text) <= args.max_chars):
                continue
            samples.append({
                "wav": str(wav_full.relative_to(kss)),
                "text": text,
            })

    print(f"valid samples: {len(samples)}")
    lengths = [len(s["text"]) for s in samples]
    print(f"text length p50={statistics.median(lengths)}  p95={sorted(lengths)[int(len(lengths)*0.95)]}")

    random.shuffle(samples)
    if args.limit and args.limit < len(samples):
        samples = samples[:args.limit]
        print(f"limited to {args.limit:,} samples")
    n_val = int(len(samples) * args.val_ratio)
    val, train = samples[:n_val], samples[n_val:]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_metadata(path: Path, rows: list[dict]) -> None:
        # LJSpeech format: wav|text|speaker
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"{r['wav']}|{r['text']}|kss\n")

    write_metadata(out_dir / "metadata_train.csv", train)
    write_metadata(out_dir / "metadata_val.csv", val)

    print(f"train: {len(train):,}  →  {out_dir/'metadata_train.csv'}")
    print(f"val  : {len(val):,}  →  {out_dir/'metadata_val.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
KSS (Korean Single Speaker) 데이터셋 다운로드 + 검증.

데이터셋: https://www.kaggle.com/datasets/bryanpark/korean-single-speaker-speech-dataset
  - 단일 화자 한국어 음성 12,853개 (~12시간)
  - 16kHz · 16-bit · mono WAV
  - 텍스트 transcript.v.1.4.txt (탭 구분)

KSS는 Kaggle 가입 후 다운로드. 본 스크립트는 압축 해제·검증을 자동화한다.

사용:
    # 1) Kaggle CLI 설정 후
    kaggle datasets download bryanpark/korean-single-speaker-speech-dataset
    # 2) 본 스크립트 실행
    python download_kss.py --zip korean-single-speaker-speech-dataset.zip --out ./kss
"""
import argparse
import os
import zipfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True, help="KSS zip 파일 경로")
    ap.add_argument("--out", default="./kss", help="압축 해제 위치")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {args.zip} → {out}")
    with zipfile.ZipFile(args.zip, "r") as z:
        z.extractall(out)

    transcript = out / "transcript.v.1.4.txt"
    if not transcript.exists():
        # nested 구조 보정
        for f in out.rglob("transcript.v.*.txt"):
            transcript = f
            break

    if not transcript.exists():
        print("ERROR: transcript.v.1.4.txt not found")
        return 1

    n_lines = sum(1 for _ in transcript.open("r", encoding="utf-8"))
    n_wavs = len(list((transcript.parent).rglob("*.wav")))

    print(f"transcript lines : {n_lines}")
    print(f"wav files        : {n_wavs}")
    if n_wavs < 10000:
        print("WARN: wav count looks low. Check extraction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

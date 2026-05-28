"""
본인 녹음(WAV들)과 스크립트(recording_script.md) → XTTS 학습용 metadata 생성.

사용 방법 (스크립트 기반 — 권장):
    # WAV 파일명은 001.wav, 002.wav, ... 처럼 순서대로
    python prepare_personal.py \\
        --wav-dir ./my_voice \\
        --script ./recording_script.md \\
        --out ./manifest

이 경우 script의 1~300번 문장을 WAV 001~300과 1:1 매칭한다.

대안 (Whisper STT — 스크립트 없이 자유 녹음):
    python prepare_personal.py \\
        --wav-dir ./my_voice \\
        --whisper \\
        --out ./manifest

Whisper large-v3로 자동 받아쓰기 후 매칭.
"""
import argparse
import re
import random
import statistics
import subprocess
from pathlib import Path

random.seed(20260527)


def parse_script(script_path: Path) -> list[str]:
    """recording_script.md에서 번호 + 문장 추출."""
    lines = script_path.read_text(encoding="utf-8").splitlines()
    sentences = []
    pattern = re.compile(r"^\d+\.\s+(.+)$")
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            sentences.append(m.group(1).strip())
    return sentences


def normalize_wav(in_path: Path, out_path: Path) -> bool:
    """24kHz · 16-bit · mono로 변환 (ffmpeg 필요)."""
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "24000", "-ac", "1", "-sample_fmt", "s16",
            str(out_path),
        ], check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"WARN: ffmpeg 실패 {in_path.name}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav-dir",  required=True, help="녹음한 WAV 폴더")
    ap.add_argument("--script",   help="recording_script.md (스크립트 기반)")
    ap.add_argument("--whisper",  action="store_true", help="Whisper STT 자동 받아쓰기")
    ap.add_argument("--out",      default="./manifest", help="metadata 출력 위치")
    ap.add_argument("--speaker",  default="user", help="화자 ID")
    ap.add_argument("--val-ratio", type=float, default=0.05)
    ap.add_argument("--normalize", action="store_true", help="24kHz mono로 ffmpeg 변환")
    args = ap.parse_args()

    wav_dir = Path(args.wav_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wavs = sorted(wav_dir.glob("*.wav"))
    print(f"WAV files: {len(wavs)}")
    if not wavs:
        print("ERROR: WAV 파일이 없습니다. 녹음을 확인하세요.")
        return 1

    # 정규화 (선택)
    if args.normalize:
        norm_dir = wav_dir.parent / f"{wav_dir.name}_24k"
        norm_dir.mkdir(exist_ok=True)
        print(f"Normalizing to {norm_dir} ...")
        new_wavs = []
        for w in wavs:
            out = norm_dir / w.name
            if normalize_wav(w, out):
                new_wavs.append(out)
        wavs = new_wavs
        wav_dir = norm_dir

    # 텍스트 매칭
    pairs = []
    if args.script:
        sentences = parse_script(Path(args.script))
        print(f"Script sentences: {len(sentences)}")
        for w in wavs:
            # 파일명에서 숫자 추출 (001.wav → 1)
            m = re.match(r"^0*(\d+)", w.stem)
            if not m: continue
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(sentences):
                pairs.append({"wav": w.name, "text": sentences[idx]})

    elif args.whisper:
        print("Loading Whisper large-v3 ...")
        import whisper
        asr = whisper.load_model("large-v3")
        for w in wavs:
            result = asr.transcribe(str(w), language="ko", fp16=False)
            text = result["text"].strip()
            if text:
                pairs.append({"wav": w.name, "text": text})
                print(f"  {w.name}: {text[:50]}")
    else:
        print("ERROR: --script 또는 --whisper 중 하나가 필요합니다.")
        return 1

    print(f"Valid pairs: {len(pairs)}")
    if not pairs:
        print("ERROR: 매칭된 pair가 없습니다.")
        return 1

    # split
    random.shuffle(pairs)
    n_val = max(int(len(pairs) * args.val_ratio), 1)
    val, train = pairs[:n_val], pairs[n_val:]

    def write(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(f"{r['wav']}|{r['text']}|{args.speaker}\n")

    write(out_dir / "metadata_train.csv", train)
    write(out_dir / "metadata_val.csv", val)
    lengths = [len(p["text"]) for p in pairs]
    print(f"train: {len(train)} · val: {len(val)}")
    print(f"text length: p50={statistics.median(lengths)} · max={max(lengths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

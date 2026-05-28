"""
Tier 3 학습 worker — 큐에서 queued 작업을 운영자에게 안내한다.

자동 학습은 Colab에서 사람이 실행하므로 worker 의 역할:
  1. 큐 폴링 (--watch 모드)
  2. 새 queued 작업 감지 시 → 다음 단계 SOP 출력
  3. queued → training → ready/failed 상태 천이 (CLI)
  4. 추론 서버에 어댑터 로드 알림 (선택, --notify-server)

사용 예:
    python tier3_worker.py --list                        # 대기 중인 작업 출력
    python tier3_worker.py --watch                       # 데몬 — 5초마다 폴링
    python tier3_worker.py --mark-training 5             # job 5 → training
    python tier3_worker.py --mark-ready    5 --ckpt /path/to/best.pth
    python tier3_worker.py --mark-ready    5 --ckpt ... --notify-server
    python tier3_worker.py --mark-failed   5 --error "OOM"
"""
import argparse
import os
import sys
import time
import urllib.request
import urllib.error
import json

from services.tier3_repo import Tier3Repository
from services.user_settings_service import UserSettingsService

try:
    from config import CLONED_VOICE_URL
except Exception:
    CLONED_VOICE_URL = os.getenv("CLONED_VOICE_URL", "")


def _print_sop(job) -> None:
    """전문가에게 학습 SOP 안내 — 새 queued 작업이 감지되면 출력."""
    sep = "─" * 64
    print(sep)
    print(f"📥 신규 학습 신청 — Job #{job.job_id}")
    print(f"   user_id={job.user_id} · guild_id={job.guild_id} · wavs={job.wav_count}")
    print(f"   wav_dir={job.wav_dir}")
    print(sep)
    print("다음 단계:")
    print("  1) WAV 디렉토리를 Drive 로 업로드")
    print(f"     예: rclone copy \"{job.wav_dir}\" gdrive:xtts_personal/job_{job.job_id}/my_voice")
    print("  2) 로컬에서 manifest 생성")
    print(f"     python tuning/1_data/prepare_personal.py \\")
    print(f"         --wav-dir \"{job.wav_dir}\" \\")
    print(f"         --script tuning/1_data/recording_script.md \\")
    print(f"         --out tuning/manifest_{job.job_id} --normalize")
    print(f"     → manifest_{job.job_id} 도 Drive 같은 경로에 업로드")
    print("  3) Colab 노트북 열기")
    print("     tuning/2_train/train_personal_colab.ipynb")
    print(f"     · DRIVE_ROOT 를 /content/drive/MyDrive/xtts_personal/job_{job.job_id} 로 설정")
    print("     · 셀 0~9 실행 (2~4 시간)")
    print("  4) 학습 시작 직후 — 상태 천이")
    print(f"     python tier3_worker.py --mark-training {job.job_id}")
    print("  5) 학습 완료 후 — ckpt 등록")
    print(f"     python tier3_worker.py --mark-ready {job.job_id} \\")
    print(f"         --ckpt /content/drive/MyDrive/xtts_personal/job_{job.job_id}/runs/.../best_model.pth \\")
    print(f"         --notify-server")
    print(sep)


def _notify_inference_server(ckpt_path: str) -> None:
    """추론 서버에 어댑터 사전 로드 요청 — 첫 합성 지연 제거."""
    if not CLONED_VOICE_URL:
        print("[notify] CLONED_VOICE_URL 비어있음 — 스킵", file=sys.stderr)
        return
    url = CLONED_VOICE_URL.rstrip("/") + "/load_ckpt"
    body = json.dumps({"ckpt": ckpt_path}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f"[notify] {url} → {resp.status} {resp.read().decode('utf-8','ignore')[:200]}")
    except urllib.error.URLError as e:
        print(f"[notify] 실패 ({e})  — 첫 /synthesize 호출에서 lazy load 됨", file=sys.stderr)


def _watch_loop(repo: Tier3Repository, interval: int = 5) -> int:
    """5초마다 큐 폴링 — 새 job 감지 시 SOP 출력."""
    print(f"[watch] polling tier3_jobs every {interval}s · Ctrl+C 종료")
    seen: set[int] = {j.job_id for j in repo.queued()}
    if seen:
        print(f"[watch] 이미 대기 중인 job: {sorted(seen)}")
    try:
        while True:
            current = repo.queued()
            for j in current:
                if j.job_id not in seen:
                    _print_sop(j)
                    seen.add(j.job_id)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[watch] 종료")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--watch", action="store_true", help="큐 폴링 데몬")
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--mark-training", type=int)
    ap.add_argument("--mark-ready",    type=int)
    ap.add_argument("--mark-failed",   type=int)
    ap.add_argument("--ckpt")
    ap.add_argument("--error")
    ap.add_argument("--notify-server", action="store_true",
                    help="--mark-ready 시 추론 서버에 어댑터 로드 요청")
    args = ap.parse_args()

    repo = Tier3Repository()
    settings = UserSettingsService()

    if args.list:
        jobs = repo.queued()
        if not jobs:
            print("queued: 없음")
            return 0
        for j in jobs:
            print(f"#{j.job_id}  user={j.user_id}  guild={j.guild_id}  "
                  f"wavs={j.wav_count}  dir={j.wav_dir}  submitted={j.submitted_at}")
        return 0

    if args.watch:
        return _watch_loop(repo, interval=args.interval)

    if args.mark_training:
        repo.update_status(args.mark_training, "training")
        print(f"job {args.mark_training} → training")
        return 0

    if args.mark_ready:
        if not args.ckpt:
            print("--ckpt 필요", file=sys.stderr)
            return 1
        repo.update_status(args.mark_ready, "ready", ckpt_path=args.ckpt)
        job = repo.latest_for(0, 0)  # 단순 조회용 — 실제로는 job_id로 user 조회 필요
        # user/guild 갱신
        from db.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, guild_id FROM tier3_jobs WHERE job_id=?", (args.mark_ready,)
            ).fetchone()
        if row:
            settings.set_tier3_ready(row["user_id"], row["guild_id"], ckpt_path=args.ckpt)
            print(f"job {args.mark_ready} → ready  · user={row['user_id']}  ckpt={args.ckpt}")
        if args.notify_server:
            _notify_inference_server(args.ckpt)
        return 0

    if args.mark_failed:
        repo.update_status(args.mark_failed, "failed", error=args.error or "unknown")
        from db.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT user_id, guild_id FROM tier3_jobs WHERE job_id=?", (args.mark_failed,)
            ).fetchone()
        if row:
            settings.set_tier3_status(row["user_id"], row["guild_id"], "failed")
        print(f"job {args.mark_failed} → failed  · error={args.error}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

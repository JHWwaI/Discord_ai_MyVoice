"""
9단계 — 봇 자동 재시작 + Discord 에러 웹훅 알림

실행: .venv\Scripts\python.exe watchdog.py
"""

import subprocess
import sys
import time
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL: str = os.getenv("ERROR_WEBHOOK_URL", "")
PYTHON = sys.executable
BOT_SCRIPT = os.path.join(os.path.dirname(__file__), "main.py")
RESTART_DELAY = 10  # 재시작 전 대기 초
MAX_FAST_CRASHES = 5  # 연속 빠른 크래시 허용 횟수
FAST_CRASH_THRESHOLD = 30  # 이 초 이내 종료 → 빠른 크래시


def send_webhook(content: str) -> None:
    if not WEBHOOK_URL:
        return
    try:
        data = json.dumps({"content": content}).encode()
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[watchdog] 웹훅 전송 실패: {e}")


def run_bot() -> None:
    fast_crash_count = 0
    run_count = 0

    while True:
        run_count += 1
        start = time.time()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[watchdog] {ts} — 봇 시작 (#{run_count})")

        proc = subprocess.run([PYTHON, BOT_SCRIPT])

        elapsed = time.time() - start
        exit_code = proc.returncode
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[watchdog] {ts} — 봇 종료 (코드={exit_code}, 가동={elapsed:.0f}초)")

        if exit_code == 0:
            print("[watchdog] 정상 종료. 재시작하지 않습니다.")
            break

        # 빠른 크래시 감지
        if elapsed < FAST_CRASH_THRESHOLD:
            fast_crash_count += 1
            msg = (
                f"⚠️ **봇 크래시** `#{run_count}` — "
                f"종료코드 `{exit_code}`, 가동 `{elapsed:.0f}초`\n"
                f"연속 빠른 크래시: {fast_crash_count}/{MAX_FAST_CRASHES}"
            )
            print(f"[watchdog] {msg}")
            send_webhook(msg)

            if fast_crash_count >= MAX_FAST_CRASHES:
                send_webhook(
                    f"🔴 **봇이 {MAX_FAST_CRASHES}회 연속 즉시 크래시 — 자동 재시작 중단**"
                )
                print("[watchdog] 연속 크래시 한도 초과. 종료합니다.")
                break
        else:
            fast_crash_count = 0
            send_webhook(
                f"🔄 **봇 재시작** `#{run_count + 1}` — "
                f"이전 가동 `{elapsed:.0f}초`, 종료코드 `{exit_code}`"
            )

        print(f"[watchdog] {RESTART_DELAY}초 후 재시작...")
        time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    run_bot()

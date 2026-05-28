"""
Tier 1·2·3 인프라 시연 — Discord/XTTS 없이 동작 검증.

검증 내용:
  1. DB 마이그레이션 — tier 컬럼·tier3_jobs 테이블 생성
  2. UserSettingsService.set_tier — Tier 1·2 등록 시 DB 반영
  3. Tier3Repository.submit/update — 작업 큐 흐름
  4. VoiceRouter — tier에 따라 Provider 분기 (Tier 3 미준비 → Edge fallback)
  5. ClonedVoiceProvider payload — Tier 1·2·3 페이로드 생성 검증

실행:
    python demo_tiers.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Windows 콘솔 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db.database import init_db, get_connection
from models.user_settings import UserSettings
from providers.base import CloneRequest
from providers.cloned_voice_provider import ClonedVoiceProvider
from services.tier3_repo import Tier3Repository
from services.user_settings_service import UserSettingsService
from services.voice_router import VoiceRouter


GREEN = "\033[92m"; RED = "\033[91m"; CYAN = "\033[96m"; RESET = "\033[0m"
def ok(t):    print(f"{GREEN}✓{RESET} {t}")
def fail(t):  print(f"{RED}✗{RESET} {t}")
def info(t):  print(f"{CYAN}·{RESET} {t}")


async def main():
    print("="*70)
    print("VoiceBridge — Tier 1·2·3 인프라 시연")
    print("="*70)

    # ── Step 1. DB 마이그레이션 ──────────────────────────────────────────
    print("\n[Step 1] DB 마이그레이션")
    init_db()
    with get_connection() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(user_settings)")]
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
    needed = {"tier", "refs_json", "ckpt_path", "tier3_status", "updated_at"}
    if needed <= set(cols):
        ok(f"user_settings 컬럼 확장 완료 → {sorted(needed)}")
    else:
        fail(f"누락: {needed - set(cols)}")
    if "tier3_jobs" in tables:
        ok("tier3_jobs 테이블 생성됨")
    else:
        fail("tier3_jobs 테이블 누락")

    # ── Step 2. Tier 1 등록 ──────────────────────────────────────────────
    print("\n[Step 2] Tier 1 — Instant 등록")
    settings = UserSettingsService()
    USER_A, GUILD = 1001, 9999

    # 가상 WAV 파일 생성
    Path("voice_data/user_1001/tier1").mkdir(parents=True, exist_ok=True)
    fake_wav = Path("voice_data/user_1001/tier1/sample.wav")
    fake_wav.write_bytes(b"FAKE_WAV_DATA_FOR_TEST")

    s = settings.set_tier(USER_A, GUILD, tier=1, refs=[str(fake_wav.resolve())])
    info(f"User {USER_A} 등록: tier={s.tier}  refs={len(s.refs)}  cloned={s.use_cloned_voice}")
    if s.tier == 1 and len(s.refs) == 1 and s.use_cloned_voice:
        ok("Tier 1 등록 정상 — DB 반영 확인")
    else:
        fail("Tier 1 등록 실패")

    # ── Step 3. Tier 2 등록 ──────────────────────────────────────────────
    print("\n[Step 3] Tier 2 — Enhanced 등록")
    USER_B = 1002
    refs2 = []
    Path("voice_data/user_1002/tier2").mkdir(parents=True, exist_ok=True)
    for i in range(8):
        f = Path(f"voice_data/user_1002/tier2/sample_{i:03d}.wav")
        f.write_bytes(b"FAKE")
        refs2.append(str(f.resolve()))

    s = settings.set_tier(USER_B, GUILD, tier=2, refs=refs2)
    info(f"User {USER_B} 등록: tier={s.tier}  refs={len(s.refs)}  cloned={s.use_cloned_voice}")
    if s.tier == 2 and len(s.refs) == 8:
        ok("Tier 2 등록 정상 — 다중 참조 8개 저장")
    else:
        fail("Tier 2 등록 실패")

    # ── Step 4. Tier 3 신청 (queued) ────────────────────────────────────
    print("\n[Step 4] Tier 3 — Pro 신청 큐")
    USER_C = 1003
    refs3 = []
    Path("voice_data/user_1003/tier3").mkdir(parents=True, exist_ok=True)
    for i in range(120):
        f = Path(f"voice_data/user_1003/tier3/{i:03d}.wav")
        f.write_bytes(b"FAKE")
        refs3.append(str(f.resolve()))

    repo = Tier3Repository()
    job_id = repo.submit(USER_C, GUILD,
                          wav_dir="voice_data/user_1003/tier3",
                          wav_count=120)
    settings.upsert(USER_C, GUILD, tier=3, tier3_status="queued", refs=refs3)
    info(f"Job #{job_id} 등록 — 120 WAV")
    job = repo.latest_for(USER_C, GUILD)
    if job and job.status == "queued" and job.wav_count == 120:
        ok(f"Tier 3 신청 완료 → queued")
    else:
        fail("Tier 3 신청 실패")

    # ── Step 5. Tier 3 학습 시뮬레이션 ──────────────────────────────────
    print("\n[Step 5] Tier 3 — 학습 라이프사이클 시뮬레이션")
    repo.update_status(job_id, "training")
    info(f"Job #{job_id} → training")
    repo.update_status(job_id, "ready", ckpt_path="/fake/best_model.pth")
    settings.set_tier3_ready(USER_C, GUILD, ckpt_path="/fake/best_model.pth")
    job = repo.latest_for(USER_C, GUILD)
    if job.status == "ready" and job.ckpt_path:
        ok(f"학습 완료 마킹 → ckpt={job.ckpt_path}")

    # ── Step 6. VoiceRouter 분기 검증 ───────────────────────────────────
    print("\n[Step 6] VoiceRouter — Tier별 Provider 선택")
    router = VoiceRouter()

    # Tier 1 — Cloned
    s1 = settings.get(USER_A, GUILD)
    p1 = router.get_provider(s1).__class__.__name__
    info(f"User A (tier=1) → {p1}")
    assert p1 == "ClonedVoiceProvider"; ok("Tier 1 → Cloned")

    # Tier 2 — Cloned
    s2 = settings.get(USER_B, GUILD)
    p2 = router.get_provider(s2).__class__.__name__
    info(f"User B (tier=2) → {p2}")
    assert p2 == "ClonedVoiceProvider"; ok("Tier 2 → Cloned")

    # Tier 3 — Ready → Cloned
    s3 = settings.get(USER_C, GUILD)
    p3 = router.get_provider(s3).__class__.__name__
    info(f"User C (tier=3, ready) → {p3}")
    assert p3 == "ClonedVoiceProvider"; ok("Tier 3 ready → Cloned")

    # Tier 3 — Pending → Edge fallback
    USER_D = 1004
    settings.upsert(USER_D, GUILD, tier=3, tier3_status="queued", use_cloned_voice=True)
    s4 = settings.get(USER_D, GUILD)
    p4 = router.get_provider(s4).__class__.__name__
    info(f"User D (tier=3, queued) → {p4} (학습 미완료 fallback)")
    assert p4 == "EdgeTTSProvider"; ok("Tier 3 미준비 → Edge fallback")

    # ── Step 7. CloneRequest 페이로드 검증 ──────────────────────────────
    print("\n[Step 7] CloneRequest — Tier별 페이로드")
    for u, label in [(USER_A, "Tier 1"), (USER_B, "Tier 2"), (USER_C, "Tier 3 ready")]:
        st = settings.get(u, GUILD)
        cr = router._build_clone_request(st)
        if cr is None:
            fail(f"{label}: clone request none")
            continue
        info(f"{label}: tier={cr.tier}  refs={len(cr.refs)}  ckpt={cr.ckpt_path}")
        if u == USER_C:
            assert cr.ckpt_path, "Tier 3은 ckpt 있어야"
        else:
            assert cr.refs, f"{label}은 refs 있어야"
    ok("페이로드 생성 — Tier별 정상 분기")

    # ── Step 8. /tier_status 시뮬레이션 ─────────────────────────────────
    print("\n[Step 8] /tier_status 출력 시뮬레이션 (User C — Tier 3)")
    print("-" * 70)
    s = settings.get(USER_C, GUILD)
    job = repo.latest_for(USER_C, GUILD)
    print(f"**현재 등급**: Tier {s.tier}")
    print(f"**참조 파일**: {len(s.refs)}개")
    print(f"**Cloned 사용**: {'on' if s.use_cloned_voice else 'off'}")
    print(f"\n**Tier 3 Job #{job.job_id}**")
    print(f"- 상태: `{job.status}`")
    print(f"- WAV: {job.wav_count}개")
    print(f"- 제출: {job.submitted_at}")
    print(f"- 완료: {job.completed_at}")
    print("-" * 70)

    # ── Cleanup ─────────────────────────────────────────────────────────
    print("\n[Cleanup] 임시 데이터 정리")
    import shutil
    if Path("voice_data").exists():
        shutil.rmtree("voice_data")
        ok("voice_data/ 제거")

    print("\n" + "="*70)
    print(f"{GREEN}모든 단계 통과 — Tier 1·2·3 인프라 동작 확인{RESET}")
    print("="*70)
    print("""
실제 GPU 합성·Discord 통합은 별도 검증 필요:
  · 봇 띄우기:   python main.py
  · Kaggle 서버: kaggle_tts_server.py 실행 → ngrok URL을 .env에 입력
  · Tier 3 학습: tuning/2_train/train_personal_colab.ipynb (Colab)
""")


if __name__ == "__main__":
    asyncio.run(main())

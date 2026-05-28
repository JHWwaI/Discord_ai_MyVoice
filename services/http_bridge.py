"""
외부 서비스 → 봇 HTTP 브릿지.

봇과 같은 프로세스에서 aiohttp 웹 서버를 띄워, 외부 HTTP 요청을 받아
Discord 음성 채널 합성·재생까지 트리거한다.

엔드포인트:
  GET  /                     — 데모 HTML 폼
  POST /api/say              — JSON {text, guild_id, voice_channel_id, user_id?} → 큐 enqueue
  POST /api/register         — multipart: tier, wavs[] → 사용자 등록
  GET  /api/health           — 상태 확인
  GET  /api/status?guild_id  — 현재 큐 상태

CORS는 와이드 오픈 (개인 프로젝트 가정). 운영 시 토큰 인증 추가.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web

import aiohttp

from config import CLONED_VOICE_URL, TIER3_MAX_WAVS, TIER3_MIN_WAVS, VOICE_DATA_DIR
from models.queue_item import QueueItem
from services.queue_manager import QueueManager
from services.tier3_repo import Tier3Repository
from services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)

# ── 데모 HTML ──
INDEX_HTML = """\
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>VoiceBridge — Cast your voice into Discord</title>
  <style>
    :root {
      --bg-0:        #1E1F22;
      --bg-1:        #2B2D31;
      --bg-2:        #313338;
      --bg-3:        #383A40;
      --bg-input:    #1E1F22;
      --line:        #1F2023;
      --text:        #F2F3F5;
      --text-sub:    #B5BAC1;
      --text-mut:    #80848E;
      --blurple:     #5865F2;
      --blurple-hov: #4752C4;
      --blurple-soft:rgba(88,101,242,0.12);
      --green:       #23A55A;
      --green-hov:   #1A8348;
      --red:         #DA373C;
      --red-hov:     #B62B30;
      --yellow:      #F0B232;
    }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; }
    body {
      font-family: "gg sans","Pretendard","Noto Sans KR","Helvetica Neue",Helvetica,Arial,sans-serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, rgba(88,101,242,0.18), transparent 60%),
        radial-gradient(900px 500px at 100% 0%, rgba(35,165,90,0.08), transparent 60%),
        var(--bg-0);
      color: var(--text);
      min-height: 100vh;
    }

    /* ── Nav ── */
    .nav {
      max-width: 1080px; margin: 0 auto; padding: 22px 24px;
      display: flex; align-items: center; gap: 16px;
    }
    .brand {
      display: flex; align-items: center; gap: 10px;
      font-weight: 700; letter-spacing: -0.01em; font-size: 18px;
    }
    .brand .logo {
      width: 32px; height: 32px; border-radius: 9px;
      background: var(--blurple); color: white;
      display: inline-flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 13px; font-family: Georgia, serif;
      box-shadow: 0 6px 18px rgba(88,101,242,0.45);
    }
    .nav .links { margin-left: auto; display: flex; gap: 6px; }
    .nav .links a {
      color: var(--text-sub); text-decoration: none; font-size: 14px;
      padding: 8px 12px; border-radius: 6px;
    }
    .nav .links a:hover { background: var(--bg-1); color: var(--text); }
    .nav .status-chip {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 12px; color: var(--text-sub);
      padding: 6px 10px; border-radius: 999px;
      background: var(--bg-1); border: 1px solid var(--line);
    }
    .nav .status-chip::before {
      content: ""; width: 8px; height: 8px; border-radius: 50%;
      background: var(--green); box-shadow: 0 0 0 3px rgba(35,165,90,0.18);
    }

    /* ── Hero ── */
    .hero {
      max-width: 1080px; margin: 16px auto 32px; padding: 0 24px;
      text-align: center;
    }
    .hero .tag {
      display: inline-block; padding: 4px 10px; border-radius: 999px;
      background: var(--blurple-soft); color: var(--blurple);
      font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
      margin-bottom: 14px;
    }
    .hero h1 {
      font-size: 40px; line-height: 1.15; margin: 0 0 12px;
      letter-spacing: -0.02em; font-weight: 800;
    }
    .hero h1 .accent { color: var(--blurple); }
    .hero p {
      color: var(--text-sub); font-size: 16px; max-width: 640px;
      margin: 0 auto;
    }

    /* ── Main grid ── */
    .container { max-width: 1080px; margin: 0 auto; padding: 0 24px 64px; }
    .grid {
      display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px;
    }
    @media (max-width: 880px) { .grid { grid-template-columns: 1fr; } }

    .card {
      background: var(--bg-1); border-radius: 12px; padding: 22px 22px;
      border: 1px solid var(--line);
    }
    .card.span-2 { grid-column: 1 / -1; }
    .card-head {
      display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
    }
    .card-head .step {
      width: 26px; height: 26px; border-radius: 8px;
      background: var(--blurple-soft); color: var(--blurple);
      display: inline-flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 13px;
    }
    .card-head h2 {
      margin: 0; font-size: 16px; font-weight: 700; letter-spacing: -0.01em;
    }
    .card-desc { color: var(--text-mut); font-size: 13.5px; margin: -6px 0 14px; }

    label {
      display: block; font-size: 11.5px; font-weight: 700;
      letter-spacing: 0.05em; text-transform: uppercase;
      color: var(--text-sub); margin: 6px 0 6px;
    }
    input, textarea {
      width: 100%; padding: 10px 12px; border: 1px solid var(--line);
      border-radius: 6px; background: var(--bg-input); color: var(--text);
      font-family: inherit; font-size: 14.5px; box-sizing: border-box;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    input:focus, textarea:focus {
      outline: none; border-color: var(--blurple);
      box-shadow: 0 0 0 3px rgba(88,101,242,0.18);
    }
    textarea { resize: vertical; min-height: 86px; }
    .row { display:flex; gap:10px; flex-wrap: wrap; }
    .row > div { flex:1; min-width: 160px; }

    button {
      background: var(--blurple); color: white; border: none;
      padding: 9px 16px; border-radius: 6px; font-weight: 600;
      font-size: 14px; cursor: pointer; transition: background 0.15s, transform 0.04s;
      font-family: inherit;
    }
    button:hover:not(:disabled) { background: var(--blurple-hov); }
    button:active:not(:disabled) { transform: translateY(1px); }
    button:disabled { background: var(--bg-3); color: var(--text-mut); cursor: not-allowed; }
    button.secondary { background: var(--bg-3); }
    button.secondary:hover:not(:disabled) { background: #4E5058; }
    button.green { background: var(--green); }
    button.green:hover:not(:disabled) { background: var(--green-hov); }
    button.red { background: var(--red); }
    button.red:hover:not(:disabled) { background: var(--red-hov); }
    .actions { display:flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; align-items: center; }

    .out {
      background: var(--bg-input); color: #B5BAC1; padding: 12px 14px;
      border-radius: 6px; margin-top: 12px;
      font-family: "JetBrains Mono","Consolas",ui-monospace,monospace; font-size: 12.5px;
      white-space: pre-wrap; min-height: 2.5rem;
      border-left: 3px solid var(--blurple);
    }
    .out.ok   { border-left-color: var(--green); }
    .out.err  { border-left-color: var(--red); color: #F9C2C5; }
    .out.live { border-left-color: var(--yellow); }

    .rec-status {
      margin-left: auto; font-size: 13px; color: var(--text-mut);
      display: inline-flex; align-items: center; gap: 6px;
    }
    .rec-status.live { color: var(--red); font-weight: 600; }
    .rec-status.live::before {
      content: ""; width: 8px; height: 8px; border-radius: 50%;
      background: var(--red); display: inline-block;
      animation: pulse 1s infinite;
    }
    @keyframes pulse { 50% { opacity: 0.3; } }

    audio { width: 100%; margin-top: 10px; }
    audio::-webkit-media-controls-panel { background: var(--bg-3); }

    .prompt-quote {
      background: var(--blurple-soft); border-left: 3px solid var(--blurple);
      padding: 11px 14px; border-radius: 0 6px 6px 0; margin: 4px 0 12px;
      color: var(--text); font-size: 14px; line-height: 1.5;
    }
    .badge {
      display: inline-block; background: var(--blurple-soft); color: var(--blurple);
      padding: 2px 8px; border-radius: 999px; font-size: 11px;
      font-weight: 700; letter-spacing: 0.04em; margin-left: 6px;
    }

    /* ── Tabs ── */
    .tabs {
      display: flex; gap: 6px; margin: 6px 0 12px;
      border-bottom: 1px solid var(--line); padding-bottom: 0;
    }
    .tab {
      background: transparent; color: var(--text-sub);
      border: 1px solid transparent; border-bottom: none;
      padding: 10px 18px; border-radius: 8px 8px 0 0;
      font-weight: 600; font-size: 14px; cursor: pointer;
      display: inline-flex; align-items: center; gap: 8px;
      position: relative; top: 1px;
    }
    .tab:hover:not(.active) { background: var(--bg-1); color: var(--text); }
    .tab.active {
      background: var(--bg-1); color: var(--text);
      border-color: var(--line); border-bottom-color: var(--bg-1);
    }
    .tab .pill {
      font-size: 11px; padding: 2px 7px; border-radius: 999px;
      background: var(--bg-3); color: var(--text-mut); font-weight: 700;
    }
    .tab.active .pill { background: var(--blurple-soft); color: var(--blurple); }
    .tab.expert.active .pill { background: rgba(240,178,50,0.18); color: var(--yellow); }
    .tab-desc {
      color: var(--text-mut); font-size: 13.5px; margin: 0 0 14px;
      padding: 10px 14px; background: var(--bg-1); border-radius: 8px;
      border-left: 3px solid var(--blurple);
    }
    .tab-desc.expert { border-left-color: var(--yellow); }
    .tab-pane { display: none; }
    .tab-pane.active { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 880px) { .tab-pane.active { grid-template-columns: 1fr; } }
    .tab-pane .card.span-2 { grid-column: 1 / -1; }

    /* ── How-it-works strip ── */
    .how {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;
      margin: 28px 0 0;
    }
    @media (max-width: 720px) { .how { grid-template-columns: 1fr; } }
    .how .step-card {
      background: var(--bg-1); border: 1px solid var(--line);
      padding: 16px; border-radius: 10px;
    }
    .how .step-card .n {
      width: 28px; height: 28px; border-radius: 8px;
      background: var(--blurple); color: white;
      display: inline-flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 13px; margin-bottom: 10px;
    }
    .how .step-card h3 { margin: 0 0 4px; font-size: 14.5px; }
    .how .step-card p { margin: 0; color: var(--text-mut); font-size: 13px; line-height: 1.5; }

    footer {
      max-width: 1080px; margin: 32px auto 0; padding: 24px;
      color: var(--text-mut); font-size: 12.5px;
      border-top: 1px solid var(--line);
      display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    }
  </style>
</head>
<body>
  <nav class="nav">
    <div class="brand">
      <span class="logo">VB</span>
      <span>VoiceBridge</span>
    </div>
    <div class="links">
      <a href="/api/health" target="_blank">/health</a>
      <a href="https://github.com/" target="_blank">GitHub</a>
    </div>
    <span class="status-chip">Bot online</span>
  </nav>

  <header class="hero">
    <span class="tag">DISCORD VOICE-CLONE BOT</span>
    <h1>당신의 목소리를 <span class="accent">Discord 음성 채널</span>에 흘려보내세요.</h1>
    <p><strong>Light</strong> — 6초 녹음으로 즉시 시작 · &nbsp;<strong>Expert</strong> — 다중 참조·fine-tune 으로 한 단계 위 품질.
       동일한 XTTS v2 인프라 위에서 사용자가 부담을 선택합니다.</p>
  </header>

  <main class="container">
    <!-- ⓘ 식별 (공유) -->
    <section class="card" style="margin-bottom:16px;">
      <div class="card-head">
        <span class="step">i</span>
        <h2>Discord 식별 정보</h2>
      </div>
      <div class="card-desc">Discord 설정 → 고급 → 개발자 모드 ON → 우클릭 → ID 복사</div>
      <div class="row">
        <div>
          <label>User ID</label>
          <input id="user" placeholder="본인 Discord ID">
        </div>
        <div>
          <label>Guild ID</label>
          <input id="guild" placeholder="서버 ID">
        </div>
        <div>
          <label>Voice Channel ID</label>
          <input id="vch" placeholder="음성 채널 ID">
        </div>
      </div>
    </section>

    <!-- 탭 — Light / Expert -->
    <div class="tabs" role="tablist">
      <button class="tab light active" data-pane="paneLight" role="tab">
        ☀ Light user <span class="pill">6초 · 즉시</span>
      </button>
      <button class="tab expert" data-pane="paneExpert" role="tab">
        🛠 Expert user <span class="pill">Tier 2 · 3</span>
      </button>
    </div>

    <!-- ── Light pane ───────────────────────────────────────────── -->
    <div class="tab-pane active" id="paneLight">
      <div class="tab-desc span-2" style="grid-column: 1 / -1;">
        <strong>Light user</strong> — 6초만 녹음하면 그 자리에서 Discord 발화 시작.
        설치·세팅 없이 즉시 체험. 일반 사용자 80%가 이 경로로 충분합니다.
      </div>

      <!-- 녹음 6초 -->
      <section class="card">
        <div class="card-head">
          <span class="step">1</span>
          <h2>음성 녹음 · 즉시 등록 <span class="badge">Tier 1</span></h2>
        </div>
        <div class="prompt-quote">"안녕하세요, 저는 이재환입니다. 오늘 음성 복제 봇을 시연합니다."</div>
        <div class="actions">
          <button id="recStart" class="red">🎙 녹음 시작</button>
          <button id="recStop" class="secondary" disabled>■ 종료</button>
          <button id="recRegister" class="green" disabled>등록</button>
          <span id="recStatus" class="rec-status">대기 중</span>
        </div>
        <audio id="recPlayback" controls hidden></audio>
        <div class="out" id="recOut">녹음 결과가 여기에 표시됩니다.</div>
      </section>

      <!-- Light 안내 -->
      <section class="card">
        <div class="card-head">
          <span class="step">2</span>
          <h2>그 다음 단계</h2>
        </div>
        <p style="color:var(--text-sub); font-size:14px; line-height:1.6; margin:4px 0 10px;">
          ① 위에서 6초 녹음 후 <strong>등록</strong> 버튼.<br>
          ② 아래 <strong>텍스트 → 음성 발화</strong> 카드에서 문장을 입력하고 전송.<br>
          ③ Discord 음성 채널에서 본인 목소리로 봇이 발화합니다.
        </p>
        <p style="color:var(--text-mut); font-size:13px; line-height:1.5;">
          더 자연스러운 한국어 발음·말투를 원한다면 <strong>Expert</strong> 탭으로 이동해
          Tier 2(1~3분 다중 참조) 또는 Tier 3(fine-tune) 을 시도해 보세요.
        </p>
      </section>
    </div>

    <!-- ── Expert pane ───────────────────────────────────────────── -->
    <div class="tab-pane" id="paneExpert">
      <div class="tab-desc expert span-2" style="grid-column: 1 / -1;">
        <strong>Expert user</strong> — 한국어 품질·말투 충실도를 한 단계 끌어올리는 경로.
        Tier 2(1~3분 다중 참조)는 즉시 적용, Tier 3(fine-tune)은 2~4시간 비동기 학습.
      </div>

      <!-- Tier 2 다중 참조 -->
      <section class="card">
        <div class="card-head">
          <span class="step">2</span>
          <h2>Tier 2 — 다중 참조 등록 <span class="badge">Enhanced</span></h2>
        </div>
        <div class="card-desc">
          5~15개의 짧은 본인 음성 WAV를 업로드하면 다중 참조 평균으로
          한국어 발음·톤 안정성이 향상됩니다. 학습 없이 즉시 적용.
        </div>
        <label>WAV 파일 다중 선택 (5~15개)</label>
        <input id="tier2Files" type="file" accept="audio/wav,audio/x-wav,audio/mpeg,audio/webm" multiple>
        <div class="actions">
          <button id="tier2Submit" class="green">📤 다중 참조 등록</button>
          <span id="tier2Count" class="rec-status" style="margin-left:auto;">선택된 파일: 0개</span>
        </div>
        <div class="out" id="tier2Out">등록 결과가 여기에 표시됩니다.</div>
      </section>

      <!-- Tier 3 fine-tune -->
      <section class="card">
        <div class="card-head">
          <span class="step">3</span>
          <h2>Tier 3 — 본인 전용 모델 학습 <span class="badge">Pro</span></h2>
        </div>
        <div class="card-desc">
          100~400개의 본인 음성을 업로드하면 GPU 학습 작업이 큐에 등록됩니다.
          학습은 백그라운드로 <strong>2~4 시간</strong> 소요. 상태는 아래에서 자동 폴링.
        </div>
        <label>WAV 파일 다중 선택 (100~400개)</label>
        <input id="tier3Files" type="file" accept="audio/wav,audio/x-wav,audio/mpeg,audio/webm" multiple>
        <div class="actions">
          <button id="tier3Submit" class="green">📤 학습 신청</button>
          <button id="tier3Refresh" class="secondary">상태 새로고침</button>
          <span id="tier3Count" class="rec-status" style="margin-left:auto;">선택된 파일: 0개</span>
        </div>
        <div class="out" id="tier3Out">신청 결과 / 상태가 여기에 표시됩니다.</div>
      </section>
    </div>

    <!-- ▶ 발화 (공유) -->
    <section class="card" style="margin-top:16px;">
      <div class="card-head">
        <span class="step">▶</span>
        <h2>텍스트 → 음성 발화</h2>
      </div>
      <div class="card-desc">현재 등록된 등급(Tier 1/2/3)으로 Discord 음성 채널에 발화합니다.</div>
      <label>읽을 텍스트</label>
      <textarea id="text" placeholder="안녕하세요, 외부에서 보낸 메시지입니다."></textarea>
      <div class="actions">
        <button id="sayBtn">📨 Discord로 전송</button>
      </div>
      <div class="out" id="sayOut">결과가 여기에 표시됩니다.</div>
    </section>

    <!-- How it works -->
    <div class="how">
      <div class="step-card">
        <div class="n">1</div>
        <h3>Capture</h3>
        <p>브라우저 MediaRecorder로 6~10초 마이크 녹음 → 서버에서 ffmpeg로 24kHz mono WAV 변환.</p>
      </div>
      <div class="step-card">
        <div class="n">2</div>
        <h3>Clone</h3>
        <p>XTTS v2 zero-shot 모델이 참조 음성을 임베딩하고 텍스트를 본인 음색으로 합성.</p>
      </div>
      <div class="step-card">
        <div class="n">3</div>
        <h3>Cast</h3>
        <p>discord.py 봇이 asyncio 큐로 직렬화해 지정한 음성 채널에 ffmpeg 스트리밍으로 재생.</p>
      </div>
    </div>
  </main>

  <footer>
    <span>VoiceBridge · 개인 포트폴리오 데모</span>
    <span>Built with discord.py · aiohttp · XTTS v2</span>
  </footer>

  <script>
    const $ = (id) => document.getElementById(id);
    const recOut = $("recOut"), sayOut = $("sayOut"), status = $("recStatus");

    const setOut = (el, text, kind="info") => {
      el.classList.remove("ok","err","live");
      if (kind === "ok") el.classList.add("ok");
      else if (kind === "err") el.classList.add("err");
      else if (kind === "live") el.classList.add("live");
      el.textContent = text;
    };

    // ── 탭 전환 ──
    document.querySelectorAll(".tab").forEach(t => {
      t.onclick = () => {
        document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(x => x.classList.remove("active"));
        t.classList.add("active");
        $(t.dataset.pane).classList.add("active");
      };
    });

    // ── Tier 2 다중 참조 업로드 ──
    const tier2Files = $("tier2Files"), tier2Out = $("tier2Out"), tier2Count = $("tier2Count");
    tier2Files.onchange = () => {
      const n = tier2Files.files ? tier2Files.files.length : 0;
      tier2Count.textContent = `선택된 파일: ${n}개`;
      tier2Count.style.color = (n >= 5 && n <= 15) ? "var(--green)" : "var(--text-mut)";
    };
    $("tier2Submit").onclick = async () => {
      const user = $("user").value.trim(), guild = $("guild").value.trim();
      const files = tier2Files.files;
      if (!user || !guild) { setOut(tier2Out, "User ID + Guild ID 필요", "err"); return; }
      if (!files || files.length < 5 || files.length > 15) {
        setOut(tier2Out, `WAV 5~15개 필요 (현재 ${files?files.length:0}개)`, "err"); return;
      }
      setOut(tier2Out, `업로드 중... (${files.length}개)`, "live");
      const fd = new FormData();
      fd.append("tier", "2"); fd.append("user_id", user); fd.append("guild_id", guild);
      for (const f of files) fd.append("wavs", f, f.name);
      try {
        const r = await fetch("/api/register", { method: "POST", body: fd });
        const j = await r.json();
        setOut(tier2Out, `HTTP ${r.status}\\n${JSON.stringify(j, null, 2)}`, r.ok ? "ok" : "err");
      } catch (e) { setOut(tier2Out, "ERROR: " + e, "err"); }
    };

    // ── 녹음 ──
    let mediaRecorder = null;
    let chunks = [];
    let lastBlob = null;
    let timer = null;

    $("recStart").onclick = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
        chunks = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
        mediaRecorder.onstop = () => {
          lastBlob = new Blob(chunks, { type: 'audio/webm' });
          const url = URL.createObjectURL(lastBlob);
          const audio = $("recPlayback");
          audio.src = url; audio.hidden = false;
          setOut(recOut, `녹음 완료: ${(lastBlob.size/1024).toFixed(1)} KB · 등록 가능`, "ok");
          $("recRegister").disabled = false;
          stream.getTracks().forEach(t => t.stop());
          clearInterval(timer);
        };
        mediaRecorder.start();
        $("recStart").disabled = true;
        $("recStop").disabled = false;
        status.textContent = "REC 00:00";
        status.classList.add("live");
        setOut(recOut, "녹음 중... 평소 말투로 6~10초 정도 말해주세요.", "live");
        let sec = 0;
        timer = setInterval(() => {
          sec++;
          const m = String(Math.floor(sec/60)).padStart(2,'0');
          const s = String(sec%60).padStart(2,'0');
          status.textContent = `REC ${m}:${s}`;
          if (sec >= 30) $("recStop").click();
        }, 1000);
      } catch (e) {
        setOut(recOut, "마이크 권한 거부 또는 에러: " + e.message, "err");
      }
    };

    $("recStop").onclick = () => {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        $("recStart").disabled = false;
        $("recStop").disabled = true;
        status.textContent = "녹음 종료";
        status.classList.remove("live");
      }
    };

    $("recRegister").onclick = async () => {
      if (!lastBlob) { setOut(recOut, "먼저 녹음하세요.", "err"); return; }
      const user = $("user").value, guild = $("guild").value;
      if (!user || !guild) {
        setOut(recOut, "① 식별 정보의 User ID + Guild ID 입력 필요", "err");
        return;
      }
      setOut(recOut, "업로드 중...", "live");
      const fd = new FormData();
      fd.append("tier", "1");
      fd.append("user_id", user);
      fd.append("guild_id", guild);
      fd.append("wavs", lastBlob, "recording.webm");
      try {
        const r = await fetch("/api/register", { method: "POST", body: fd });
        const j = await r.json();
        setOut(recOut, JSON.stringify(j, null, 2), r.ok ? "ok" : "err");
      } catch (e) {
        setOut(recOut, "ERROR: " + e, "err");
      }
    };

    // ── /say ──
    // Discord Snowflake(19자리)는 JS Number 정밀도를 넘으므로 항상 string으로 전송.
    $("sayBtn").onclick = async () => {
      const text = $("text").value.trim();
      const guild = $("guild").value.trim();
      const vch = $("vch").value.trim();
      const user = $("user").value.trim();
      if (!text || !guild || !vch) {
        setOut(sayOut, "텍스트 · Guild ID · Voice Channel ID 모두 입력해 주세요.", "err");
        return;
      }
      setOut(sayOut, "전송 중...", "live");
      try {
        const payload = JSON.stringify({
          text: text, guild_id: guild, voice_channel_id: vch, user_id: user || "0",
        });
        const r = await fetch("/api/say", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
        });
        const raw = await r.text();
        let pretty = raw;
        try { pretty = JSON.stringify(JSON.parse(raw), null, 2); } catch(_) {}
        setOut(sayOut, `HTTP ${r.status}\n${pretty}`, r.ok ? "ok" : "err");
      } catch (e) {
        setOut(sayOut, "ERROR: " + e, "err");
      }
    };

    // ── Tier 3 신청 + 폴링 ──────────────────────────────────────
    const tier3Out = $("tier3Out");
    const tier3Files = $("tier3Files");
    const tier3Count = $("tier3Count");

    tier3Files.onchange = () => {
      const n = tier3Files.files ? tier3Files.files.length : 0;
      tier3Count.textContent = `선택된 파일: ${n}개`;
      tier3Count.style.color = (n >= 100 && n <= 400) ? "var(--green)" : "var(--text-mut)";
    };

    const STATUS_LABEL = {
      queued:   "🟡 대기 중 — GPU 워커 할당 대기",
      training: "🔵 학습 중 — 2~4시간 소요",
      ready:    "🟢 완료 — Tier 3 합성 사용 가능",
      failed:   "🔴 실패",
    };

    $("tier3Submit").onclick = async () => {
      const user = $("user").value.trim();
      const guild = $("guild").value.trim();
      const files = tier3Files.files;
      if (!user || !guild) {
        setOut(tier3Out, "User ID + Guild ID 입력 필요", "err"); return;
      }
      if (!files || files.length < 100 || files.length > 400) {
        setOut(tier3Out, `WAV 100~400개 필요 (현재 ${files ? files.length : 0}개)`, "err"); return;
      }
      setOut(tier3Out, `업로드 중... (${files.length}개 파일)`, "live");
      const fd = new FormData();
      fd.append("tier", "3"); fd.append("user_id", user); fd.append("guild_id", guild);
      for (const f of files) fd.append("wavs", f, f.name);
      try {
        const r = await fetch("/api/register", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok) { setOut(tier3Out, "HTTP " + r.status + "\\n" + JSON.stringify(j, null, 2), "err"); return; }
        setOut(tier3Out,
          `✅ 신청 완료 — Job #${j.job_id}\\n저장된 WAV: ${j.stored}개\\n\\n상태 폴링 중...`,
          "ok");
        startTier3Polling(user, guild);
      } catch (e) {
        setOut(tier3Out, "ERROR: " + e, "err");
      }
    };

    $("tier3Refresh").onclick = () => {
      const user = $("user").value.trim(), guild = $("guild").value.trim();
      if (!user || !guild) { setOut(tier3Out, "User ID + Guild ID 입력 필요", "err"); return; }
      pollTier3Once(user, guild);
    };

    let tier3Timer = null;
    function startTier3Polling(user, guild) {
      if (tier3Timer) clearInterval(tier3Timer);
      pollTier3Once(user, guild);
      tier3Timer = setInterval(() => pollTier3Once(user, guild), 10000);
    }

    async function pollTier3Once(user, guild) {
      try {
        const r = await fetch(`/api/tier3/jobs?user_id=${encodeURIComponent(user)}&guild_id=${encodeURIComponent(guild)}`);
        const j = await r.json();
        if (!j.found) { setOut(tier3Out, "신청 내역 없음", "live"); return; }
        const label = STATUS_LABEL[j.status] || j.status;
        const lines = [
          `${label}`,
          `Job #${j.job_id} · WAV ${j.wav_count}개`,
          `제출: ${j.submitted_at}`,
          j.started_at   ? `학습 시작: ${j.started_at}` : "",
          j.completed_at ? `완료: ${j.completed_at}`   : "",
          j.ckpt_path    ? `체크포인트: ${j.ckpt_path}` : "",
          j.error        ? `에러: ${j.error}`           : "",
        ].filter(Boolean);
        const kind = j.status === "ready" ? "ok"
                   : j.status === "failed" ? "err"
                   : "live";
        setOut(tier3Out, lines.join("\\n"), kind);
        if (j.status === "ready" || j.status === "failed") {
          if (tier3Timer) { clearInterval(tier3Timer); tier3Timer = null; }
        }
      } catch (e) {
        setOut(tier3Out, "ERROR: " + e, "err");
      }
    }
  </script>
</body>
</html>
"""


class HttpBridge:
    """봇 → aiohttp 브릿지. main에서 인스턴스 만들어 start_in_background()로 띄움."""

    def __init__(self, bot, queue: QueueManager, settings: UserSettingsService,
                 host: str = "0.0.0.0", port: int = 8090) -> None:
        self.bot = bot
        self.queue = queue
        self.settings = settings
        self.tier3 = Tier3Repository()
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None

    # ── handlers ───────────────────────────────────────────────────────────
    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "bot_ready": self.bot.is_ready(),
            "guilds": len(self.bot.guilds),
        })

    async def _say(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        text = (data.get("text") or "").strip()
        guild_id_raw = data.get("guild_id")
        vch_id_raw = data.get("voice_channel_id")
        user_id_raw = data.get("user_id") or 0

        if not text or not guild_id_raw or not vch_id_raw:
            return web.json_response(
                {"error": "text, guild_id, voice_channel_id required"}, status=400,
            )

        try:
            guild_id = int(guild_id_raw)
            vch_id   = int(vch_id_raw)
            user_id  = int(user_id_raw)
        except ValueError:
            return web.json_response({"error": "id must be integer"}, status=400)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "guild not found / bot not joined"}, status=404)

        channel = guild.get_channel(vch_id)
        if channel is None or channel.type.name != "voice":
            return web.json_response({"error": "voice channel not found"}, status=404)

        # 봇이 해당 채널에 없으면 자동 입장
        vc = guild.voice_client
        if not vc or vc.channel.id != vch_id:
            try:
                if vc:
                    await vc.move_to(channel)
                else:
                    await channel.connect()
            except Exception as e:
                logger.exception("voice connect failed")
                return web.json_response({"error": f"voice connect failed: {e}"}, status=502)

        # 등록된 사용자 정보 — 없으면 default
        user_name = "external"
        if user_id:
            member = guild.get_member(user_id)
            if member:
                user_name = member.display_name

        item = QueueItem(
            text=text, user_id=user_id or 0, user_name=user_name,
            guild_id=guild_id, channel=channel,
        )
        started, position = await self.queue.enqueue(guild, item)

        return web.json_response({
            "ok": True,
            "started_immediately": started,
            "queue_position": position,
            "guild_id": str(guild_id),
            "voice_channel": channel.name,
            "text_len": len(text),
        })

    async def _register(self, request: web.Request) -> web.Response:
        """multipart/form-data — tier(int), user_id(int), guild_id(int), wavs(files).

        브라우저 MediaRecorder는 webm/opus로 녹음하므로 ffmpeg로 WAV 변환.
        """
        import subprocess
        from config import require_ffmpeg

        reader = await request.multipart()
        fields: dict[str, str] = {}
        wav_files: list[bytes] = []
        wav_names: list[str] = []

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "wavs":
                name = part.filename or "voice.wav"
                # webm·m4a·mp3 등도 받아서 변환
                if not any(name.lower().endswith(ext) for ext in (".wav", ".webm", ".m4a", ".mp3", ".ogg")):
                    continue
                buf = await part.read()
                wav_files.append(buf)
                wav_names.append(name)
            else:
                fields[part.name] = (await part.read()).decode("utf-8", "ignore")

        try:
            tier = int(fields.get("tier", "1"))
            user_id = int(fields.get("user_id", "0"))
            guild_id = int(fields.get("guild_id", "0"))
        except ValueError:
            return web.json_response({"error": "tier/user_id/guild_id must be integer"}, status=400)

        if not wav_files:
            return web.json_response({"error": "no wav uploaded"}, status=400)

        # 저장 위치
        save_dir = Path(VOICE_DATA_DIR) / f"user_{user_id}" / f"tier{tier}"
        save_dir.mkdir(parents=True, exist_ok=True)
        # 기존 파일 비움
        for old in save_dir.glob("*.wav"):
            old.unlink(missing_ok=True)

        ffmpeg = require_ffmpeg()
        paths: list[str] = []
        for i, (name, blob) in enumerate(zip(wav_names, wav_files), 1):
            # 1) 원본 일시 저장
            raw_path = save_dir / f"_raw_{i:03d}_{name}"
            raw_path.write_bytes(blob)
            # 2) WAV로 변환 (24kHz · 16-bit · mono)
            wav_path = save_dir / f"{i:03d}.wav"
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-i", str(raw_path),
                     "-ar", "24000", "-ac", "1", "-sample_fmt", "s16",
                     str(wav_path)],
                    check=True, capture_output=True,
                )
                paths.append(str(wav_path.resolve()))
            except subprocess.CalledProcessError as e:
                logger.warning("ffmpeg failed for %s: %s", name, e.stderr[:200])
            finally:
                raw_path.unlink(missing_ok=True)

        # ── XTTS 서버로 자동 푸시 (있으면) ──
        forwarded = False
        forward_error: str | None = None
        if CLONED_VOICE_URL and paths:
            try:
                forwarded = await self._forward_to_xtts(user_id, tier, paths)
            except Exception as e:
                forward_error = str(e)
                logger.warning("forward to xtts failed: %s", e)

        job_id: int | None = None
        if tier in (1, 2):
            self.settings.set_tier(user_id, guild_id, tier=tier, refs=paths)
        elif tier == 3:
            # Tier 3 — fine-tune 신청: 데이터 검증 + 학습 큐 등록
            if not (TIER3_MIN_WAVS <= len(paths) <= TIER3_MAX_WAVS):
                return web.json_response({
                    "error": f"tier 3 requires {TIER3_MIN_WAVS}~{TIER3_MAX_WAVS} wavs "
                             f"(got {len(paths)})",
                }, status=400)
            self.settings.upsert(
                user_id, guild_id, tier=3, tier3_status="queued", refs=paths,
            )
            job_id = self.tier3.submit(
                user_id=user_id, guild_id=guild_id,
                wav_dir=str(save_dir.resolve()), wav_count=len(paths),
            )
        else:
            return web.json_response({"error": f"unknown tier {tier}"}, status=400)

        return web.json_response({
            "ok": True, "tier": tier, "stored": len(paths),
            "user_id": str(user_id), "guild_id": str(guild_id),
            "job_id": job_id,
            "forwarded_to_xtts": forwarded,
            "forward_error": forward_error,
        })

    async def _forward_to_xtts(self, user_id: int, tier: int, paths: list[str]) -> bool:
        """변환된 WAV 들을 XTTS 추론 서버(/upload_refs)로 자동 전송.

        Discord 봇 호스트와 XTTS 추론 서버가 다른 머신이므로 파일 동기화가 필요.
        ngrok URL 이 비어있으면 호출하지 않음.
        """
        url = CLONED_VOICE_URL.rstrip("/") + "/upload_refs"
        form = aiohttp.FormData()
        form.add_field("user_id", str(user_id))
        form.add_field("tier",    str(tier))
        for p in paths:
            form.add_field(
                "files",
                open(p, "rb"),
                filename=os.path.basename(p),
                content_type="audio/wav",
            )
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(url, data=form) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"xtts {resp.status}: {body[:200]}")
                logger.info("forwarded %d wavs to xtts: %s", len(paths), body[:200])
                return True

    async def _tier3_jobs(self, request: web.Request) -> web.Response:
        """GET /api/tier3/jobs?user_id=&guild_id= — 최신 학습 작업 상태 조회 (폴링용)."""
        user_id_raw = request.query.get("user_id")
        guild_id_raw = request.query.get("guild_id")
        if not user_id_raw or not guild_id_raw:
            return web.json_response({"error": "user_id, guild_id required"}, status=400)
        try:
            user_id = int(user_id_raw); guild_id = int(guild_id_raw)
        except ValueError:
            return web.json_response({"error": "id must be integer"}, status=400)

        job = self.tier3.latest_for(user_id, guild_id)
        if not job:
            return web.json_response({"found": False})
        return web.json_response({
            "found":        True,
            "job_id":       job.job_id,
            "status":       job.status,         # queued · training · ready · failed
            "wav_count":    job.wav_count,
            "wav_dir":      job.wav_dir,
            "ckpt_path":    job.ckpt_path,
            "error":        job.error,
            "submitted_at": job.submitted_at,
            "started_at":   job.started_at,
            "completed_at": job.completed_at,
        })

    async def _status(self, request: web.Request) -> web.Response:
        guild_id_raw = request.query.get("guild_id")
        if not guild_id_raw:
            return web.json_response({"error": "guild_id required"}, status=400)
        try:
            guild_id = int(guild_id_raw)
        except ValueError:
            return web.json_response({"error": "invalid guild_id"}, status=400)
        state = self.queue._states.get(guild_id)  # 내부 접근 — 데모용
        if not state:
            return web.json_response({"guild_id": guild_id, "queue": 0, "playing": False})
        return web.json_response({
            "guild_id": guild_id,
            "queue": len(state.pending),
            "playing": state.is_playing,
            "current": state.current_item.text if state.current_item else None,
        })

    # ── lifecycle ──────────────────────────────────────────────────────────
    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get ("/",             self._index)
        app.router.add_get ("/api/health",   self._health)
        app.router.add_post("/api/say",      self._say)
        app.router.add_post("/api/register", self._register)
        app.router.add_get ("/api/status",   self._status)
        app.router.add_get ("/api/tier3/jobs", self._tier3_jobs)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self._build_app())
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("HTTP bridge listening on http://%s:%d", self.host, self.port)
        print(f"HTTP bridge → http://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

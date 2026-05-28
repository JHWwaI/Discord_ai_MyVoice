"""
Tier 1·2·3 음성 등록 슬래시 커맨드.

UX 흐름:
  /voice register tier:1        → 6초 WAV 1개 첨부 (Instant)
  /voice register tier:2        → 5~15개 WAV 첨부 (Enhanced)
  /voice register tier:3        → 100~400개 WAV 첨부 (Pro · fine-tune 신청)
  /voice tier_status            → 현재 등록된 tier + Tier 3 학습 진행 상황
  /voice tier_reset             → Tier 1로 되돌리기 (refs 비움)

WAV 첨부는 Discord 메시지 attachments로 받는다. 슬래시 커맨드의 attachment 옵션을
여러 개 받을 수 없으므로, 등록 모드에 들어간 후 N초 동안 다음 메시지를 기다리는 방식.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config import (
    TIER2_MAX_REFS, TIER2_MIN_REFS,
    TIER3_MAX_WAVS, TIER3_MIN_WAVS,
    VOICE_DATA_DIR,
)
from services.tier3_repo import Tier3Repository
from services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)

_WAIT_SECONDS = 120  # 사용자가 메시지에 WAV 올릴 때까지 기다리는 시간


def _user_dir(user_id: int, tier: int) -> Path:
    p = Path(VOICE_DATA_DIR) / f"user_{user_id}" / f"tier{tier}"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _download(att: discord.Attachment, dst: Path) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(att.url) as resp:
                resp.raise_for_status()
                data = await resp.read()
        dst.write_bytes(data)
        return True
    except Exception as e:
        logger.warning("download fail %s: %s", att.filename, e)
        return False


class TierCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: UserSettingsService) -> None:
        self.bot = bot
        self.settings = settings
        self.tier3 = Tier3Repository()

    voice_group = app_commands.Group(name="register", description="Tier별 음성 등록")

    # ── /register tier:N ────────────────────────────────────────────────────
    @voice_group.command(name="voice", description="Tier 1/2/3 음성 등록을 시작합니다")
    @app_commands.describe(tier="등록 등급을 선택하세요")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Tier 1 — Instant (6초 1개)",      value=1),
        app_commands.Choice(name="Tier 2 — Enhanced (5~15개)",       value=2),
        app_commands.Choice(name="Tier 3 — Pro (100~400개 · 학습)", value=3),
    ])
    async def register(
        self, interaction: discord.Interaction,
        tier: app_commands.Choice[int],
    ) -> None:
        t = tier.value
        if t == 1:
            min_n, max_n, kind = 1, 1, "Tier 1 Instant"
        elif t == 2:
            min_n, max_n, kind = TIER2_MIN_REFS, TIER2_MAX_REFS, "Tier 2 Enhanced"
        else:
            min_n, max_n, kind = TIER3_MIN_WAVS, TIER3_MAX_WAVS, "Tier 3 Pro"

        await interaction.response.send_message(
            f"**{kind}** 등록을 시작합니다.\n"
            f"이 채널에 WAV 파일 **{min_n}~{max_n}개**를 메시지로 첨부해 주세요.\n"
            f"여러 메시지에 나눠 올려도 됩니다. **{_WAIT_SECONDS}초** 내에 완료해야 합니다.\n"
            "마지막에 메시지 본문에 **`done`** 을 보내면 등록이 마감됩니다.",
            ephemeral=True,
        )

        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else 0
        channel = interaction.channel

        collected: list[Path] = []
        dst_dir = _user_dir(user_id, t)
        # Tier 등록 시 이전 파일은 비움
        for old in dst_dir.glob("*.wav"):
            old.unlink(missing_ok=True)

        def check(msg: discord.Message) -> bool:
            return msg.author.id == user_id and msg.channel.id == channel.id

        deadline_done = False
        async def wait_loop():
            nonlocal deadline_done
            try:
                while True:
                    msg: discord.Message = await self.bot.wait_for(
                        "message", check=check, timeout=_WAIT_SECONDS,
                    )
                    if msg.content.strip().lower() == "done":
                        deadline_done = True
                        return
                    for att in msg.attachments:
                        if not att.filename.lower().endswith(".wav"):
                            continue
                        if len(collected) >= max_n:
                            await msg.reply(f"최대 {max_n}개까지만 받습니다. `done` 으로 마감하세요.")
                            return
                        dst = dst_dir / f"{len(collected)+1:03d}_{uuid.uuid4().hex[:6]}.wav"
                        if await _download(att, dst):
                            collected.append(dst)
                    if collected:
                        await msg.add_reaction("✅")
            except asyncio.TimeoutError:
                return

        await wait_loop()

        # 결과 처리
        if len(collected) < min_n:
            await interaction.followup.send(
                f"등록 실패 — 받은 WAV {len(collected)}개 (최소 {min_n}개 필요)",
                ephemeral=True,
            )
            return

        if t in (1, 2):
            self.settings.set_tier(
                user_id, guild_id, tier=t, refs=[str(p.resolve()) for p in collected],
            )
            await interaction.followup.send(
                f"✅ **{kind}** 등록 완료 — {len(collected)}개 WAV 저장. "
                f"`/say` 로 사용하세요.",
                ephemeral=True,
            )
            return

        # Tier 3 — 학습 큐 신청
        job_id = self.tier3.submit(
            user_id=user_id, guild_id=guild_id,
            wav_dir=str(dst_dir.resolve()), wav_count=len(collected),
        )
        self.settings.upsert(
            user_id, guild_id, tier=3, tier3_status="queued",
            refs=[str(p.resolve()) for p in collected],
        )
        await interaction.followup.send(
            f"📝 **Tier 3 Pro** 신청 완료 — Job #{job_id} ({len(collected)}개 WAV)\n"
            f"학습은 백그라운드에서 진행됩니다. `/voice tier_status` 로 확인.\n"
            f"완료까지 약 2~4시간 예상.",
            ephemeral=True,
        )

    # ── /voice tier_status ─────────────────────────────────────────────────
    @app_commands.command(name="tier_status", description="현재 음성 등록 등급과 상태를 확인합니다")
    async def tier_status(self, interaction: discord.Interaction) -> None:
        s = self.settings.get(interaction.user.id, interaction.guild.id)
        lines = [
            f"**현재 등급**: Tier {s.tier}",
            f"**참조 파일**: {len(s.refs)}개",
            f"**Cloned 사용**: {'on' if s.use_cloned_voice else 'off'}",
        ]
        if s.tier == 3:
            job = self.tier3.latest_for(interaction.user.id, interaction.guild.id)
            if job:
                lines.append("")
                lines.append(f"**Tier 3 Job #{job.job_id}**")
                lines.append(f"- 상태: `{job.status}`")
                lines.append(f"- WAV: {job.wav_count}개")
                lines.append(f"- 제출: {job.submitted_at}")
                if job.completed_at:
                    lines.append(f"- 완료: {job.completed_at}")
                if job.error:
                    lines.append(f"- 에러: {job.error}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ── /voice tier_reset ──────────────────────────────────────────────────
    @app_commands.command(name="tier_reset", description="음성 등록을 초기화합니다 (Tier 1로)")
    async def tier_reset(self, interaction: discord.Interaction) -> None:
        self.settings.upsert(
            interaction.user.id, interaction.guild.id,
            tier=1, refs=[], ckpt_path=None, tier3_status=None, use_cloned_voice=False,
        )
        await interaction.response.send_message("등록이 초기화됐습니다 (Tier 1).", ephemeral=True)


async def setup(bot: commands.Bot, settings: UserSettingsService) -> None:
    await bot.add_cog(TierCommands(bot, settings))

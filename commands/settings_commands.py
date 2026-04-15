import discord
from discord import app_commands
from discord.ext import commands

from config import TTS_SPEED_DEFAULT, TTS_VOICE_DEFAULT
from services.user_settings_service import UserSettingsService

VOICE_CHOICES = [
    app_commands.Choice(name="선희 — 여성 (기본)", value="ko-KR-SunHiNeural"),
    app_commands.Choice(name="인준 — 남성",        value="ko-KR-InJoonNeural"),
    app_commands.Choice(name="현수 — 남성2",       value="ko-KR-HyunsuNeural"),
]

SPEED_CHOICES = [
    app_commands.Choice(name="느리게  (-25%)",      value="-25%"),
    app_commands.Choice(name="보통    (+0%, 기본)", value="+0%"),
    app_commands.Choice(name="빠르게  (+25%)",      value="+25%"),
    app_commands.Choice(name="매우 빠르게 (+50%)",  value="+50%"),
]

_VOICE_LABEL = {c.value: c.name for c in VOICE_CHOICES}
_SPEED_LABEL = {c.value: c.name for c in SPEED_CHOICES}


class SettingsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, settings: UserSettingsService) -> None:
        self.bot = bot
        self.settings = settings

    voice_group = app_commands.Group(name="voice", description="TTS 음성 설정을 관리합니다")

    # ── /voice set ─────────────────────────────────────────────────────────────

    @voice_group.command(name="set", description="TTS 음성을 변경합니다")
    @app_commands.describe(voice="사용할 음성을 선택하세요")
    @app_commands.choices(voice=VOICE_CHOICES)
    async def voice_set(
        self, interaction: discord.Interaction, voice: app_commands.Choice[str]
    ) -> None:
        self.settings.upsert(interaction.user.id, interaction.guild.id, voice=voice.value)
        await interaction.response.send_message(
            f"음성이 **{voice.name}**으로 변경됐습니다.", ephemeral=True
        )

    # ── /voice speed ───────────────────────────────────────────────────────────

    @voice_group.command(name="speed", description="TTS 속도를 변경합니다")
    @app_commands.describe(speed="재생 속도를 선택하세요")
    @app_commands.choices(speed=SPEED_CHOICES)
    async def voice_speed(
        self, interaction: discord.Interaction, speed: app_commands.Choice[str]
    ) -> None:
        self.settings.upsert(interaction.user.id, interaction.guild.id, speed=speed.value)
        await interaction.response.send_message(
            f"속도가 **{speed.name}**으로 변경됐습니다.", ephemeral=True
        )

    # ── /voice show ────────────────────────────────────────────────────────────

    @voice_group.command(name="show", description="현재 음성 설정을 확인합니다")
    async def voice_show(self, interaction: discord.Interaction) -> None:
        s = self.settings.get(interaction.user.id, interaction.guild.id)
        voice_label = _VOICE_LABEL.get(s.voice, s.voice)
        speed_label = _SPEED_LABEL.get(s.speed, s.speed)
        await interaction.response.send_message(
            f"**현재 설정**\n> 음성: {voice_label}\n> 속도: {speed_label}",
            ephemeral=True,
        )

    # ── /voice clone ───────────────────────────────────────────────────────────

    @voice_group.command(name="clone", description="개인 음성 클로닝 on/off")
    @app_commands.describe(enabled="켜기/끄기")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="켜기", value=1),
        app_commands.Choice(name="끄기", value=0),
    ])
    async def voice_clone(
        self, interaction: discord.Interaction, enabled: app_commands.Choice[int]
    ) -> None:
        self.settings.upsert(
            interaction.user.id,
            interaction.guild.id,
            use_cloned_voice=bool(enabled.value),
        )
        state = "활성화" if enabled.value else "비활성화"
        await interaction.response.send_message(
            f"개인 음성 클로닝이 **{state}**됐습니다.", ephemeral=True
        )

    # ── /voice reset ───────────────────────────────────────────────────────────

    @voice_group.command(name="reset", description="음성 설정을 기본값으로 초기화합니다")
    async def voice_reset(self, interaction: discord.Interaction) -> None:
        self.settings.upsert(
            interaction.user.id,
            interaction.guild.id,
            voice=TTS_VOICE_DEFAULT,
            speed=TTS_SPEED_DEFAULT,
            use_cloned_voice=False,
        )
        await interaction.response.send_message(
            "설정이 기본값으로 초기화됐습니다.", ephemeral=True
        )

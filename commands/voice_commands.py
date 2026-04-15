import discord
from discord import app_commands
from discord.ext import commands

from models.queue_item import QueueItem
from services.queue_manager import QueueManager

MAX_TEXT_LENGTH = 200


class VoiceCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, queue_manager: QueueManager) -> None:
        self.bot = bot
        self.queue_manager = queue_manager

    @app_commands.command(name="join", description="봇을 내 음성 채널에 입장시킵니다")
    async def join(self, interaction: discord.Interaction) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "먼저 음성 채널에 입장해주세요.", ephemeral=True
            )
            return

        target = interaction.user.voice.channel
        vc = interaction.guild.voice_client

        if vc and vc.channel == target:
            await interaction.response.send_message(
                f"이미 **{target.name}**에 있습니다.", ephemeral=True
            )
            return

        if vc and vc.is_connected():
            await vc.move_to(target)
            self.queue_manager.start_idle_timer(interaction.guild)
            await interaction.response.send_message(f"**{target.name}**으로 이동했습니다.")
            return

        await target.connect()
        self.queue_manager.start_idle_timer(interaction.guild)
        await interaction.response.send_message(f"**{target.name}**에 입장했습니다.")

    @app_commands.command(name="leave", description="봇을 음성 채널에서 퇴장시킵니다")
    async def leave(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message(
                "봇이 음성 채널에 없습니다.", ephemeral=True
            )
            return

        # idle 타이머 취소 먼저 — disconnect 후 타이머가 깨어나는 것을 방지
        self.queue_manager.cancel_idle(interaction.guild.id)
        self.queue_manager.stop(interaction.guild)
        name = vc.channel.name
        await vc.disconnect()
        await interaction.response.send_message(f"**{name}**에서 퇴장했습니다.")

    @app_commands.command(name="say", description="텍스트를 음성으로 변환해 재생합니다")
    @app_commands.describe(text="읽어줄 텍스트")
    async def say(self, interaction: discord.Interaction, text: str) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "먼저 음성 채널에 입장해주세요.", ephemeral=True
            )
            return

        if len(text) > MAX_TEXT_LENGTH:
            await interaction.response.send_message(
                f"텍스트가 너무 깁니다. {MAX_TEXT_LENGTH}자 이하로 입력해주세요. "
                f"(현재 {len(text)}자)",
                ephemeral=True,
            )
            return

        item = QueueItem(
            text=text,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            guild_id=interaction.guild.id,
            channel=interaction.user.voice.channel,
        )
        started_immediately, position = await self.queue_manager.enqueue(
            interaction.guild, item
        )

        if started_immediately:
            await interaction.response.send_message(
                f"**{interaction.user.display_name}**: {text}"
            )
        else:
            await interaction.response.send_message(
                f"대기열 **{position}번째** 추가: {text}", ephemeral=True
            )

    @app_commands.command(name="stop", description="재생을 중단하고 대기열을 비웁니다")
    async def stop(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            await interaction.response.send_message(
                "봇이 음성 채널에 없습니다.", ephemeral=True
            )
            return

        self.queue_manager.stop(interaction.guild)
        await interaction.response.send_message("재생을 중단하고 대기열을 비웠습니다.")

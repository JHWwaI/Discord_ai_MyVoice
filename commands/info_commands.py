import discord
from discord import app_commands
from discord.ext import commands

from services.log_service import LogService
from services.queue_manager import QueueManager

HISTORY_LIMIT = 10


class InfoCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, queue_manager: QueueManager, log: LogService) -> None:
        self.bot = bot
        self.queue_manager = queue_manager
        self._log = log

    @app_commands.command(name="ping", description="봇 상태 확인")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"pong! ({latency}ms)")

    @app_commands.command(name="queue", description="현재 재생 대기열을 확인합니다")
    async def queue_status(self, interaction: discord.Interaction) -> None:
        current, pending = self.queue_manager.get_status(interaction.guild.id)

        if current is None and not pending:
            await interaction.response.send_message("현재 대기열이 비어있습니다.")
            return

        lines: list[str] = []
        if current:
            lines.append(f"▶ **재생 중** [{current.user_name}]: {current.text}")
        for i, item in enumerate(pending, 1):
            lines.append(f"{i}. [{item.user_name}]: {item.text}")

        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="history", description="내 최근 재생 기록을 확인합니다")
    async def history(self, interaction: discord.Interaction) -> None:
        rows = self._log.get_recent(interaction.user.id, interaction.guild.id, HISTORY_LIMIT)
        if not rows:
            await interaction.response.send_message("재생 기록이 없습니다.", ephemeral=True)
            return

        lines = [f"**최근 재생 기록 ({len(rows)}개)**"]
        for i, row in enumerate(rows, 1):
            lines.append(f"{i}. `{row['played_at']}` [{row['voice']}] {row['text']}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

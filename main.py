import asyncio
import logging
import os

import discord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
from discord.ext import commands

from commands.info_commands import InfoCommands
from commands.settings_commands import SettingsCommands
from commands.voice_commands import VoiceCommands
from config import DISCORD_BOT_TOKEN, TEMP_DIR
from db.database import init_db
from services.log_service import LogService
from services.playback_service import PlaybackService
from services.queue_manager import QueueManager
from services.user_settings_service import UserSettingsService
from services.voice_router import VoiceRouter

os.makedirs(TEMP_DIR, exist_ok=True)
init_db()

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# Dependency injection
_settings_service = UserSettingsService()
_playback_service = PlaybackService()
_voice_router = VoiceRouter()
_log_service = LogService()
_queue_manager = QueueManager(_playback_service, _voice_router, _settings_service, _log_service)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Slash commands synced.")


async def main() -> None:
    async with bot:
        await bot.add_cog(VoiceCommands(bot, _queue_manager))
        await bot.add_cog(InfoCommands(bot, _queue_manager, _log_service))
        await bot.add_cog(SettingsCommands(bot, _settings_service))
        await bot.start(DISCORD_BOT_TOKEN)


asyncio.run(main())

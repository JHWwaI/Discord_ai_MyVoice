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
from commands.tier_commands import TierCommands
from commands.voice_commands import VoiceCommands
from config import TEMP_DIR, require_discord_token, require_ffmpeg
from db.database import init_db
from services.http_bridge import HttpBridge
from services.log_service import LogService
from services.playback_service import PlaybackService
from services.queue_manager import QueueManager
from services.user_settings_service import UserSettingsService
from services.voice_router import VoiceRouter

os.makedirs(TEMP_DIR, exist_ok=True)
init_db()
require_ffmpeg()

intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# ── Dependency injection ──
_settings_service = UserSettingsService()
_playback_service = PlaybackService()
_voice_router = VoiceRouter()
_log_service = LogService()
_queue_manager = QueueManager(_playback_service, _voice_router, _settings_service, _log_service)

# HTTP 브릿지 (외부 서비스 → 봇)
_http_bridge = HttpBridge(
    bot=bot, queue=_queue_manager, settings=_settings_service,
    host=os.getenv("HTTP_BRIDGE_HOST", "0.0.0.0"),
    port=int(os.getenv("HTTP_BRIDGE_PORT", "8090")),
)


@bot.event
async def on_ready() -> None:
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Slash commands synced.")
    # HTTP 브릿지는 봇 준비 후 시작
    await _http_bridge.start()


async def main() -> None:
    async with bot:
        await bot.add_cog(VoiceCommands(bot, _queue_manager))
        await bot.add_cog(InfoCommands(bot, _queue_manager, _log_service))
        await bot.add_cog(SettingsCommands(bot, _settings_service))
        await bot.add_cog(TierCommands(bot, _settings_service))
        try:
            await bot.start(require_discord_token())
        finally:
            await _http_bridge.stop()


asyncio.run(main())

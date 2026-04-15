from dataclasses import dataclass

import discord


@dataclass
class QueueItem:
    text: str
    user_id: int
    user_name: str
    guild_id: int
    channel: discord.VoiceChannel

import asyncio

import discord

from config import FFMPEG_PATH


class PlaybackService:
    """Discord 음성 채널 연결 및 오디오 재생을 담당한다."""

    async def ensure_connected(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel,
    ) -> discord.VoiceClient:
        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            return await channel.connect()
        if vc.channel != channel:
            await vc.move_to(channel)
        return vc

    async def play(self, vc: discord.VoiceClient, file_path: str) -> None:
        """재생이 완전히 끝날 때까지 대기한다."""
        loop = asyncio.get_running_loop()
        done_event = asyncio.Event()

        def after_play(error):
            if error:
                print(f"[재생 오류] {error}")
            loop.call_soon_threadsafe(done_event.set)

        source = discord.FFmpegPCMAudio(file_path, executable=FFMPEG_PATH)
        vc.play(source, after=after_play)
        await done_event.wait()

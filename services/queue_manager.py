import asyncio
import logging
import os
import uuid

import discord

from config import IDLE_TIMEOUT, TEMP_DIR
from models.queue_item import QueueItem
from services.log_service import LogService
from services.playback_service import PlaybackService
from services.user_settings_service import UserSettingsService
from services.voice_router import VoiceRouter

logger = logging.getLogger(__name__)


class GuildState:
    __slots__ = ("queue", "pending", "is_playing", "current_item", "worker_task", "idle_task")

    def __init__(self) -> None:
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.pending: list[QueueItem] = []          # get_status용 — _queue private 접근 대체
        self.is_playing: bool = False
        self.current_item: QueueItem | None = None
        self.worker_task: asyncio.Task | None = None
        self.idle_task: asyncio.Task | None = None


class QueueManager:
    """
    길드별 재생 큐 + idle timeout 관리.

    흐름:
      enqueue  → idle_task 취소 → worker 시작
      worker 종료 → idle_task 시작 (IDLE_TIMEOUT 초 후 자동 퇴장)
      새 /say  → idle_task 취소 → worker 재시작
    """

    def __init__(
        self,
        playback: PlaybackService,
        router: VoiceRouter,
        settings: UserSettingsService,
        log: LogService,
    ) -> None:
        self._states: dict[int, GuildState] = {}
        self._playback = playback
        self._router = router
        self._settings = settings
        self._log = log

    def _get_state(self, guild_id: int) -> GuildState:
        if guild_id not in self._states:
            self._states[guild_id] = GuildState()
        return self._states[guild_id]

    # ── 공개 API ───────────────────────────────────────────────────────────────

    async def enqueue(
        self, guild: discord.Guild, item: QueueItem
    ) -> tuple[bool, int]:
        """큐에 추가. Returns: (바로_재생_여부, 대기열_순번)"""
        state = self._get_state(guild.id)
        self._cancel_idle(state)

        started_immediately = state.queue.empty() and not state.is_playing
        await state.queue.put(item)
        state.pending.append(item)
        position = len(state.pending)

        if state.worker_task is None or state.worker_task.done():
            state.worker_task = asyncio.create_task(self._worker(guild, state))

        return started_immediately, position

    def stop(self, guild: discord.Guild) -> None:
        """재생 중단 + 큐 비우기. idle 타이머는 건드리지 않는다."""
        state = self._states.get(guild.id)
        if not state:
            return
        state.queue = asyncio.Queue()
        state.pending.clear()
        vc = guild.voice_client
        if vc and vc.is_playing():
            vc.stop()

    def cancel_idle(self, guild_id: int) -> None:
        """/leave 전에 호출 — idle 타이머만 취소한다."""
        state = self._states.get(guild_id)
        if state:
            self._cancel_idle(state)

    def start_idle_timer(self, guild: discord.Guild) -> None:
        """/join 직후처럼 재생 없이 봇이 채널에 입장했을 때 타이머를 시작한다."""
        state = self._get_state(guild.id)
        if not state.is_playing and state.queue.empty():
            self._schedule_idle(guild, state)

    def get_status(
        self, guild_id: int
    ) -> tuple[QueueItem | None, list[QueueItem]]:
        state = self._states.get(guild_id)
        if not state:
            return None, []
        return state.current_item, list(state.pending)

    # ── 내부 구현 ──────────────────────────────────────────────────────────────

    async def _worker(self, guild: discord.Guild, state: GuildState) -> None:
        while not state.queue.empty():
            item = await state.queue.get()
            # pending의 맨 앞이 현재 처리할 항목
            if state.pending:
                state.pending.pop(0)
            state.current_item = item
            state.is_playing = True
            file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.mp3")

            try:
                settings = self._settings.get(item.user_id, item.guild_id)
                await self._router.synthesize(item.text, settings, file_path)
                vc = await self._playback.ensure_connected(guild, item.channel)
                await self._playback.play(vc, file_path)
                self._log.record(item.user_id, item.guild_id, item.text, settings.voice)
            except Exception:
                logger.exception("[%s] 재생 중 오류 발생 — text=%r", guild.name, item.text)
            finally:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                state.is_playing = False
                state.current_item = None

        # 큐 소진 → idle 타이머 시작
        self._schedule_idle(guild, state)

    def _schedule_idle(self, guild: discord.Guild, state: GuildState) -> None:
        self._cancel_idle(state)
        state.idle_task = asyncio.create_task(self._idle_watcher(guild, state))

    def _cancel_idle(self, state: GuildState) -> None:
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
            state.idle_task = None

    async def _idle_watcher(self, guild: discord.Guild, state: GuildState) -> None:
        try:
            await asyncio.sleep(IDLE_TIMEOUT)
        except asyncio.CancelledError:
            return

        if state.is_playing or not state.queue.empty():
            return

        vc = guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            logger.info("[%s] %d초 유휴 — 자동 퇴장", guild.name, IDLE_TIMEOUT)

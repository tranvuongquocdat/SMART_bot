"""Hàng đợi agent-run theo hội thoại: tuần tự, hủy được.

Mỗi hội thoại (key) là một chuỗi task nối đuôi nhau — tin nhắn gửi liên tục
được xử lý lần lượt thay vì chạy chồng (hai reply chen nhau), và toàn bộ
chuỗi hủy được giữa chừng (nút Stop trên web chat).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable

log = logging.getLogger(__name__)


class ChatRunRegistry:
    def __init__(self):
        self._tail: dict[str, asyncio.Task] = {}
        self._active: dict[str, set[asyncio.Task]] = defaultdict(set)

    def submit(self, key: str, coro: Awaitable[None]) -> asyncio.Task:
        """Xếp coro vào chuỗi của key; chạy khi các lượt trước xong/hủy."""
        prev = self._tail.get(key)

        async def _run():
            if prev is not None and not prev.done():
                # wait() không raise khi prev bị hủy/lỗi — chỉ chờ nó kết thúc.
                await asyncio.wait({prev})
            await coro

        task = asyncio.create_task(_run(), name=f"chat-run:{key}")
        self._tail[key] = task
        self._active[key].add(task)

        def _done(t: asyncio.Task):
            self._active[key].discard(t)
            if not self._active[key]:
                del self._active[key]
            if self._tail.get(key) is t:
                del self._tail[key]
            if not t.cancelled() and t.exception():
                log.exception("chat run failed key=%s", key, exc_info=t.exception())

        task.add_done_callback(_done)
        return task

    def cancel(self, key: str) -> int:
        """Hủy mọi lượt đang chạy/đang chờ của key. Trả về số task bị hủy."""
        tasks = list(self._active.get(key, ()))
        for t in tasks:
            t.cancel()
        return len(tasks)

    def running(self, key: str) -> bool:
        return bool(self._active.get(key))

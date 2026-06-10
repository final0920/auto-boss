"""inbox_watcher — HR 消息巡检骨架（M1 精简）。

BackendManager / VLM / vision 降级路径已删除（M1）。
巡检方法体待 M4/D0 rid 采样后接 BossDriver.open_message_tab/scrape_conversations 实现。
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class InboxWatcher:
    """HR 消息巡检器骨架。run/stop 结构保留供 M4 接入。"""

    def __init__(self) -> None:
        self._running = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """巡检主循环骨架。"""
        self._running = True
        logger.info("inbox_watcher: 启动（骨架，M4 前无实际巡检）")
        while self._running:
            await self._poll_once()
            await asyncio.sleep(60.0)
        logger.info("inbox_watcher: 已停止")

    async def _poll_once(self) -> list:
        # TODO(M4/D0 rid 采样后接 BossDriver.open_message_tab/scrape_conversations)
        return []

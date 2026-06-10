"""APScheduler 管理（M1 精简后骨架）。

_dispatcher_job / _inbox_watcher_job 已删除（M1）。
runner 常驻循环将在 M3 由 lifespan 直接 create_task 驱动，不经调度器。
# TODO(M3 runner): 若仍需定时任务，在此补充；否则本模块可进一步缩减。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return scheduler


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册调度任务（当前为空，M3 后按需补充）。"""
    logger.info("APScheduler: 无调度任务注册（M1 后骨架）")

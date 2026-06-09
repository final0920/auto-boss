"""APScheduler 管理：巡检/夜停/限速窗口定时任务。

调度器实例作为 app.state.scheduler 挂载。
lifespan 负责 start/shutdown。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    return scheduler


async def _inbox_watcher_job() -> None:
    """定时巡检任务：调用 inbox_watcher 执行一轮巡检。"""
    from app.automation.device_mode import device_mode_manager

    if not device_mode_manager.is_inbox_active():
        logger.debug("inbox_watcher_job: 已跳过（当前模式=%s）", device_mode_manager.mode.value)
        return

    try:
        from app.automation.inbox_watcher import run_inbox_check  # 惰性导入
        await run_inbox_check()
    except ImportError:
        logger.debug("inbox_watcher 尚未实现，跳过")
    except Exception as exc:
        logger.exception("inbox_watcher_job error: %s", exc)


async def _dispatcher_job() -> None:
    """定时投递任务：执行一轮 dispatch_loop。"""
    from app.automation.device_mode import device_mode_manager

    if device_mode_manager.mode.value != "AUTO":
        logger.debug("dispatcher_job: 已跳过（当前模式=%s）", device_mode_manager.mode.value)
        return

    try:
        from app.pipeline.dispatcher import dispatch_loop
        stats = await dispatch_loop()
        logger.info("dispatcher_job 完成: %s", stats)
    except Exception as exc:
        logger.exception("dispatcher_job error: %s", exc)


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """注册默认调度任务。"""
    # inbox_watcher：每 inbox_poll_min_sec ~ inbox_poll_max_sec 随机间隔
    # 使用 min 作为基础间隔，抖动在任务内实现
    poll_interval = settings.inbox_poll_min_sec
    scheduler.add_job(
        _inbox_watcher_job,
        trigger=IntervalTrigger(seconds=poll_interval),
        id="inbox_watcher",
        name="HR 收件箱巡检",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # dispatcher：每 5 分钟执行一轮投递
    scheduler.add_job(
        _dispatcher_job,
        trigger=IntervalTrigger(minutes=5),
        id="dispatcher",
        name="投递 dispatcher",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    logger.info(
        "调度任务已注册: inbox_watcher(间隔=%ds), dispatcher(间隔=5min)",
        poll_interval,
    )

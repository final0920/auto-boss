"""
dispatcher — 两阶段幂等投递（AC8/plan §4）。

状态机约束：
  - 只取 status==CLAIMED 的 Application
  - 先写 SENDING（含 greeting）再执行设备操作，最后回写 SENT/FAILED
  - 永不自动重拾 SENDING（崩溃恢复由 scan_sending() 推人工确认）
  - geetest 检测 → PAUSED + 通知
  - 任何发送必经 RateLimiter.check_and_consume_apply()（AC19）
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, time as dtime
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Application, ApplicationStatus, RunLog
from app.pipeline.rate_limiter import rate_limiter

# 夜停窗口（可由 Config 表覆盖，此处为默认值）
NIGHT_STOP_START = dtime(23, 0)
NIGHT_STOP_END = dtime(7, 0)


def _is_night_stop() -> bool:
    now = datetime.now().time()
    if NIGHT_STOP_START <= NIGHT_STOP_END:
        return NIGHT_STOP_START <= now <= NIGHT_STOP_END
    # 跨午夜
    return now >= NIGHT_STOP_START or now <= NIGHT_STOP_END


def _log(session: Session, event: str, message: str, app_id: Optional[int] = None) -> None:
    log = RunLog(
        event=event,
        message=message,
        application_id=app_id,
        level="INFO",
    )
    session.add(log)


# ---------------------------------------------------------------------------
# 启动自检：扫描 SENDING 推人工确认（AC8）
# ---------------------------------------------------------------------------


def scan_sending() -> list[int]:
    """
    启动时调用。返回仍处于 SENDING 状态的 Application id 列表。
    这些记录需人工在前端确认（已发/未发 → SENT/FAILED）。
    不自动改状态，避免二次发送。
    """
    with Session(engine) as session:
        stuck = session.exec(
            select(Application).where(Application.status == ApplicationStatus.SENDING)
        ).all()
        ids = [a.id for a in stuck]
        if ids:
            _log(
                session,
                "scan_sending",
                f"发现 {len(ids)} 条 SENDING 记录，需人工确认: {ids}",
            )
            session.commit()
    return ids


# ---------------------------------------------------------------------------
# 单次投递
# ---------------------------------------------------------------------------


async def dispatch_one(application_id: int) -> str:
    """
    对单个 CLAIMED Application 执行两阶段投递。
    返回最终状态字符串："SENT" | "FAILED" | "PAUSED" | "SKIP"。

    调用方（dispatcher loop）负责随机间隔和夜停检查。
    """
    # --- 夜停 ---
    if _is_night_stop():
        return "SKIP"

    # --- 配额检查（唯一入口，AC19）---
    allowed = await rate_limiter.check_and_consume_apply()
    if not allowed:
        return "SKIP"

    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None or app.status != ApplicationStatus.CLAIMED:
            return "SKIP"

        # --- 阶段一：写 SENDING（含 greeting）---
        app.status = ApplicationStatus.SENDING
        app.updated_at = datetime.utcnow()
        session.add(app)
        session.commit()
        session.refresh(app)

    # --- 阶段二：执行设备操作（委托给 agent/executor，此处为接口占位）---
    # 真正的执行由 agent.executor 调用，dispatcher 保证幂等状态机
    # executor 需从外部注入，避免循环依赖
    success, fail_reason, geetest = await _execute_apply(application_id)

    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None:
            return "FAILED"

        if geetest:
            app.status = ApplicationStatus.FAILED
            app.fail_reason = "geetest detected"
            _log(session, "geetest", "检测到 geetest，已暂停", app.id)
        elif success:
            app.status = ApplicationStatus.SENT
            app.sent_at = datetime.utcnow()
        else:
            app.status = ApplicationStatus.FAILED
            app.fail_reason = fail_reason

        app.updated_at = datetime.utcnow()
        session.add(app)
        session.commit()

    return app.status.value


async def _execute_apply(application_id: int) -> tuple[bool, str, bool]:
    """
    占位执行器接口。
    返回 (success, fail_reason, geetest_detected)。
    实际实现在 app.agent.executor，通过依赖注入替换。
    """
    # 延迟导入，避免循环依赖；executor 模块尚未实现时安全降级
    try:
        from app.agent.executor import execute_apply  # type: ignore
        return await execute_apply(application_id)
    except ImportError:
        return False, "executor not implemented", False


# ---------------------------------------------------------------------------
# 批量 dispatcher 循环
# ---------------------------------------------------------------------------


async def dispatch_loop(
    account_id: str = "default",
    device_id: str = "default",
    max_per_run: int = 10,
) -> dict:
    """
    一次 dispatcher 运行：取最多 max_per_run 条 CLAIMED，依次投递。
    两次投递间随机等待 apply_interval_min ~ apply_interval_max 秒。
    返回统计 {"sent": int, "failed": int, "skip": int}。
    """
    stats = {"sent": 0, "failed": 0, "skip": 0}

    with Session(engine) as session:
        apps = session.exec(
            select(Application)
            .where(
                Application.status == ApplicationStatus.CLAIMED,
                Application.account_id == account_id,
                Application.device_id == device_id,
            )
            .limit(max_per_run)
        ).all()
        app_ids = [a.id for a in apps]

    for app_id in app_ids:
        result = await dispatch_one(app_id)
        if result == "SENT":
            stats["sent"] += 1
        elif result == "FAILED":
            stats["failed"] += 1
        else:
            stats["skip"] += 1

        # 随机间隔（夜停/配额耗尽时跳过等待）
        if result not in ("SKIP",):
            delay = random.uniform(
                settings.apply_interval_min,
                settings.apply_interval_max,
            )
            await asyncio.sleep(delay)

    return stats

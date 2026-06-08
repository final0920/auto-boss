"""
RateLimiter — 配额 + VLM 熔断唯一真相源（AC9/AC13）。

三路 VLM 消费者共享同一 vlm_daily_limit：
  - vision_backend  (投递用，优先级高)
  - planner         (投递用，优先级高)
  - inbox_watcher   (巡检用，优先级低；超额返回 False，退化纯控件树)

持久化到 Quota 表，重启后配额不丢失。
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import Quota

# 投递优先消费者；巡检消费者超额时只返回 False 不抛异常
_INBOX_CONSUMER = "inbox_watcher"
_HIGH_PRIORITY = {"vision_backend", "planner"}

ConsumerType = Literal["vision_backend", "planner", "inbox_watcher"]

# 模块级异步锁，防止并发双写 Quota
_lock = asyncio.Lock()


def _today() -> str:
    return date.today().isoformat()


def _get_or_create_quota(session: Session, day: str) -> Quota:
    stmt = select(Quota).where(Quota.date == day)
    q = session.exec(stmt).first()
    if q is None:
        q = Quota(date=day)
        session.add(q)
        session.commit()
        session.refresh(q)
    return q


# ---------------------------------------------------------------------------
# 同步核心（被异步包装调用）
# ---------------------------------------------------------------------------


def _sync_check_apply(daily_limit: int) -> bool:
    """检查并消耗一次投递配额。返回 False 表示今日已达上限。"""
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        if q.apply_count >= daily_limit:
            return False
        q.apply_count += 1
        session.add(q)
        session.commit()
        return True


def _sync_check_vlm(consumer: ConsumerType, vlm_limit: int) -> bool:
    """检查并消耗一次 VLM 配额。巡检消费者超额时返回 False 而非抛异常。"""
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        if q.vlm_count >= vlm_limit:
            # 巡检超额：退化，不阻塞
            if consumer == _INBOX_CONSUMER:
                return False
            # 投递优先消费者：也返回 False，由调用方决定是否熔断/告警
            return False
        q.vlm_count += 1
        session.add(q)
        session.commit()
        return True


def _sync_get_quota() -> dict:
    day = _today()
    with Session(engine) as session:
        q = _get_or_create_quota(session, day)
        return {
            "date": day,
            "apply_count": q.apply_count,
            "vlm_count": q.vlm_count,
            "daily_apply_limit": settings.daily_apply_limit,
            "vlm_daily_limit": settings.vlm_daily_limit,
        }


# ---------------------------------------------------------------------------
# 公开异步接口
# ---------------------------------------------------------------------------


class RateLimiter:
    """
    全局单例限速器。

    用法：
        from app.pipeline.rate_limiter import rate_limiter
        ok = await rate_limiter.check_and_consume_apply()
        ok = await rate_limiter.check_and_consume_vlm("vision_backend")
    """

    async def check_and_consume_apply(self) -> bool:
        """消耗一次投递配额。超限返回 False。"""
        async with _lock:
            return _sync_check_apply(settings.daily_apply_limit)

    async def check_and_consume_vlm(self, consumer: ConsumerType) -> bool:
        """
        消耗一次 VLM 配额（三路共享）。
        - 投递消费者（vision_backend/planner）：超限返回 False，调用方应告警/熔断。
        - 巡检消费者（inbox_watcher）：超限返回 False，调用方退化为纯控件树。
        """
        async with _lock:
            return _sync_check_vlm(consumer, settings.vlm_daily_limit)

    async def get_quota(self) -> dict:
        """返回今日配额快照（用于前端成本监控/日志）。"""
        async with _lock:
            return _sync_get_quota()

    async def reset_quota_for_test(self) -> None:
        """仅供测试使用：重置今日配额。"""
        day = _today()
        async with _lock:
            with Session(engine) as session:
                stmt = select(Quota).where(Quota.date == day)
                q = session.exec(stmt).first()
                if q:
                    q.apply_count = 0
                    q.vlm_count = 0
                    session.add(q)
                    session.commit()


# 全局单例
rate_limiter = RateLimiter()

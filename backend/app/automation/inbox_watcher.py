"""inbox_watcher — 常驻 HR 消息巡检（AC7 / plan §4 / C4）。

设计约束（勿删）：
  - 强制走 uia_backend 控件树读 HR 消息 + 廉价文本 diff（AC7）。
  - 控件树读不到才有限降级 vision，且降级计入统一 VLM 预算：
      rate_limiter.check_and_consume_vlm('inbox_watcher')
    超额时退化为纯控件树或跳过该轮（不阻塞，巡检优先级低于投递）。
  - MANUAL 模式期间 inbox_watcher 暂停（device_mode_manager.is_inbox_active()）。
  - 不自动回复 HR，只通知（notify_hr_reply）+ 置 Application.taken_over=True。
  - 巡检轮询间隔：inbox_poll_min_sec ~ inbox_poll_max_sec 随机抖动。

巡检目标：Application.status == SENT，且 taken_over == False。
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.automation.device_mode import device_mode_manager
from app.backends.manager import BackendManager
from app.config import settings
from app.db import engine
from app.models import Application, ApplicationStatus, Message, MessageRole, RunLog
from app.notify import notify_hr_reply
from app.pipeline.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 文本 diff：检测新 HR 消息
# ---------------------------------------------------------------------------


def _diff_messages(prev: list[str], curr: list[str]) -> list[str]:
    """返回 curr 中比 prev 多出的文本行（廉价 diff）。"""
    prev_set = set(prev)
    return [t for t in curr if t not in prev_set]


# ---------------------------------------------------------------------------
# 控件树读取 HR 消息
# ---------------------------------------------------------------------------


def _read_hr_messages_uia(mgr: BackendManager) -> list[str]:
    """用 uia_backend 控件树读取聊天页面所有 HR 消息文本（强制路径）。

    返回文本列表；无法读取返回空列表（由上层决定是否降级 vision）。
    """
    try:
        page = mgr.observe()
        texts: list[str] = []
        for node in page.nodes:
            # 过滤 HR 气泡：resource_id 含 "receive" 或 content_desc 含 HR 标记
            rid = node.resource_id.lower()
            if "receive" in rid or "hr_msg" in rid or "message_receive" in rid:
                t = node.text.strip()
                if t:
                    texts.append(t)
        return texts
    except Exception as exc:
        logger.debug("_read_hr_messages_uia error: %s", exc)
        return []


async def _read_hr_messages_vision(mgr: BackendManager) -> list[str]:
    """vision 降级路径：截图 + VLM 提取 HR 消息。

    先消耗 VLM 配额；超额则返回空列表（退化）。
    """
    allowed = await rate_limiter.check_and_consume_vlm("inbox_watcher")
    if not allowed:
        logger.info("inbox_watcher: VLM 配额超额，跳过 vision 降级")
        return []

    try:
        # observe() 在 vision_backend 下会填充 screenshot_png
        page = await asyncio.to_thread(mgr.observe)
        if not page.screenshot_png:
            return []

        from io import BytesIO
        from PIL import Image as PILImage
        from app.llm.client import get_client

        img = PILImage.open(BytesIO(page.screenshot_png))
        client = get_client()
        raw = await asyncio.to_thread(
            client.chat,
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "这是 Boss 直聘聊天界面截图。"
                                "请列出所有 HR 发送的消息文本，每条独占一行。"
                                "只输出消息原文，不要编号或解释。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,"
                                + __import__("base64").b64encode(page.screenshot_png).decode()
                            },
                        },
                    ],
                }
            ],
        )
        return [line.strip() for line in raw.splitlines() if line.strip()]
    except Exception as exc:
        logger.warning("inbox_watcher: vision 降级失败: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 单个 Application 巡检
# ---------------------------------------------------------------------------


async def _check_application(app_id: int, mgr: BackendManager) -> None:
    """巡检单个 SENT Application 的 HR 回复。"""
    with Session(engine) as session:
        app = session.get(Application, app_id)
        if app is None or app.status != ApplicationStatus.SENT or app.taken_over:
            return

        job_title = ""
        company = ""
        device_id = app.device_id
        account_id = app.account_id

        # 读取岗位信息（用于通知）
        from app.models import Job
        job = session.get(Job, app.job_id)
        if job:
            job_title = job.title
            company = job.company

        # 读取已存 HR 消息（作为 diff 基准）
        existing_msgs = session.exec(
            select(Message)
            .where(
                Message.application_id == app_id,
                Message.role == MessageRole.HR,
            )
            .order_by(Message.ts)  # type: ignore[arg-type]
        ).all()
        prev_texts = [m.text for m in existing_msgs]

    # 优先走控件树（强制路径，AC7）
    curr_texts = await asyncio.to_thread(_read_hr_messages_uia, mgr)

    # 控件树为空时才降级 vision
    if not curr_texts:
        logger.debug("inbox_watcher: app_id=%d 控件树为空，尝试 vision 降级", app_id)
        curr_texts = await _read_hr_messages_vision(mgr)

    new_texts = _diff_messages(prev_texts, curr_texts)
    if not new_texts:
        return

    # 有新 HR 消息 → 持久化 + 通知 + 置 taken_over
    logger.info(
        "inbox_watcher: app_id=%d 发现 %d 条新 HR 消息", app_id, len(new_texts)
    )

    with Session(engine) as session:
        app = session.get(Application, app_id)
        if app is None:
            return

        for text in new_texts:
            msg = Message(
                application_id=app_id,
                role=MessageRole.HR,
                text=text,
                ts=datetime.utcnow(),
            )
            session.add(msg)

        # 置 taken_over，等待人工接管（不自动回复，AC7）
        app.taken_over = True
        app.last_poll_at = datetime.utcnow()
        session.add(app)

        log = RunLog(
            level="INFO",
            event="hr_reply",
            message=f"app_id={app_id} 新消息 {len(new_texts)} 条",
            application_id=app_id,
        )
        session.add(log)
        session.commit()

    # 发通知（截断，不含完整 PII，AC18）
    first_msg = new_texts[0] if new_texts else ""
    notify_hr_reply(
        application_id=app_id,
        job_title=job_title,
        company=company,
        message_text=first_msg,
        device_id=device_id,
        account_id=account_id,
    )


# ---------------------------------------------------------------------------
# 巡检主循环
# ---------------------------------------------------------------------------


class InboxWatcher:
    """常驻 HR 消息巡检器。

    用法（main.py lifespan 或 scheduler）：
        watcher = InboxWatcher(backend_manager)
        asyncio.create_task(watcher.run())
        ...
        watcher.stop()
    """

    def __init__(self, backend_manager: BackendManager) -> None:
        self._mgr = backend_manager
        self._running = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """巡检主循环：轮询 SENT Application，检测新 HR 消息。"""
        self._running = True
        logger.info("inbox_watcher: 启动")

        while self._running:
            # MANUAL 模式暂停（AC7 / C3）
            if not device_mode_manager.is_inbox_active():
                logger.debug("inbox_watcher: 当前非 AUTO 模式，暂停本轮")
                await asyncio.sleep(5.0)
                continue

            try:
                await self._poll_once()
            except Exception as exc:
                logger.exception("inbox_watcher: poll_once 异常: %s", exc)

            # 随机间隔（inbox_poll_min_sec ~ inbox_poll_max_sec，AC7）
            delay = random.uniform(
                settings.inbox_poll_min_sec,
                settings.inbox_poll_max_sec,
            )
            logger.debug("inbox_watcher: 下次巡检 %.0fs 后", delay)
            await asyncio.sleep(delay)

        logger.info("inbox_watcher: 已停止")

    async def _poll_once(self) -> None:
        """单次巡检：查询所有 SENT∧¬taken_over 的 Application。"""
        with Session(engine) as session:
            apps = session.exec(
                select(Application).where(
                    Application.status == ApplicationStatus.SENT,
                    Application.taken_over == False,  # noqa: E712
                )
            ).all()
            app_ids = [a.id for a in apps]

        if not app_ids:
            logger.debug("inbox_watcher: 无待巡检 Application")
            return

        logger.debug("inbox_watcher: 巡检 %d 个 Application", len(app_ids))
        for app_id in app_ids:
            # 再次检查模式（长轮询中途可能切 MANUAL）
            if not device_mode_manager.is_inbox_active():
                logger.info("inbox_watcher: 模式切换，中断本轮巡检")
                return
            await _check_application(app_id, self._mgr)

    async def check_once(self, app_id: Optional[int] = None) -> None:
        """手动触发单次巡检（用于 API /inbox/check 端点调用）。

        app_id=None 时巡检全部；否则仅巡检指定 Application。
        """
        if app_id is not None:
            await _check_application(app_id, self._mgr)
        else:
            await self._poll_once()

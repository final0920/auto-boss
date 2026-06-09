"""executor — 执行层，连接 dispatcher 状态机与 planner 单步执行。

架构约束（AC19，勿删）：
  - 任何"发送/投递"动作必须经 dispatcher 状态机 + RateLimiter.check_and_consume_apply()。
  - executor 无直达 adb-send 的旁路：不调用 run_adb / run_adb_global，
    不直接调用 humanized_tap / motionevent 等底层写函数。
  - 所有设备动作委托 BackendManager（planner.execute_step 内调用）。
  - executor 的职责：把 dispatcher 指派的子任务序列按顺序驱动 planner 执行，
    并汇报 (success, fail_reason, geetest_detected) 给 dispatcher。

此模块被 dispatcher._execute_apply() 以延迟 import 调用：
    from app.agent.executor import execute_apply
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.agent.planner import Planner, SubTask
from app.automation.device_mode import device_mode_manager
from app.backends.manager import BackendManager
from app.pipeline.dispatcher import dispatch_one
from app.pipeline.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 子任务序列定义（对应 dispatcher 的"两阶段投递"子任务）
# ---------------------------------------------------------------------------

# 子任务序列：打开岗位详情 → 点击"立即沟通" → 输入招呼语
# dispatcher 已将 Application 置为 SENDING 并写入 greeting，
# executor 只负责执行设备操作，不重复判断是否应投递。
_APPLY_SUBTASKS: list[SubTask] = [
    SubTask(kind="locate_tap",  target="立即沟通按钮",     context="岗位详情页底部操作栏"),
    SubTask(kind="locate_tap",  target="聊天输入框",       context="聊天页面底部"),
    # text 由 execute_apply 运行时填充（greeting 从 Application 读取）
    SubTask(kind="input_text",  target="聊天输入框",       context="聊天页面底部"),
    SubTask(kind="locate_tap",  target="发送按钮",         context="聊天输入框右侧"),
]

# geetest 检测关键字（控件树 / 视觉描述中出现时触发 PAUSED）
_GEETEST_KEYWORDS = frozenset(["验证", "滑动验证", "geetest", "请完成安全验证"])


def _check_geetest(page_state_text: str) -> bool:
    """从页面状态文本中检测 geetest 关键字。"""
    low = page_state_text.lower()
    return any(kw in low for kw in _GEETEST_KEYWORDS)


# ---------------------------------------------------------------------------
# 公开接口：execute_apply
# ---------------------------------------------------------------------------


async def execute_apply(application_id: int) -> tuple[bool, str, bool]:
    """对指定 Application（状态应为 SENDING）执行设备侧投递操作。

    返回 (success, fail_reason, geetest_detected)。
    由 dispatcher._execute_apply() 调用，不直接对外暴露。

    设计约束（AC19）：
      - 此函数通过 check_and_consume_apply() 已在 dispatch_one() 中消耗配额，
        executor 本身不重复消耗，但会断言 rate_limiter 可访问（可测试性）。
      - 设备写操作在 device_mode_manager.auto_write_ctx() 中执行。
      - 不调用任何 adb 底层函数，仅驱动 BackendManager（通过 Planner）。
    """
    from sqlmodel import Session
    from app.db import engine
    from app.models import Application, ApplicationStatus

    # 读取 Application 和 greeting
    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None or app.status != ApplicationStatus.SENDING:
            return False, f"Application {application_id} 状态不符合预期", False
        greeting = app.greeting
        device_id = app.device_id

    # 获取 BackendManager（按 device_id 查找，当前单设备直接取模块级实例）
    mgr = _get_backend_manager(device_id)
    if mgr is None:
        return False, f"未找到设备 {device_id!r} 的 BackendManager", False

    planner = Planner(mgr)

    # 构造运行时子任务序列（input_text 填入 greeting）
    tasks = [
        SubTask(kind="locate_tap", target="立即沟通按钮",  context="岗位详情页底部操作栏"),
        SubTask(kind="locate_tap", target="聊天输入框",    context="聊天页面底部"),
        SubTask(kind="input_text", target="聊天输入框",    text=greeting, context="聊天页面底部"),
        SubTask(kind="locate_tap", target="发送按钮",      context="聊天输入框右侧"),
    ]

    geetest_detected = False
    fail_reason = ""

    for step_idx, task in enumerate(tasks):
        try:
            # 所有设备写操作在 auto_write_ctx 内执行（单写者锁，AC10）
            async with device_mode_manager.auto_write_ctx(timeout=30.0):
                result = await asyncio.to_thread(planner.execute_step, task)

            if not result.success:
                # 执行失败前先检查 geetest
                try:
                    page = await asyncio.to_thread(mgr.observe)
                    state_text = " ".join(
                        n.text + " " + n.content_desc
                        for n in page.nodes
                    )
                    if _check_geetest(state_text):
                        geetest_detected = True
                        fail_reason = "geetest detected"
                        logger.warning(
                            "executor: 检测到 geetest，步骤 %d app_id=%d",
                            step_idx, application_id,
                        )
                        return False, fail_reason, geetest_detected
                except Exception:
                    pass

                fail_reason = result.error or f"第{step_idx}步失败: {task.kind}/{task.target}"
                logger.warning(
                    "executor: 第 %d 步失败 app_id=%d 原因=%r",
                    step_idx, application_id, fail_reason,
                )
                return False, fail_reason, False

            logger.debug(
                "executor: 第 %d 步完成 app_id=%d action=%r",
                step_idx, application_id, result.action_taken,
            )

        except RuntimeError as exc:
            # device_mode 不是 AUTO 或锁超时
            fail_reason = str(exc)
            logger.error("executor: device_mode 错误于第 %d 步: %s", step_idx, exc)
            return False, fail_reason, False
        except Exception as exc:
            fail_reason = f"第{step_idx}步异常: {exc}"
            logger.exception("executor: 第 %d 步发生异常", step_idx)
            return False, fail_reason, False

    return True, "", False


# ---------------------------------------------------------------------------
# BackendManager 注册表（单设备场景直接用模块级实例）
# ---------------------------------------------------------------------------

# 按 device_id 存放 BackendManager 实例
_backend_managers: dict[str, BackendManager] = {}


def register_backend_manager(device_id: str, mgr: BackendManager) -> None:
    """注册设备对应的 BackendManager（main.py 启动时调用）。"""
    _backend_managers[device_id] = mgr
    logger.info("executor: 已注册 BackendManager device_id=%r", device_id)


def _get_backend_manager(device_id: str) -> Optional[BackendManager]:
    """按 device_id 查找 BackendManager；未注册返回 None。"""
    return _backend_managers.get(device_id)

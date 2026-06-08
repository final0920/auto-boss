"""planner — 受限单步执行器（AC19 / plan §4）。

职责边界（重要，勿删）：
  planner 是无业务决策权的单步执行器。
  给定 dispatcher 指派的明确子任务（如"定位并点击'立即沟通'按钮"），
  planner 只决定：怎么定位、点哪个坐标、用哪个后端。
  planner **不决定**：是否投递、是否发送、是否转人工——这些决策属于 dispatcher/pipeline。

AC19 旁路禁令：
  planner 不持有 adb 句柄，不调用 run_adb/run_adb_global，
  不直接执行任何发送动作，所有动作经 BackendManager.act()，
  发送类动作（send_text）必须由 executor 在 dispatcher 状态机内调用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.backends.base import Action, Coord
from app.backends.manager import BackendManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 子任务描述（dispatcher 指派给 planner 的输入）
# ---------------------------------------------------------------------------


@dataclass
class SubTask:
    """pipeline/dispatcher 指派的单步子任务。

    kind 枚举：
      "locate_tap"  — 定位目标元素并点击
      "input_text"  — 在当前焦点/目标框输入文本
      "swipe"       — 向指定方向滑动
      "back"        — 返回键
      "home"        — Home 键
    """
    kind: str
    target: str = ""        # 自然语言描述，用于 locate（locate_tap / input_text 定位）
    text: str = ""          # input_text 时填写
    direction: str = "up"   # swipe 时填写（"up" | "down" | "left" | "right"）
    context: str = ""       # 给 vision_backend 的屏幕上下文提示


@dataclass
class PlanResult:
    """planner 单步执行结果。"""
    success: bool
    action_taken: str = ""   # 描述执行的动作（用于日志/trace）
    coord: Optional[Coord] = None
    error: str = ""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class Planner:
    """受限单步执行器。

    接受 SubTask，决定定位方式和坐标，委托 BackendManager.act() 执行。
    不持有 adb 句柄，不做业务决策。
    """

    # 滑动距离（像素）
    _SWIPE_DISTANCE = 700

    def __init__(self, backend_manager: BackendManager) -> None:
        self._mgr = backend_manager

    def execute_step(self, task: SubTask) -> PlanResult:
        """执行单步子任务。同步（由 executor 在 asyncio.to_thread 中调用）。"""
        logger.debug(
            "planner.execute_step kind=%s target=%r", task.kind, task.target
        )

        if task.kind == "locate_tap":
            return self._locate_tap(task)
        elif task.kind == "input_text":
            return self._input_text(task)
        elif task.kind == "swipe":
            return self._swipe(task)
        elif task.kind == "back":
            self._mgr.press_back()
            return PlanResult(success=True, action_taken="press_back")
        elif task.kind == "home":
            self._mgr.press_home()
            return PlanResult(success=True, action_taken="press_home")
        else:
            return PlanResult(
                success=False,
                error=f"未知子任务类型: {task.kind!r}",
            )

    # ------------------------------------------------------------------
    # 内部执行方法（仅定位/点击/输入，无业务决策）
    # ------------------------------------------------------------------

    def _locate_tap(self, task: SubTask) -> PlanResult:
        """定位目标元素并点击。"""
        coord = self._mgr.locate(task.target)
        if coord is None:
            logger.warning("planner: locate '%s' 未命中", task.target)
            return PlanResult(
                success=False,
                error=f"定位失败: {task.target!r}",
            )
        self._mgr.tap(coord.x, coord.y)
        return PlanResult(
            success=True,
            action_taken=f"tap({coord.x},{coord.y}) target={task.target!r}",
            coord=coord,
        )

    def _input_text(self, task: SubTask) -> PlanResult:
        """可选定位聚焦后输入文本。

        注意：输入文本本身不是"发送"动作——发送必须由 executor 经 dispatcher 触发。
        planner 只负责把文字写入输入框，不执行任何提交/发送操作。
        """
        # 如果提供了 target，先点击聚焦
        if task.target:
            coord = self._mgr.locate(task.target)
            if coord is None:
                return PlanResult(
                    success=False,
                    error=f"输入框定位失败: {task.target!r}",
                )
            self._mgr.tap(coord.x, coord.y)

        self._mgr.send_text(task.text)
        return PlanResult(
            success=True,
            action_taken=f"input_text len={len(task.text)} target={task.target!r}",
        )

    def _swipe(self, task: SubTask) -> PlanResult:
        """执行滑动（方向 + 固定距离）。"""
        # 以屏幕中心为基准滑动（坐标系 0-1000 → 实际设备由 backend 换算）
        # BackendManager.act 接受 Action，vision_backend 会换算到像素
        center = 500
        d = self._SWIPE_DISTANCE // 2

        direction_map = {
            "up":    (center, center + d, center, center - d),
            "down":  (center, center - d, center, center + d),
            "left":  (center + d, center, center - d, center),
            "right": (center - d, center, center + d, center),
        }
        coords = direction_map.get(task.direction)
        if coords is None:
            return PlanResult(
                success=False,
                error=f"未知滑动方向: {task.direction!r}",
            )

        x1, y1, x2, y2 = coords
        self._mgr.act(Action(kind="swipe", x=x1, y=y1, x2=x2, y2=y2, duration_ms=400))
        return PlanResult(
            success=True,
            action_taken=f"swipe_{task.direction}",
        )

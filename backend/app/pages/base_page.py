"""
base_page — 后端无关页面对象基类。

所有页面对象委托当前激活的 ControlBackend 执行定位/操作，
自身不持有 adb 句柄，确保双后端可插拔（plan §4）。

ensure_anchor() 回锚点页（默认：岗位列表页），
dispatcher/agent 释锁前必须调用（plan §4/AC10）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.backends.base import ControlBackend


class BasePage:
    """
    页面对象基类。

    子类实现具体页面的导航/断言逻辑。
    backend 通过构造函数注入，支持运行时热切换。
    """

    # 子类覆盖：页面标识（用于日志/断言）
    PAGE_NAME: str = "base"

    def __init__(self, backend: "ControlBackend") -> None:
        self._backend = backend

    @property
    def backend(self) -> "ControlBackend":
        return self._backend

    @backend.setter
    def backend(self, value: "ControlBackend") -> None:
        """后端热切换入口（切换以页面/动作为原子边界，由调用方保证）。"""
        self._backend = value

    def observe(self) -> dict:
        """抓取当前页面控件树/截图快照。"""
        return self._backend.observe()

    def locate(self, target: str) -> Optional[tuple[int, int]]:
        """定位目标元素，返回像素坐标或 None。"""
        return self._backend.locate(target)

    def act(self, action: dict) -> bool:
        """执行操作（tap/swipe/input），返回是否成功。"""
        return self._backend.act(action)

    # ------------------------------------------------------------------
    # 锚点页回归（plan §4/AC10 要求）
    # ------------------------------------------------------------------

    def ensure_anchor(self) -> bool:
        """
        导航回锚点页（岗位列表页）。
        持锁者（dispatcher/inbox_watcher）释锁前调用。
        子类可覆盖实现具体导航逻辑。
        """
        return True  # 基类无操作，由 ListPage 覆盖


    # ------------------------------------------------------------------
    # 辅助：等待元素出现（轮询 observe）
    # ------------------------------------------------------------------

    def wait_for(self, target: str, max_attempts: int = 5) -> Optional[tuple[int, int]]:
        """轮询定位目标，最多尝试 max_attempts 次。"""
        for _ in range(max_attempts):
            coord = self.locate(target)
            if coord is not None:
                return coord
        return None

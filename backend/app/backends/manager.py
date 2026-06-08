"""BackendManager — 可插拔双后端切换管理器。

切换原子性规则（plan §4 / AC4 / C5 / C7）：
  - 后端切换以页面/动作为原子边界，禁止单次 act() 中途切换后端。
  - 切换为持锁原子序列：回锚点 → 重 observe → 换后端。
  - 手动覆盖（manual_override）优先级高于自动判据，锁定后自动判据不再切。

自动切换判据：
  uia.locate() 返回 None 时，BackendManager 升级到 vision_backend 补充定位。
  也可由外部（probe / 前端设置）强制指定后端。

用法：
    mgr = BackendManager(serial="XXXXXXXX")
    state = mgr.observe()
    coord = mgr.locate("立即沟通按钮")
    mgr.act(Action(kind="tap", x=coord.x, y=coord.y))
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from app.backends.base import Action, ControlBackend, Coord, PageState
from app.backends.uia_backend import UiaBackend
from app.backends.vision_backend import VisionBackend
from app.config import settings
from app.models import BackendType

logger = logging.getLogger(__name__)


class BackendManager:
    """管理 uia / vision 双后端的统一入口。

    - observe / locate / act 对外表现为单一 ControlBackend 接口。
    - locate() 内部实现三级降级：uia → vision（不可中途切）。
    - switch_backend() 持内部锁保证切换原子性。
    """

    def __init__(self, serial: str):
        self.serial = serial
        self._lock = threading.Lock()

        # 实例化两个后端
        self._uia = UiaBackend(serial)
        self._vision = VisionBackend(serial)

        # 当前活跃后端
        _default = settings.default_backend
        self._active: ControlBackend = (
            self._uia if _default == BackendType.UIA else self._vision
        )

        # 手动覆盖锁定（True 时自动判据不切换）
        self._manual_override: bool = False
        self._override_backend: Optional[str] = None  # "uia" | "vision" | None

    # ------------------------------------------------------------------
    # 手动覆盖（前端设置 / 探针结果）
    # ------------------------------------------------------------------

    def set_manual_override(self, backend_name: str) -> None:
        """锁定后端，自动判据不再切换，直到 clear_manual_override()。"""
        with self._lock:
            self._manual_override = True
            self._override_backend = backend_name
            self._active = self._uia if backend_name == "uia" else self._vision
            logger.info("BackendManager 手动覆盖 → %s", backend_name)

    def clear_manual_override(self) -> None:
        """解除手动覆盖，恢复自动判据。"""
        with self._lock:
            self._manual_override = False
            self._override_backend = None
            logger.info("BackendManager 手动覆盖已解除")

    @property
    def active_backend_name(self) -> str:
        return self._active.name

    # ------------------------------------------------------------------
    # 内部切换（原子序列）
    # ------------------------------------------------------------------

    def _switch_to(self, backend: ControlBackend, reason: str = "") -> None:
        """原子切换后端（调用方需持 _lock）。"""
        if self._active.name == backend.name:
            return
        old = self._active.name
        self._active = backend
        logger.info(
            "BackendManager 后端切换 %s → %s%s",
            old, backend.name,
            f" ({reason})" if reason else "",
        )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def observe(self) -> PageState:
        """用当前活跃后端抓取页面状态。"""
        with self._lock:
            return self._active.observe()

    def locate(self, target: str) -> Optional[Coord]:
        """定位目标。

        自动降级流程：
          1. 先用当前活跃后端（默认 uia）locate。
          2. uia 未命中且未手动覆盖 → 升 vision 补充定位。
          3. 手动覆盖模式：只用指定后端，不自动切换。
        """
        with self._lock:
            # 手动覆盖：不自动切换
            if self._manual_override:
                coord = self._active.locate(target)
                if coord is None:
                    logger.info(
                        "BackendManager locate '%s' 手动覆盖后端 %s 未命中",
                        target, self._active.name,
                    )
                return coord

            # 自动模式：uia 优先
            coord = self._uia.locate(target)
            if coord is not None:
                # 确保活跃后端是 uia
                if self._active.name != "uia":
                    self._switch_to(self._uia, "uia 命中，回切")
                return coord

            # uia 未命中 → vision 兜底
            logger.info("BackendManager locate '%s' uia 未命中，升级 vision", target)
            coord = self._vision.locate(target)
            if coord is not None:
                # 记录后端使用情况（不切换 _active，locate 是单步原子）
                logger.debug("BackendManager locate '%s' vision 命中 (%d,%d)", target, coord.x, coord.y)
            else:
                logger.warning("BackendManager locate '%s' uia+vision 均未命中", target)
            return coord

    def act(self, action: Action) -> None:
        """用当前活跃后端执行动作（原子，禁止中途切后端）。

        调用方须在 device_mode_manager.auto_write_ctx() 内调用。
        """
        with self._lock:
            self._active.act(action)

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def tap(self, x: int, y: int) -> None:
        self.act(Action(kind="tap", x=x, y=y))

    def send_text(self, text: str) -> None:
        self.act(Action(kind="text", text=text))

    def press_back(self) -> None:
        self.act(Action(kind="back"))

    def press_home(self) -> None:
        self.act(Action(kind="home"))

    def __repr__(self) -> str:
        return (
            f"BackendManager(serial={self.serial!r}, "
            f"active={self._active.name!r}, "
            f"manual_override={self._manual_override})"
        )

"""
设备模式锁 + 模式互斥（AC10 / C3）

DeviceMode:
  AUTO   — pipeline + inbox_watcher 持锁轮转；手动 /control 与 Terminal 拒绝
  MANUAL — 人工接管；自动化全停（含 inbox_watcher 暂停）；手动 /control / Terminal 放行
  PAUSED — geetest / 登录失效等暂停；自动化停；手动也停

单写者锁规则：
  - AUTO 下：pipeline/inbox_watcher 通过 acquire_auto() 竞争锁；
    每次写操作（单次 act）完成后调用 release_auto() 释放，
    下一个消费者在锁外等待（即 interval 间隔在锁外）。
  - MANUAL 下：持锁者是"人工操控会话"，acquire_manual() 一次取得，
    release_manual() 释放。
  - 切换模式本身由 set_mode() 持 _mode_lock 原子执行。

用法：
    from app.automation.device_mode import device_mode_manager

    # pipeline 写操作
    async with device_mode_manager.auto_write_ctx():
        await executor.act(...)

    # FastAPI 依赖：仅 MANUAL 放行
    from app.automation.device_mode import require_manual
    @router.post("/control/tap")
    async def tap(..., _: None = Depends(require_manual)):
        ...
"""
from __future__ import annotations

import asyncio
import enum
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class DeviceMode(str, enum.Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    PAUSED = "PAUSED"


class DeviceModeManager:
    """Singleton — use the module-level `device_mode_manager` instance."""

    def __init__(self) -> None:
        self._mode: DeviceMode = DeviceMode.AUTO
        # Protects mode transitions
        self._mode_lock = asyncio.Lock()
        # Single-writer lock for AUTO write operations
        self._write_lock = asyncio.Lock()
        # Event broadcast when mode changes (consumers waiting on AUTO lock can check)
        self._mode_changed = asyncio.Event()

    # ------------------------------------------------------------------
    # Mode accessors
    # ------------------------------------------------------------------

    @property
    def mode(self) -> DeviceMode:
        return self._mode

    async def set_mode(self, new_mode: DeviceMode, reason: str = "") -> None:
        """Switch device mode atomically."""
        async with self._mode_lock:
            old = self._mode
            if old == new_mode:
                return
            self._mode = new_mode
            logger.info("DeviceMode %s -> %s%s", old.value, new_mode.value, f" ({reason})" if reason else "")
            # Wake any waiters so they can re-check mode
            self._mode_changed.set()
            self._mode_changed.clear()

    # ------------------------------------------------------------------
    # AUTO single-writer context manager
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def auto_write_ctx(self, timeout: float = 60.0) -> AsyncIterator[None]:
        """Acquire write lock for one AUTO operation.

        Raises RuntimeError if mode is not AUTO when lock is acquired.
        The lock is held only for the duration of one write operation;
        intervals between operations happen outside this context.
        """
        try:
            await asyncio.wait_for(self._write_lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("Timed out waiting for AUTO write lock after %.0fs" % timeout)

        try:
            if self._mode != DeviceMode.AUTO:
                raise RuntimeError(
                    f"Expected AUTO mode but got {self._mode.value}; aborting write operation"
                )
            yield
        finally:
            self._write_lock.release()

    # ------------------------------------------------------------------
    # MANUAL acquire/release (for manual control sessions)
    # ------------------------------------------------------------------

    async def acquire_manual(self, timeout: float = 5.0) -> None:
        """Take the write lock for manual session.

        Waits up to `timeout` seconds for AUTO pipeline to release.
        """
        if self._mode != DeviceMode.MANUAL:
            raise RuntimeError("acquire_manual called but mode is not MANUAL")
        try:
            await asyncio.wait_for(self._write_lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "Timed out acquiring manual write lock; AUTO pipeline may still be running"
            )

    def release_manual(self) -> None:
        if self._write_lock.locked():
            self._write_lock.release()

    # ------------------------------------------------------------------
    # Guard helpers
    # ------------------------------------------------------------------

    def assert_manual(self) -> None:
        """Raise HTTPException 403 if not in MANUAL mode."""
        if self._mode != DeviceMode.MANUAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation only allowed in MANUAL mode (current: {self._mode.value})",
            )

    def assert_auto(self) -> None:
        """Raise RuntimeError if not in AUTO mode."""
        if self._mode != DeviceMode.AUTO:
            raise RuntimeError(
                f"Auto-pipeline operation requires AUTO mode (current: {self._mode.value})"
            )

    def is_inbox_active(self) -> bool:
        """inbox_watcher should run only in AUTO mode (AC7 / C3)."""
        return self._mode == DeviceMode.AUTO


# Module-level singleton
device_mode_manager = DeviceModeManager()


# ---------------------------------------------------------------------------
# FastAPI dependency — rejects non-MANUAL requests
# ---------------------------------------------------------------------------


async def require_manual() -> None:
    """FastAPI dependency: allow only when device is in MANUAL mode.

    Apply to all human-control endpoints: /control/*, /terminal WS.
    """
    device_mode_manager.assert_manual()

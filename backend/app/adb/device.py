"""adb 设备操作原语 — tap/swipe/motionevent/keyevent/monkey。

所有操作走非特权命令，不使用 root/su。
"""

from __future__ import annotations

import time
from typing import Sequence

from app.adb._run import run_adb, AdbResult


class AdbDevice:
    """封装针对单台设备的 adb shell 原语操作。"""

    def __init__(self, serial: str):
        self.serial = serial

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _run(self, args: Sequence[str], *, timeout: float = 30.0, check: bool = True) -> AdbResult:
        return run_adb(self.serial, args, timeout=timeout, check=check)

    def _shell(self, cmd: str, *, timeout: float = 30.0, check: bool = True) -> AdbResult:
        return self._run(["shell", cmd], timeout=timeout, check=check)

    def _shell_su(self, cmd: str, *, timeout: float = 30.0, check: bool = False) -> AdbResult:
        """以 root(su -c)执行。MIUI 禁止普通 adb 的 input 注入(INJECT_EVENTS)，
        设备已 root，注入类命令(input tap/swipe/motionevent/keyevent)走 su 绕过。

        注意：必须把 `su -c '<cmd>'` 作为单个 shell 参数传。Windows adb 对
        ["shell","su","-c",cmd] 多参数形式会拆散，导致 su -c 拿不到完整命令
        （返回码 0 但实际没执行）。cmd 内不含单引号（input/wm/svc 等均满足）。"""
        return self._run(["shell", f"su -c '{cmd}'"], timeout=timeout, check=check)

    # ------------------------------------------------------------------
    # 触摸 / 点击
    # ------------------------------------------------------------------

    def tap(self, x: int, y: int) -> AdbResult:
        """adb shell input tap x y"""
        return self._shell_su(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> AdbResult:
        """adb shell input swipe x1 y1 x2 y2 [duration_ms]"""
        return self._shell_su(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    # ------------------------------------------------------------------
    # motionevent — 更拟人的多点触摸序列（抗检测）
    # 协议：sendevent 走 input keyevent / motionevent 走 exec-out
    # 此处用 adb shell input motionevent DOWN/MOVE/UP
    # ------------------------------------------------------------------

    def motionevent_down(self, x: int, y: int) -> AdbResult:
        return self._shell_su(f"input motionevent DOWN {x} {y}")

    def motionevent_move(self, x: int, y: int) -> AdbResult:
        return self._shell_su(f"input motionevent MOVE {x} {y}")

    def motionevent_up(self, x: int, y: int) -> AdbResult:
        return self._shell_su(f"input motionevent UP {x} {y}")

    def humanized_swipe(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        steps: int = 10,
        step_delay_ms: int = 30,
    ) -> None:
        """分段 MOVE 序列模拟非直线滑动（拟人化）。"""
        self.motionevent_down(x1, y1)
        time.sleep(0.02)
        for i in range(1, steps + 1):
            t = i / steps
            mx = int(x1 + (x2 - x1) * t)
            my = int(y1 + (y2 - y1) * t)
            self.motionevent_move(mx, my)
            time.sleep(step_delay_ms / 1000.0)
        self.motionevent_up(x2, y2)

    # ------------------------------------------------------------------
    # 按键
    # ------------------------------------------------------------------

    def keyevent(self, keycode: int | str) -> AdbResult:
        """adb shell input keyevent <keycode>"""
        return self._shell_su(f"input keyevent {keycode}")

    def press_back(self) -> AdbResult:
        return self.keyevent(4)  # KEYCODE_BACK

    # ------------------------------------------------------------------
    # 应用启动
    # ------------------------------------------------------------------

    def monkey_start(self, package: str) -> AdbResult:
        """用 monkey 启动 App（不依赖 am start 需知 Activity 名称）。"""
        return self._shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
            timeout=15.0,
        )

    def am_force_stop(self, package: str) -> AdbResult:
        return self._shell(f"am force-stop {package}", timeout=10.0)

    # ------------------------------------------------------------------
    # dumpsys
    # ------------------------------------------------------------------

    def dumpsys(self, service: str, *, timeout: float = 10.0) -> AdbResult:
        return self._shell(f"dumpsys {service}", timeout=timeout, check=False)

    def __repr__(self) -> str:
        return f"AdbDevice(serial={self.serial!r})"

"""adb 设备操作原语 — tap/swipe/motionevent/keyevent/monkey。

所有操作走非特权命令，不使用 root/su，中文输入走 ADBKeyboard（inputs.py）。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Sequence

from app.adb._run import run_adb, AdbResult


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class Point:
    x: int
    y: int


@dataclass
class SwipeGesture:
    start: Point
    end: Point
    duration_ms: int = 300  # 默认 300ms，拟人化：调用方可随机化


# ---------------------------------------------------------------------------
# AdbDevice — 绑定 serial 的设备操作句柄
# ---------------------------------------------------------------------------


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

    def swipe_gesture(self, gesture: SwipeGesture) -> AdbResult:
        return self.swipe(
            gesture.start.x, gesture.start.y,
            gesture.end.x, gesture.end.y,
            gesture.duration_ms,
        )

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

    def humanized_tap(self, x: int, y: int, hold_ms: int = 80) -> None:
        """DOWN → 短暂停顿 → UP，比 input tap 更像真实触摸。"""
        self.motionevent_down(x, y)
        time.sleep(hold_ms / 1000.0)
        self.motionevent_up(x, y)

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

    def press_home(self) -> AdbResult:
        return self.keyevent(3)  # KEYCODE_HOME

    def press_enter(self) -> AdbResult:
        return self.keyevent(66)  # KEYCODE_ENTER

    # ------------------------------------------------------------------
    # 应用启动
    # ------------------------------------------------------------------

    def monkey_start(self, package: str) -> AdbResult:
        """用 monkey 启动 App（不依赖 am start 需知 Activity 名称）。"""
        return self._shell(
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
            timeout=15.0,
        )

    def am_start(self, package: str, activity: str) -> AdbResult:
        """am start 指定 Activity。"""
        return self._shell(f"am start -n {package}/{activity}", timeout=15.0)

    def am_force_stop(self, package: str) -> AdbResult:
        return self._shell(f"am force-stop {package}", timeout=10.0)

    # ------------------------------------------------------------------
    # 滚动
    # ------------------------------------------------------------------

    def scroll_down(self, x: int = 540, y_start: int = 1400, y_end: int = 400, duration_ms: int = 400) -> AdbResult:
        return self.swipe(x, y_start, x, y_end, duration_ms)

    def scroll_up(self, x: int = 540, y_start: int = 400, y_end: int = 1400, duration_ms: int = 400) -> AdbResult:
        return self.swipe(x, y_start, x, y_end, duration_ms)

    # ------------------------------------------------------------------
    # dumpsys
    # ------------------------------------------------------------------

    def dumpsys(self, service: str, *, timeout: float = 10.0) -> AdbResult:
        return self._shell(f"dumpsys {service}", timeout=timeout, check=False)

    # ------------------------------------------------------------------
    # 屏幕尺寸（归一化坐标 → 像素换算用）
    # ------------------------------------------------------------------

    def screen_size(self) -> tuple[int, int]:
        """返回当前显示分辨率 (width, height)，优先 Override（用户改过分辨率时）。

        wm size 输出：Physical size: 1440x3200 / Override size: 1080x2400
        """
        r = self._shell("wm size", check=False)
        text = r.stdout or ""
        m = re.search(r"Override size:\s*(\d+)x(\d+)", text) or \
            re.search(r"Physical size:\s*(\d+)x(\d+)", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        return 1080, 2400  # 兜底

    def __repr__(self) -> str:
        return f"AdbDevice(serial={self.serial!r})"

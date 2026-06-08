"""ADBKeyboard 封装 — 中文输入走 am broadcast，不用 input text。

参考 AutoGLM adb/input.py：
  - ime set com.android.adbkeyboard/.AdbIME
  - am broadcast -a ADB_INPUT_B64 --es msg <base64(utf-8)>
  - am broadcast -a ADB_CLEAR_TEXT
  - restore_keyboard：切回原输入法
"""

from __future__ import annotations

import base64
from typing import Optional

from app.adb._run import run_adb, AdbResult


# ADBKeyboard APK 的包名/组件（apk 放 resources/ 目录随后手动安装）
_ADBKEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"
_ACTION_INPUT_B64 = "ADB_INPUT_B64"
_ACTION_CLEAR = "ADB_CLEAR_TEXT"

# 获取当前默认 IME 的 setting 键
_SETTING_DEFAULT_IME = "secure default_input_method"


def _get_current_ime(serial: str) -> str:
    result = run_adb(serial, ["shell", f"settings get {_SETTING_DEFAULT_IME}"], check=False)
    return result.stdout.strip()


def _set_ime(serial: str, ime: str) -> AdbResult:
    return run_adb(serial, ["shell", f"ime set {ime}"])


def _broadcast(serial: str, action: str, extras: Optional[list[str]] = None) -> AdbResult:
    parts = ["shell", "am", "broadcast", "-a", action]
    if extras:
        parts.extend(extras)
    return run_adb(serial, parts)


class ADBKeyboard:
    """通过 ADBKeyboard IME 向设备发送中文/Unicode 文本。

    用法:
        kb = ADBKeyboard(serial)
        kb.activate()
        kb.send_text("你好 Boss")
        kb.restore()
    """

    def __init__(self, serial: str):
        self.serial = serial
        self._original_ime: Optional[str] = None

    def activate(self) -> None:
        """切换到 ADBKeyboard IME，保存原输入法以便恢复。"""
        self._original_ime = _get_current_ime(self.serial)
        _set_ime(self.serial, _ADBKEYBOARD_IME)

    def restore_keyboard(self) -> None:
        """恢复原来的输入法。"""
        if self._original_ime:
            _set_ime(self.serial, self._original_ime)
            self._original_ime = None

    def send_text(self, text: str) -> AdbResult:
        """发送任意 Unicode 文本（含中文）。

        编码为 base64(utf-8) 后通过 am broadcast ADB_INPUT_B64 发送，
        绕过 input text 不支持中文的限制。
        """
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return _broadcast(
            self.serial,
            _ACTION_INPUT_B64,
            ["--es", "msg", b64],
        )

    def clear_text(self) -> AdbResult:
        """清空当前输入框内容（ADB_CLEAR_TEXT broadcast）。"""
        return _broadcast(self.serial, _ACTION_CLEAR)

    # ------------------------------------------------------------------
    # 上下文管理器支持：with ADBKeyboard(serial) as kb: kb.send_text(...)
    # ------------------------------------------------------------------

    def __enter__(self) -> "ADBKeyboard":
        self.activate()
        return self

    def __exit__(self, *_) -> None:
        self.restore_keyboard()

    def __repr__(self) -> str:
        return f"ADBKeyboard(serial={self.serial!r})"


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------


def send_text_once(serial: str, text: str) -> None:
    """临时激活 ADBKeyboard、发送文本、恢复输入法的一次性帮助函数。"""
    kb = ADBKeyboard(serial)
    with kb:
        kb.send_text(text)

"""adb REPL — 纵深防御白名单 + 高危子命令管控。

安全分层说明（重要，勿删）：
  主防线 = localhost-bind + 会话 token + Origin 校验（security/auth.py）。
  此白名单仅作纵深防御附加项，不作为 RCE 防线。
  原因：设备已 root，`adb shell su` = 整机 RCE，"命令名是 adb"提供的
        安全增量约等于 0。白名单的价值是减少误操作和提示意识，而非阻断能力。

高危子命令策略（AC12）：
  `shell su` / `forward` / `reverse` / `install` / `push` / `tcpip`
  → 默认需要二次确认（CONFIRM_REQUIRED），不直接执行。
  前端在收到 {"type":"confirm_required","cmd":...} 后展示确认对话框，
  用户点确认后附带 force=true 重发，服务端检测 force 标志直接执行。

白名单模式（默认启用）：
  仅允许 ALLOWED_CMDS 中列出的 adb 子命令前缀。
  如需关闭白名单（完全透传），设 AdbRepl.whitelist_enabled = False。
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from dataclasses import dataclass
from typing import Optional

from app.adb._run import run_adb, run_adb_global, AdbResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 白名单：允许不经确认直接执行的 adb 子命令前缀（纵深防御，非主防线）
# ---------------------------------------------------------------------------
ALLOWED_CMDS: frozenset[str] = frozenset(
    [
        "devices",
        "shell dumpsys",
        "shell getprop",
        "shell am",          # am start/force-stop 等，不含 su
        "shell pm list",
        "shell wm",
        "shell settings",
        "shell input",       # tap/swipe/keyevent 等（不含 su）
        "shell screencap",
        "shell uiautomator",
        "shell logcat",
        "shell cat /proc",
        "shell cat /sys",
        "bugreport",
        "logcat",
        "version",
        "get-state",
        "get-serialno",
    ]
)

# 高危子命令：默认二次确认（AC12）
# 注：即使这些命令被确认执行，主防线（鉴权）仍生效；此处仅减慢误操作速度
CONFIRM_REQUIRED: frozenset[str] = frozenset(
    [
        "shell su",
        "shell su -c",
        "forward",
        "reverse",
        "install",
        "install-multiple",
        "push",
        "pull",         # 数据外泄风险，也需确认
        "tcpip",
        "usb",          # 切换传输模式
        "root",         # 某些设备支持 adb root
        "remount",
        "reboot",
        "sideload",
        "emu",
    ]
)


@dataclass
class ReplResult:
    """adb REPL 单次执行结果。"""
    output: str
    confirm_required: bool = False
    cmd_blocked: bool = False
    error: Optional[str] = None


class AdbRepl:
    """adb REPL 执行器。

    用法：
        repl = AdbRepl(serial="XXXX")
        result = await repl.execute("shell dumpsys window")
        if result.confirm_required:
            # 前端展示确认对话框
            ...
        else:
            # 直接返回 result.output 给 WebSocket
    """

    def __init__(
        self,
        serial: Optional[str] = None,
        whitelist_enabled: bool = True,
    ) -> None:
        self.serial = serial
        self.whitelist_enabled = whitelist_enabled

    # ------------------------------------------------------------------

    def _classify(self, raw_cmd: str) -> tuple[str, bool, bool]:
        """返回 (normalized_cmd, is_allowed, is_confirm_required)。

        normalized_cmd：去掉多余空格、小写后的命令字符串（用于匹配）。
        is_allowed：是否在白名单中（whitelist_enabled=False 时始终 True）。
        is_confirm_required：是否需要二次确认。
        """
        cmd = raw_cmd.strip()
        norm = re.sub(r"\s+", " ", cmd).lower()

        # 高危检测：前缀匹配
        for danger in CONFIRM_REQUIRED:
            if norm == danger or norm.startswith(danger + " "):
                return cmd, False, True

        if not self.whitelist_enabled:
            return cmd, True, False

        # 白名单检测：前缀匹配
        for allowed in ALLOWED_CMDS:
            if norm == allowed or norm.startswith(allowed + " "):
                return cmd, True, False

        return cmd, False, False

    async def execute(self, raw_cmd: str, *, force: bool = False) -> ReplResult:
        """执行单条 adb 命令字符串（不含 'adb' 前缀）。

        force=True 时跳过高危确认检查（前端用户已点击确认）。
        """
        cmd, is_allowed, is_confirm = self._classify(raw_cmd)

        if is_confirm and not force:
            logger.warning("adb REPL: confirm required for cmd=%r", cmd)
            return ReplResult(
                output="",
                confirm_required=True,
                error=f"高危命令需要二次确认: {cmd!r}",
            )

        if not is_allowed and not force:
            logger.warning("adb REPL: blocked cmd=%r (not in whitelist)", cmd)
            return ReplResult(
                output="",
                cmd_blocked=True,
                error=(
                    f"命令不在白名单中: {cmd!r}\n"
                    "（白名单仅纵深防御，主防线是鉴权。如需执行，联系管理员或关闭白名单）"
                ),
            )

        try:
            args = shlex.split(cmd)
        except ValueError as exc:
            return ReplResult(output="", error=f"命令解析失败: {exc}")

        try:
            if self.serial:
                result: AdbResult = await asyncio.to_thread(
                    run_adb, self.serial, args, check=False, timeout=30.0
                )
            else:
                result = await asyncio.to_thread(
                    run_adb_global, args, check=False, timeout=10.0
                )
        except Exception as exc:
            logger.exception("adb REPL execute error: %s", exc)
            return ReplResult(output="", error=str(exc))

        combined = result.stdout
        if result.stderr:
            combined += result.stderr
        if not result.ok:
            combined += f"\n[exit {result.returncode}]"

        return ReplResult(output=combined)

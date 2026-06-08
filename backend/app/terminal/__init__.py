"""Web Terminal 模块 — PTY 服务 + adb REPL。

主防线：localhost + token + Origin 鉴权（见 security/auth.py）。
纵深防御：adb_repl 白名单 + 高危子命令管控（注释见 adb_repl.py）。
仅 MANUAL 模式可用（由 API 层检查 device_mode，见 api/terminal.py）。
"""

from app.terminal.service import TerminalService
from app.terminal.adb_repl import AdbRepl

__all__ = ["TerminalService", "AdbRepl"]

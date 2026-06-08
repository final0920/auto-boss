"""PTY 服务 — 跨平台终端进程管理。

Windows 使用 pywinpty（ConPTY），Linux/macOS 使用标准 pty 模块。
每个 WebSocket 会话对应一个 TerminalSession 实例，由 TerminalService 管理。

主防线是鉴权层（security/auth.py），此处不重复校验 token。
仅 MANUAL 模式可用：API 层（api/terminal.py）在升级 WebSocket 前检查 device_mode。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 每会话最大输出缓冲字节数，防止慢客户端撑爆内存
_MAX_READ = 4096

# TerminalSession 关闭回调类型
_OnClose = Callable[["TerminalSession"], None]


class TerminalSession:
    """单个终端会话，封装底层 PTY 进程。"""

    def __init__(self, session_id: str, cols: int = 220, rows: int = 50):
        self.session_id = session_id
        self.cols = cols
        self.rows = rows
        self._proc: Optional[object] = None   # winpty.PTY | asyncio.subprocess.Process
        self._closed = False

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def start(self, cmd: list[str]) -> None:
        """启动 PTY 进程，cmd 是要执行的命令列表。"""
        if sys.platform == "win32":
            self._start_winpty(cmd)
        else:
            self._start_posix(cmd)

    def _start_winpty(self, cmd: list[str]) -> None:
        try:
            import winpty  # pywinpty>=2
        except ImportError as exc:
            raise RuntimeError(
                "pywinpty 未安装，请运行 `uv sync` 安装依赖。"
            ) from exc

        self._proc = winpty.PTY(self.cols, self.rows)
        self._proc.spawn(
            winpty.PseudoConsole.DEFAULT_INHERIT_HANDLES,
            cmdline=" ".join(cmd),
        )

    def _start_posix(self, cmd: list[str]) -> None:
        import pty

        master_fd, slave_fd = pty.openpty()
        import subprocess

        self._proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self._master_fd = master_fd

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def read(self) -> bytes:
        """同步读取一批输出字节（阻塞）；返回空 bytes 表示进程已退出。"""
        if self._closed:
            return b""
        if sys.platform == "win32":
            try:
                data = self._proc.read(_MAX_READ)  # type: ignore[union-attr]
                return data.encode("utf-8", errors="replace") if isinstance(data, str) else data
            except Exception:
                self._closed = True
                return b""
        else:
            import select

            rlist, _, _ = select.select([self._master_fd], [], [], 0.1)
            if rlist:
                try:
                    return os.read(self._master_fd, _MAX_READ)
                except OSError:
                    self._closed = True
            return b""

    def write(self, data: bytes) -> None:
        """向 PTY 写入输入字节（来自客户端键盘）。"""
        if self._closed:
            return
        if sys.platform == "win32":
            self._proc.write(data.decode("utf-8", errors="replace"))  # type: ignore[union-attr]
        else:
            os.write(self._master_fd, data)

    def resize(self, cols: int, rows: int) -> None:
        """调整终端尺寸（窗口变化时前端发送）。"""
        self.cols, self.rows = cols, rows
        if self._closed:
            return
        if sys.platform == "win32":
            self._proc.set_size(cols, rows)  # type: ignore[union-attr]
        else:
            import fcntl
            import struct
            import termios

            fcntl.ioctl(
                self._master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if sys.platform == "win32":
                self._proc.close()  # type: ignore[union-attr]
            else:
                import signal

                self._proc.send_signal(signal.SIGTERM)  # type: ignore[union-attr]
                os.close(self._master_fd)
        except Exception as exc:
            logger.debug("TerminalSession.close error: %s", exc)

    @property
    def closed(self) -> bool:
        return self._closed


# ---------------------------------------------------------------------------
# TerminalService — 会话注册表
# ---------------------------------------------------------------------------


class TerminalService:
    """管理所有活跃 TerminalSession；一般作单例挂在 app.state 上。"""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        session_id: str,
        cmd: list[str],
        cols: int = 220,
        rows: int = 50,
    ) -> TerminalSession:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].close()
            sess = TerminalSession(session_id, cols, rows)
            sess.start(cmd)
            self._sessions[session_id] = sess
            logger.info("terminal session created: %s cmd=%s", session_id, cmd)
            return sess

    async def get(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    async def close(self, session_id: str) -> None:
        async with self._lock:
            sess = self._sessions.pop(session_id, None)
            if sess:
                sess.close()
                logger.info("terminal session closed: %s", session_id)

    async def close_all(self) -> None:
        async with self._lock:
            for sess in self._sessions.values():
                sess.close()
            self._sessions.clear()

"""WebSocket 端点：Web Terminal（xterm.js 对接）。

安全模型（AC12 / plan §4）：
  主防线 = localhost-bind + token + Origin（verify_ws_request）。
  仅 MANUAL 模式放行（device_mode_manager.assert_manual()）。
  adb REPL 白名单为纵深防御，不作为 RCE 防线（见 terminal/adb_repl.py）。

协议（WebSocket 消息，JSON）：
  client → server:
    {"type": "input",   "data": "<base64 encoded bytes>"}
    {"type": "resize",  "cols": int, "rows": int}
    {"type": "confirm", "cmd": "<cmd>"}   — 用户确认高危命令后发送（force=true）
    {"type": "repl",    "cmd": "<adb sub-cmd>"}  — 直接 adb REPL 模式

  server → client:
    {"type": "output",          "data": "<base64 encoded bytes>"}
    {"type": "confirm_required", "cmd": "<cmd>", "message": str}
    {"type": "blocked",         "cmd": "<cmd>", "message": str}
    {"type": "error",           "message": str}
    {"type": "closed"}

路由：
  GET /terminal/ws?token=<TERMINAL_TOKEN>&serial=<adb_serial>&mode=repl|pty
    mode=pty  — 完整 PTY shell（adb shell）
    mode=repl — 仅 adb REPL（推荐；白名单更严格）
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.automation.device_mode import device_mode_manager
from app.security.auth import verify_ws_request
from app.terminal.adb_repl import AdbRepl
from app.terminal.service import TerminalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terminal", tags=["terminal"])

# 模块级 TerminalService 单例（main.py 可替换为 app.state 上的实例）
_terminal_service = TerminalService()


def get_terminal_service() -> TerminalService:
    return _terminal_service


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def terminal_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    serial: str = Query(default=""),
    mode: str = Query(default="repl"),  # "repl" | "pty"
):
    """WebSocket terminal 端点。

    鉴权 → 模式检查 → 分发到 PTY 或 adb REPL 处理器。
    """
    # 1. 鉴权（主防线）
    try:
        await verify_ws_request(websocket, token=token)
    except Exception as exc:
        await websocket.close(code=4401, reason=str(exc))
        return

    # 2. 仅 MANUAL 模式（AC10）
    try:
        device_mode_manager.assert_manual()
    except Exception as exc:
        await websocket.close(code=4403, reason=str(exc))
        return

    await websocket.accept()

    if mode == "pty" and serial:
        await _handle_pty(websocket, serial)
    else:
        await _handle_repl(websocket, serial or None)


# ---------------------------------------------------------------------------
# PTY 模式 — 完整 adb shell PTY
# ---------------------------------------------------------------------------


async def _handle_pty(ws: WebSocket, serial: str) -> None:
    """PTY 模式：adb shell 完整终端，通过 winpty/pty 双向 I/O。"""
    session_id = str(uuid.uuid4())
    svc = get_terminal_service()

    try:
        sess = await svc.create(
            session_id,
            cmd=["adb", "-s", serial, "shell"],
            cols=220,
            rows=50,
        )
    except Exception as exc:
        await _send_json(ws, {"type": "error", "message": f"PTY 启动失败: {exc}"})
        await ws.close()
        return

    # 读取 PTY 输出 → 推给 ws
    async def pump_output() -> None:
        loop = asyncio.get_running_loop()
        while not sess.closed:
            data = await loop.run_in_executor(None, sess.read)
            if data:
                await _send_json(ws, {
                    "type": "output",
                    "data": base64.b64encode(data).decode(),
                })
            else:
                await asyncio.sleep(0.02)
        await _send_json(ws, {"type": "closed"})

    pump_task = asyncio.create_task(pump_output())

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")
            if t == "input":
                payload = base64.b64decode(msg.get("data", ""))
                await asyncio.get_running_loop().run_in_executor(None, sess.write, payload)
            elif t == "resize":
                cols = int(msg.get("cols", 220))
                rows = int(msg.get("rows", 50))
                await asyncio.get_running_loop().run_in_executor(
                    None, sess.resize, cols, rows
                )
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        pump_task.cancel()
        await svc.close(session_id)


# ---------------------------------------------------------------------------
# REPL 模式 — adb 子命令 REPL（纵深防御白名单）
# ---------------------------------------------------------------------------


async def _handle_repl(ws: WebSocket, serial: Optional[str]) -> None:
    """REPL 模式：逐条执行 adb 命令，白名单 + 高危确认。"""
    repl = AdbRepl(serial=serial, whitelist_enabled=True)
    pending_confirm: Optional[str] = None  # 等待确认的高危命令

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")

            if t == "repl":
                cmd = msg.get("cmd", "").strip()
                if not cmd:
                    continue
                result = await repl.execute(cmd, force=False)
                if result.confirm_required:
                    pending_confirm = cmd
                    await _send_json(ws, {
                        "type": "confirm_required",
                        "cmd": cmd,
                        "message": result.error or "高危命令需要二次确认",
                    })
                elif result.cmd_blocked:
                    await _send_json(ws, {
                        "type": "blocked",
                        "cmd": cmd,
                        "message": result.error or "命令不在白名单中",
                    })
                else:
                    out = result.output or (result.error or "")
                    await _send_json(ws, {
                        "type": "output",
                        "data": base64.b64encode(out.encode()).decode(),
                    })

            elif t == "confirm":
                # 用户确认执行高危命令（force=True）
                cmd = msg.get("cmd", pending_confirm or "")
                if not cmd:
                    continue
                pending_confirm = None
                result = await repl.execute(cmd, force=True)
                out = result.output or (result.error or "")
                await _send_json(ws, {
                    "type": "output",
                    "data": base64.b64encode(out.encode()).decode(),
                })

    except (WebSocketDisconnect, Exception):
        pass


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


async def _send_json(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

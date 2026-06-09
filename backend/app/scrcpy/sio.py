"""scrcpy Socket.IO 命名空间 — H.264 帧广播，鉴权，control=false 只读。

命名空间：/scrcpy
事件：
  server → client:
    "device_info"  {"device_name": str, "width": int, "height": int}
    "frame"        {"pts": int|null, "data": bytes (binary)}
    "error"        {"message": str}
  client → server:
    "start"        {"serial": str, "token": str(可选，鉴权走 connect query)}
    "stop"         {}

鉴权：
  connect 时通过 query param token= 校验（sio_auth_ok）。
  主防线 = localhost-bind + token + Origin，见 security/auth.py。

降级逻辑：
  scrcpy-server JAR 缺失时，emit "error" 事件通知前端降级为截图轮询，
  不中断 WebSocket 连接。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import socketio

from app.scrcpy.protocol import DeviceInfo, VideoFrame
from app.scrcpy.streamer import ScrcpyServerMissingError, ScrcpyStreamer
from app.security.auth import sio_auth_ok

logger = logging.getLogger(__name__)

# 活跃 streamer 注册表：sid -> ScrcpyStreamer
_streamers: dict[str, ScrcpyStreamer] = {}
# 活跃 stream 任务：sid -> asyncio.Task
_tasks: dict[str, asyncio.Task] = {}


def register_scrcpy_namespace(sio: socketio.AsyncServer) -> None:
    """向已有 AsyncServer 注册 /scrcpy 命名空间。

    在 main.py 的 lifespan 或模块导入时调用：
        from app.scrcpy.sio import register_scrcpy_namespace
        register_scrcpy_namespace(sio)
    """
    ns = ScrcpyNamespace("/scrcpy")
    sio.register_namespace(ns)
    logger.info("scrcpy Socket.IO 命名空间 /scrcpy 已注册")


class ScrcpyNamespace(socketio.AsyncNamespace):
    """Socket.IO /scrcpy 命名空间。"""

    async def on_connect(self, sid: str, environ: dict, auth: Optional[dict] = None) -> None:
        if not sio_auth_ok(environ):
            logger.warning("scrcpy: 已拒绝未鉴权连接 sid=%s", sid)
            raise ConnectionRefusedError("authentication failed")
        logger.info("scrcpy: 客户端已连接 sid=%s", sid)

    async def on_disconnect(self, sid: str) -> None:
        await _stop_stream(sid)
        logger.info("scrcpy: 客户端已断开 sid=%s", sid)

    async def on_start(self, sid: str, data: dict) -> None:
        """client → server: 开始推流指定设备。

        data: {"serial": str}
        """
        serial = (data or {}).get("serial", "")
        if not serial:
            await self.emit("error", {"message": "serial 参数缺失"}, to=sid)
            return

        # 停止之前的流（如有）
        await _stop_stream(sid)

        streamer = ScrcpyStreamer(serial)
        _streamers[sid] = streamer

        task = asyncio.create_task(
            _run_stream(self, sid, streamer),
            name=f"scrcpy-{sid}",
        )
        _tasks[sid] = task
        logger.info("scrcpy: 推流已启动 sid=%s serial=%s", sid, serial)

    async def on_stop(self, sid: str, data: dict) -> None:
        """client → server: 停止推流。"""
        await _stop_stream(sid)
        logger.info("scrcpy: 推流已被客户端停止 sid=%s", sid)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _run_stream(ns: ScrcpyNamespace, sid: str, streamer: ScrcpyStreamer) -> None:
    """在后台 task 中读取帧并广播到 sid。"""
    try:
        async for item in streamer.stream():
            if isinstance(item, DeviceInfo):
                await ns.emit(
                    "device_info",
                    {
                        "device_name": item.device_name,
                        "width": item.width,
                        "height": item.height,
                    },
                    to=sid,
                )
            elif isinstance(item, VideoFrame):
                # 二进制帧：pts(int|null) + H.264 NAL data(bytes)
                # python-socketio 传 bytes 时自动走二进制帧
                await ns.emit(
                    "frame",
                    {"pts": item.pts, "data": item.data},
                    to=sid,
                )
    except ScrcpyServerMissingError as exc:
        logger.warning("scrcpy: server JAR 缺失，通知客户端降级: %s", exc)
        await ns.emit(
            "error",
            {
                "message": str(exc),
                "fallback": "screenshot_polling",  # 前端检查此字段降级
            },
            to=sid,
        )
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("scrcpy stream error sid=%s: %s", sid, exc)
        await ns.emit("error", {"message": str(exc)}, to=sid)
    finally:
        _streamers.pop(sid, None)
        _tasks.pop(sid, None)


async def _stop_stream(sid: str) -> None:
    """取消并清理 sid 对应的流任务和 streamer。"""
    task = _tasks.pop(sid, None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    streamer = _streamers.pop(sid, None)
    if streamer:
        await streamer.stop()

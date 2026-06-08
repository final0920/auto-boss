"""scrcpy streamer — 启动 scrcpy-server，读取 H.264 帧并广播到 Socket.IO。

control=false：只读视频流，不向设备发送任何控制指令。

scrcpy-server JAR 路径：
  优先读 SCRCPY_SERVER_JAR 环境变量；
  默认查找 backend/resources/scrcpy-server.jar。
  JAR 缺失时 ScrcpyStreamer.start() 抛出 ScrcpyServerMissingError，
  调用方应降级为截图轮询（useScreenshotPolling）。

下载说明（TODO）：
  scrcpy-server 与 scrcpy 客户端版本必须匹配。
  官方 release：https://github.com/Genymobile/scrcpy/releases
  推荐版本：v3.x，下载对应 scrcpy-server，重命名为 scrcpy-server.jar，
  放到 backend/resources/scrcpy-server.jar。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from pathlib import Path
from typing import AsyncIterator, Optional

from app.scrcpy.protocol import DeviceInfo, FrameReader, VideoFrame

logger = logging.getLogger(__name__)

# scrcpy-server 推送到设备的临时路径
_DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"

# 默认本地 JAR 搜索路径（相对 backend/）
_DEFAULT_JAR = Path(__file__).parents[3] / "resources" / "scrcpy-server.jar"


class ScrcpyServerMissingError(RuntimeError):
    """scrcpy-server JAR 不存在，需降级为截图轮询。"""


class ScrcpyStreamer:
    """管理单台设备的 scrcpy 视频流。

    用法：
        streamer = ScrcpyStreamer(serial="XXXX")
        async with streamer.stream() as frames:
            async for frame in frames:
                # frame: VideoFrame | DeviceInfo
                ...
    """

    # scrcpy-server 版本（需与 JAR 版本匹配）
    SERVER_VERSION = "3.1"
    # 视频编码器
    VIDEO_CODEC = "h264"
    # 最大尺寸（0=原始分辨率）
    MAX_SIZE = 1280
    # 视频比特率（bps）
    BIT_RATE = 2_000_000
    # 帧率上限
    MAX_FPS = 30
    # 本机监听端口（adb forward 映射到此）
    LOCAL_PORT = 27183

    def __init__(self, serial: str) -> None:
        self.serial = serial
        self._running = False
        self._proc: Optional[asyncio.subprocess.Process] = None

    # ------------------------------------------------------------------
    # JAR 路径解析
    # ------------------------------------------------------------------

    @staticmethod
    def _jar_path() -> Path:
        env_path = os.environ.get("SCRCPY_SERVER_JAR")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p
            raise ScrcpyServerMissingError(
                f"SCRCPY_SERVER_JAR={env_path} 文件不存在"
            )
        if _DEFAULT_JAR.is_file():
            return _DEFAULT_JAR
        raise ScrcpyServerMissingError(
            f"scrcpy-server JAR 未找到（默认路径: {_DEFAULT_JAR}）。\n"
            "下载说明：https://github.com/Genymobile/scrcpy/releases\n"
            "下载对应版本的 scrcpy-server，重命名为 scrcpy-server.jar，"
            "放到 backend/resources/scrcpy-server.jar。"
        )

    # ------------------------------------------------------------------
    # 推送 JAR + 建立 adb forward
    # ------------------------------------------------------------------

    async def _push_server(self, jar: Path) -> None:
        """将 scrcpy-server.jar push 到设备临时目录。"""
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", self.serial,
            "push", str(jar), _DEVICE_SERVER_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb push scrcpy-server 失败: {stderr.decode(errors='replace')}"
            )

    async def _setup_forward(self) -> None:
        """建立 adb forward tcp 映射。"""
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", self.serial,
            "forward", f"tcp:{self.LOCAL_PORT}", "localabstract:scrcpy",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb forward 失败: {stderr.decode(errors='replace')}"
            )

    async def _remove_forward(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", self.serial,
            "forward", "--remove", f"tcp:{self.LOCAL_PORT}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    # ------------------------------------------------------------------
    # 启动 scrcpy-server 进程
    # ------------------------------------------------------------------

    async def _launch_server(self) -> None:
        """在设备上以 app_process 运行 scrcpy-server。"""
        # scrcpy-server ≥2.0 参数格式（key=value）
        server_args = " ".join([
            f"version={self.SERVER_VERSION}",
            "tunnel_forward=true",
            f"video_codec={self.VIDEO_CODEC}",
            f"max_size={self.MAX_SIZE}",
            f"video_bit_rate={self.BIT_RATE}",
            f"max_fps={self.MAX_FPS}",
            "control=false",       # 只读，不接收控制指令（AC12 / plan §3）
            "send_device_meta=true",
            "send_frame_meta=true",
            "send_dummy_byte=true",
            "audio=false",
            "cleanup=true",
        ])
        cmd = [
            "adb", "-s", self.serial,
            "shell",
            f"CLASSPATH={_DEVICE_SERVER_PATH}",
            "app_process", "/",
            "com.genymobile.scrcpy.Server",
            server_args,
        ]
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("scrcpy-server launched on %s pid=%s", self.serial, self._proc.pid)

    # ------------------------------------------------------------------
    # 连接本地 socket 读取帧
    # ------------------------------------------------------------------

    async def _connect_socket(self, retries: int = 10) -> socket.socket:
        """等待 scrcpy-server 就绪后连接本地 TCP socket。"""
        for i in range(retries):
            await asyncio.sleep(0.3)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(("127.0.0.1", self.LOCAL_PORT))
                sock.setblocking(False)
                logger.info("scrcpy socket connected (attempt %d)", i + 1)
                return sock
            except OSError:
                if i == retries - 1:
                    raise RuntimeError(
                        f"无法连接 scrcpy 本地 socket（端口 {self.LOCAL_PORT}）"
                    )
        raise RuntimeError("unreachable")

    # ------------------------------------------------------------------
    # 公开接口：async generator
    # ------------------------------------------------------------------

    async def stream(self) -> AsyncIterator[VideoFrame | DeviceInfo]:
        """异步生成器：产生 DeviceInfo（握手头）和 VideoFrame。

        调用方负责在不需要时取消迭代（break 或 aclose()）。
        """
        jar = self._jar_path()  # 不存在时抛 ScrcpyServerMissingError

        await self._push_server(jar)
        await self._setup_forward()
        await self._launch_server()

        self._running = True
        sock: Optional[socket.socket] = None
        try:
            # 跳过 scrcpy 发送的 dummy byte（send_dummy_byte=true）
            sock = await self._connect_socket()
            loop = asyncio.get_running_loop()
            dummy = await loop.sock_recv(sock, 1)
            if dummy != b"\x00":
                logger.warning("scrcpy: unexpected dummy byte %r", dummy)

            reader = FrameReader()
            while self._running:
                try:
                    chunk = await loop.sock_recv(sock, 65536)
                except OSError as exc:
                    logger.warning("scrcpy socket read error: %s", exc)
                    break
                if not chunk:
                    logger.info("scrcpy socket closed by server")
                    break
                for item in reader.feed(chunk):
                    yield item
        finally:
            self._running = False
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            await self.stop()

    async def stop(self) -> None:
        """停止 scrcpy-server 进程并清理 forward。"""
        self._running = False
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except Exception as exc:
                logger.debug("scrcpy stop error: %s", exc)
        self._proc = None
        await self._remove_forward()
        logger.info("scrcpy streamer stopped for %s", self.serial)

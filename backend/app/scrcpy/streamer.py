"""scrcpy streamer — 启动 scrcpy-server，读取 H.264 帧并广播到 Socket.IO。

control=false：只读视频流，不向设备发送任何控制指令。

scrcpy-server JAR 路径：
  优先读 SCRCPY_SERVER_JAR 环境变量；
  默认查找 backend/app/scrcpy/resources/scrcpy-server.jar。
  JAR 缺失时抛出 ScrcpyServerMissingError，
  调用方应降级为截图轮询（useScreenshotPolling）。

下载说明：
  运行 uv run python scripts/download_scrcpy_server.py（走代理 127.0.0.1:7890）。
  scrcpy-server 与 scrcpy 客户端版本必须匹配。
  官方 release：https://github.com/Genymobile/scrcpy/releases
  推荐版本：v3.x，下载对应 scrcpy-server，重命名为 scrcpy-server.jar，
  放到 backend/app/scrcpy/resources/scrcpy-server.jar。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
from pathlib import Path
from typing import AsyncIterator, Optional

from app.scrcpy.protocol import DeviceInfo, FrameReader, VideoFrame

logger = logging.getLogger(__name__)

# scrcpy-server 推送到设备的临时路径
_DEVICE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"

# 默认本地 JAR 搜索路径（app/scrcpy/resources/）
_DEFAULT_JAR = Path(__file__).parent / "resources" / "scrcpy-server.jar"


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
        self._proc: Optional[subprocess.Popen] = None

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
            "下载说明：运行 uv run python scripts/download_scrcpy_server.py\n"
            "或手动下载：https://github.com/Genymobile/scrcpy/releases\n"
            "下载对应版本的 scrcpy-server，重命名为 scrcpy-server.jar，"
            "放到 backend/app/scrcpy/resources/scrcpy-server.jar。"
        )

    # ------------------------------------------------------------------
    # 推送 JAR + 建立 adb forward
    # ------------------------------------------------------------------

    async def _push_server(self, jar: Path) -> None:
        """将 scrcpy-server.jar push 到设备临时目录（同步 subprocess + 线程）。"""
        def _run() -> "subprocess.CompletedProcess[bytes]":
            return subprocess.run(
                ["adb", "-s", self.serial, "push", str(jar), _DEVICE_SERVER_PATH],
                capture_output=True,
            )
        proc = await asyncio.to_thread(_run)
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb push scrcpy-server 失败: {proc.stderr.decode(errors='replace')}"
            )

    async def _setup_forward(self) -> None:
        """建立 adb forward tcp 映射（同步 subprocess + 线程）。"""
        def _run() -> "subprocess.CompletedProcess[bytes]":
            return subprocess.run(
                ["adb", "-s", self.serial, "forward",
                 f"tcp:{self.LOCAL_PORT}", "localabstract:scrcpy"],
                capture_output=True,
            )
        proc = await asyncio.to_thread(_run)
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb forward 失败: {proc.stderr.decode(errors='replace')}"
            )

    async def _remove_forward(self) -> None:
        def _run() -> None:
            subprocess.run(
                ["adb", "-s", self.serial, "forward", "--remove",
                 f"tcp:{self.LOCAL_PORT}"],
                capture_output=True,
            )
        await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # 启动 scrcpy-server 进程
    # ------------------------------------------------------------------

    async def _launch_server(self) -> None:
        """在设备上以 app_process 运行 scrcpy-server（同步 Popen + 线程）。

        Windows 的 SelectorEventLoop 不支持 asyncio 子进程
        （create_subprocess_exec 抛 NotImplementedError），故用同步 Popen 起进程，
        socket 读仍走 asyncio（Selector 支持 sock_recv）。
        """
        # scrcpy-server ≥2.0：version 必须是紧跟 Server 的第一个裸位置参数，
        # 其余为 key=value 选项。写成 version=x 会导致版本校验失败、server 立即退出。
        server_args = " ".join([
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
            self.SERVER_VERSION,   # 裸 version 位置参数（不能写成 version=x）
            server_args,
        ]
        def _spawn() -> subprocess.Popen:
            return subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        self._proc = await asyncio.to_thread(_spawn)
        logger.info("scrcpy-server 已在 %s 上启动 pid=%s", self.serial, self._proc.pid)

    # ------------------------------------------------------------------
    # 连接本地 socket 读取帧
    # ------------------------------------------------------------------

    async def _connect_socket(self, retries: int = 20) -> socket.socket:
        """连接本地 forward socket 并完成 dummy byte 握手。

        adb forward 在设备端 localabstract:scrcpy 尚无监听者时也会 accept 本地
        连接、随后立即 EOF（recv 返回 b''）——所以必须"连接+读到 0x00"整体重试，
        不能只重试 connect（官方 scrcpy 客户端同此做法）。
        """
        last_state = "未知"
        for i in range(retries):
            await asyncio.sleep(0.4)
            # server 进程已退出 → 读 stderr 直接报因，不再空等
            if self._proc is not None and self._proc.poll() is not None:
                err = ""
                try:
                    if self._proc.stderr:
                        err = self._proc.stderr.read().decode(errors="replace").strip()
                except Exception:
                    pass
                raise RuntimeError(
                    f"scrcpy-server 已退出(code={self._proc.returncode}): {err[:300]}"
                )
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(("127.0.0.1", self.LOCAL_PORT))
                sock.settimeout(2.0)
                # 阻塞 recv via to_thread（Windows SelectorEventLoop 的 sock_recv
                # 对该 forward socket 误读 EOF，同步阻塞 recv 正常）
                dummy = await asyncio.to_thread(sock.recv, 1)
                if dummy == b"\x00":
                    logger.info("scrcpy 握手成功（第 %d 次尝试）", i + 1)
                    return sock
                # b''=EOF（server 未就绪）/其他=协议异常 → 关闭重试
                last_state = f"dummy={dummy!r}"
                sock.close()
            except (OSError, socket.timeout) as exc:
                last_state = str(exc)
                try:
                    sock.close()
                except Exception:
                    pass
        raise RuntimeError(
            f"scrcpy 握手失败（{retries} 次重试，最后状态: {last_state}）。"
            "检查设备是否在线、scrcpy-server 是否被系统杀死。"
        )

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
            # 连接 + dummy byte(0x00) 握手在 _connect_socket 内整体重试完成
            sock = await self._connect_socket()

            reader = FrameReader()
            while self._running:
                try:
                    chunk = await asyncio.to_thread(sock.recv, 65536)
                except socket.timeout:
                    continue  # 读超时（画面静止无新帧），继续轮询 _running
                except OSError as exc:
                    logger.warning("scrcpy socket 读取错误: %s", exc)
                    break
                if not chunk:
                    logger.info("scrcpy socket 已被服务端关闭")
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
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                await asyncio.to_thread(self._proc.wait, 3.0)
            except Exception as exc:
                logger.debug("scrcpy 停止出错: %s", exc)
        self._proc = None
        await self._remove_forward()
        logger.info("scrcpy streamer 已停止 serial=%s", self.serial)

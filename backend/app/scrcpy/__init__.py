"""scrcpy 投屏模块 — H.264 over Socket.IO，control=false 只读视频。

端点鉴权由 security/auth.py 统一处理（主防线）。
scrcpy-server JAR 缺失时降级为截图轮询（useScreenshotPolling）。
"""

from app.scrcpy.streamer import ScrcpyStreamer
from app.scrcpy.sio import register_scrcpy_namespace

__all__ = ["ScrcpyStreamer", "register_scrcpy_namespace"]

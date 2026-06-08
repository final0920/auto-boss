"""scrcpy 协议解析 — 仅视频帧（control=false，只读）。

参考 scrcpy 源码 server/src/main/java/com/genymobile/scrcpy/video/VideoEncoder.java
以及 AutoGLM-GUI scrcpy_protocol.py。

帧格式（scrcpy ≥2.0，video-only 模式）：
  连接后服务端先发送 device_name(64 bytes) + width(2) + height(2)，共 68 字节。
  之后每帧：
    pts       8 bytes  big-endian uint64（微秒，可能含 NO_PTS 标志）
    size      4 bytes  big-endian uint32（NAL 数据长度）
    data      size bytes H.264 NAL unit

NO_PTS 标志位：bit63 = 1 表示此帧无 PTS（配置帧 SPS/PPS）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

# scrcpy 连接握手头大小
HANDSHAKE_SIZE = 68  # device_name(64) + width(2) + height(2)

# NO_PTS 标志（bit63）
_NO_PTS_FLAG = 1 << 63


@dataclass
class DeviceInfo:
    device_name: str
    width: int
    height: int


@dataclass
class VideoFrame:
    pts: Optional[int]   # 微秒；None 表示配置帧（SPS/PPS）
    data: bytes


def parse_handshake(buf: bytes) -> DeviceInfo:
    """解析 68 字节握手头。"""
    if len(buf) < HANDSHAKE_SIZE:
        raise ValueError(f"握手数据不足: {len(buf)} < {HANDSHAKE_SIZE}")
    name_raw = buf[:64]
    name = name_raw.rstrip(b"\x00").decode("utf-8", errors="replace")
    (width,) = struct.unpack_from(">H", buf, 64)
    (height,) = struct.unpack_from(">H", buf, 66)
    return DeviceInfo(device_name=name, width=width, height=height)


def parse_frame_header(buf: bytes) -> tuple[Optional[int], int]:
    """从 12 字节帧头解析 (pts, size)。

    返回 (pts_us, payload_size)；pts 为 None 表示 NO_PTS（配置帧）。
    """
    if len(buf) < 12:
        raise ValueError(f"帧头不足: {len(buf)} < 12")
    (pts_raw,) = struct.unpack_from(">Q", buf, 0)
    (size,) = struct.unpack_from(">I", buf, 8)
    pts: Optional[int] = None if (pts_raw & _NO_PTS_FLAG) else pts_raw
    return pts, size


class FrameReader:
    """流式帧读取器，内部维护接收缓冲区。

    使用方式（asyncio）：
        reader = FrameReader()
        async for chunk in socket_stream:
            for frame in reader.feed(chunk):
                # frame 是 VideoFrame
                emit_to_client(frame)
    """

    _STATE_HANDSHAKE = "handshake"
    _STATE_HEADER = "header"
    _STATE_PAYLOAD = "payload"

    def __init__(self) -> None:
        self._buf = bytearray()
        self._state = self._STATE_HANDSHAKE
        self._pts: Optional[int] = None
        self._payload_size: int = 0
        self.device_info: Optional[DeviceInfo] = None

    def feed(self, data: bytes) -> list[VideoFrame | DeviceInfo]:
        """向缓冲区追加数据，返回解析出的对象列表（DeviceInfo 或 VideoFrame）。"""
        self._buf.extend(data)
        results: list[VideoFrame | DeviceInfo] = []

        while True:
            if self._state == self._STATE_HANDSHAKE:
                if len(self._buf) < HANDSHAKE_SIZE:
                    break
                chunk = bytes(self._buf[:HANDSHAKE_SIZE])
                del self._buf[:HANDSHAKE_SIZE]
                self.device_info = parse_handshake(chunk)
                results.append(self.device_info)
                self._state = self._STATE_HEADER

            elif self._state == self._STATE_HEADER:
                if len(self._buf) < 12:
                    break
                chunk = bytes(self._buf[:12])
                del self._buf[:12]
                self._pts, self._payload_size = parse_frame_header(chunk)
                self._state = self._STATE_PAYLOAD

            elif self._state == self._STATE_PAYLOAD:
                if len(self._buf) < self._payload_size:
                    break
                payload = bytes(self._buf[: self._payload_size])
                del self._buf[: self._payload_size]
                results.append(VideoFrame(pts=self._pts, data=payload))
                self._state = self._STATE_HEADER

        return results

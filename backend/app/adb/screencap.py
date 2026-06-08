"""截图原语 — adb exec-out screencap -p → PIL.Image，含 PNG 校验与重试。"""

from __future__ import annotations

import subprocess
import time
from io import BytesIO
from typing import Optional


# PIL 按需导入，避免在无 Pillow 环境下模块级报错
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def screencap_png_bytes(
    serial: str,
    *,
    retries: int = 3,
    retry_delay: float = 0.5,
    timeout: float = 10.0,
) -> bytes:
    """通过 adb exec-out screencap -p 获取 PNG 字节流。

    - 校验 PNG magic bytes，失败则重试。
    - 不写临时文件，直接返回内存中的 bytes。
    """
    cmd = ["adb", "-s", serial, "exec-out", "screencap", "-p"]
    last_err: Optional[Exception] = None

    for attempt in range(retries):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            last_err = TimeoutError(f"screencap 超时 attempt={attempt}: {exc}")
            time.sleep(retry_delay)
            continue
        except FileNotFoundError as exc:
            raise RuntimeError("未找到 adb，请确认 Platform-Tools 在 PATH 中。") from exc

        data: bytes = proc.stdout

        # PNG magic 校验
        if not data.startswith(_PNG_MAGIC):
            last_err = ValueError(
                f"screencap 返回非 PNG 数据 attempt={attempt}，"
                f"前8字节: {data[:8]!r}，stderr: {proc.stderr[:200]!r}"
            )
            time.sleep(retry_delay)
            continue

        return data

    raise RuntimeError(f"screencap 连续 {retries} 次失败，最后错误: {last_err}") from last_err


def screencap(
    serial: str,
    *,
    retries: int = 3,
    retry_delay: float = 0.5,
    timeout: float = 10.0,
) -> "Image.Image":
    """截图并返回 PIL.Image 对象。需要 Pillow 依赖。"""
    if not _PIL_AVAILABLE:
        raise ImportError("screencap() 需要 Pillow，请 uv add pillow。")

    data = screencap_png_bytes(serial, retries=retries, retry_delay=retry_delay, timeout=timeout)
    return Image.open(BytesIO(data))


def screencap_region(
    serial: str,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    retries: int = 3,
    timeout: float = 10.0,
) -> "Image.Image":
    """截图后裁剪指定区域，用于局部 OCR。"""
    img = screencap(serial, retries=retries, timeout=timeout)
    return img.crop((x, y, x + width, y + height))

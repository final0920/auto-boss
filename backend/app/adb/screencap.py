"""截图原语 — adb exec-out screencap -p → PNG bytes，含 PNG 校验与重试。"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

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

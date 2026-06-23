"""底层 run_adb 封装 — 所有 adb 调用统一入口，便于 mock。"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Sequence


@lru_cache(maxsize=1)
def adb_exe() -> str:
    """解析 adb 可执行文件路径。

    优先用项目依赖 adbutils 自带的 adb.exe（随 .venv 一定安装），回退系统
    PATH 的 adb。这样无需用户单独安装 platform-tools 或把 adb 配进 PATH，
    在任意 shell（PowerShell/cmd/bash）启动后端都能用。
    """
    try:
        import adbutils
        p = adbutils.adb_path()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return shutil.which("adb") or "adb"


@dataclass
class AdbResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_adb(
    serial: str,
    args: Sequence[str],
    *,
    timeout: float = 30.0,
    check: bool = True,
    input: Optional[bytes] = None,
) -> AdbResult:
    """对指定 serial 设备执行 adb 命令，返回结构化结果。

    所有 adb 调用必须经此函数，禁止直接 subprocess.run(['adb', ...])，
    方便测试时 mock 整个入口。
    """
    cmd = [adb_exe(), "-s", serial] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"adb 命令超时 ({timeout}s): {cmd}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 adb 可执行文件，请确认 Android SDK Platform-Tools 已安装并在 PATH 中。") from exc

    result = AdbResult(
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8", errors="replace"),
        stderr=proc.stderr.decode("utf-8", errors="replace"),
    )

    if check and not result.ok:
        raise RuntimeError(
            f"adb 命令失败 (rc={result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def run_adb_global(
    args: Sequence[str],
    *,
    timeout: float = 10.0,
    check: bool = True,
) -> AdbResult:
    """不带 -s serial 的全局 adb 命令（如 devices、start-server）。"""
    cmd = [adb_exe()] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"adb 全局命令超时 ({timeout}s): {cmd}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 adb 可执行文件，请确认 Android SDK Platform-Tools 已安装并在 PATH 中。") from exc

    result = AdbResult(
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8", errors="replace"),
        stderr=proc.stderr.decode("utf-8", errors="replace"),
    )

    if check and not result.ok:
        raise RuntimeError(
            f"adb 全局命令失败 (rc={result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result

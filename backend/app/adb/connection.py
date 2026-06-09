"""adb 连接管理 — 默认 USB；adb connect 仅显式调用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.adb._run import run_adb_global


@dataclass
class DeviceInfo:
    serial: str
    state: str  # "device" | "offline" | "unauthorized" | ...
    transport: str = "usb"  # "usb" | "wifi"
    product: str = ""
    model: str = ""
    device: str = ""

    @property
    def online(self) -> bool:
        return self.state == "device"


# ---------------------------------------------------------------------------
# 解析 `adb devices -l` 输出
# ---------------------------------------------------------------------------

_DEVICE_RE = re.compile(
    r"^(?P<serial>\S+)\s+(?P<state>\S+)"
    r"(?:\s+product:(?P<product>\S+))?"
    r"(?:\s+model:(?P<model>\S+))?"
    r"(?:\s+device:(?P<device>\S+))?",
    re.MULTILINE,
)


def _parse_devices(output: str) -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        m = _DEVICE_RE.match(line)
        if not m:
            continue
        serial = m.group("serial")
        state = m.group("state")
        # wifi 设备 serial 形如 192.168.x.x:port
        transport = "wifi" if re.match(r"\d+\.\d+\.\d+\.\d+:\d+", serial) else "usb"
        devices.append(
            DeviceInfo(
                serial=serial,
                state=state,
                transport=transport,
                product=m.group("product") or "",
                model=m.group("model") or "",
                device=m.group("device") or "",
            )
        )
    return devices


# ---------------------------------------------------------------------------
# 公共接口
# ---------------------------------------------------------------------------


def list_devices() -> list[DeviceInfo]:
    """枚举当前所有 adb 设备（USB + WiFi）。"""
    result = run_adb_global(["-d", "devices", "-l"], check=False)
    # -d 仅 USB；去掉 -d 可列 USB+WiFi，但 -d 会在有多设备时报错
    # 直接不带 -d，统一列全部
    result = run_adb_global(["devices", "-l"], check=False)
    return _parse_devices(result.stdout)


def list_usb_devices() -> list[DeviceInfo]:
    """仅返回 USB 连接的在线真机（排除 emulator- 模拟器）。"""
    return [
        d for d in list_devices()
        if d.transport == "usb" and d.online and not d.serial.startswith("emulator-")
    ]


def connect_usb(serial: Optional[str] = None) -> DeviceInfo:
    """返回第一个（或指定 serial 的）USB 在线设备；不发起 TCP 连接。"""
    devices = list_usb_devices()
    if not devices:
        raise RuntimeError("未检测到 USB 在线设备，请确认 USB 调试已开启并连接。")
    if serial:
        for d in devices:
            if d.serial == serial:
                return d
        raise RuntimeError(f"未找到 serial={serial} 的 USB 在线设备。")
    return devices[0]


def ensure_online(serial: str, retries: int = 3) -> bool:
    """等待设备上线；返回 True 表示在线。"""
    import time

    for _ in range(retries):
        devices = list_devices()
        for d in devices:
            if d.serial == serial and d.online:
                return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# AdbConnection — 绑定 serial 的连接句柄
# ---------------------------------------------------------------------------


class AdbConnection:
    """绑定单台设备 serial 的连接句柄，供上层模块使用。"""

    def __init__(self, serial: str):
        self.serial = serial

    @classmethod
    def from_usb(cls, serial: Optional[str] = None) -> "AdbConnection":
        """从 USB 设备列表中选取连接句柄（默认首台）。"""
        info = connect_usb(serial)
        return cls(info.serial)

    def is_online(self) -> bool:
        return ensure_online(self.serial, retries=1)

    def __repr__(self) -> str:
        return f"AdbConnection(serial={self.serial!r})"

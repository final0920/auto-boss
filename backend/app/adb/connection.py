"""adb 连接管理 — 默认 USB；adb connect 仅显式调用。"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

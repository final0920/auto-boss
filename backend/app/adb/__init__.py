"""adb 原语层 — 非特权命令封装，默认 USB 连接。"""

from app.adb.connection import AdbConnection, DeviceInfo, list_devices, connect_usb, ensure_online
from app.adb.device import AdbDevice
from app.adb.inputs import ADBKeyboard
from app.adb.screencap import screencap, screencap_png_bytes
from app.adb.appinfo import get_foreground_package, get_foreground_activity

__all__ = [
    "AdbConnection",
    "DeviceInfo",
    "list_devices",
    "connect_usb",
    "ensure_online",
    "AdbDevice",
    "ADBKeyboard",
    "screencap",
    "screencap_png_bytes",
    "get_foreground_package",
    "get_foreground_activity",
]

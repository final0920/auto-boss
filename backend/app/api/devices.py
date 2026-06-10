"""devices — 设备列表/USB 连接/状态（鉴权 AC12）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.security.auth import require_auth

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_devices() -> list[dict]:
    """列出当前所有 adb 设备。"""
    from app.adb.connection import list_devices as _list  # 惰性导入

    devices = await __import__("asyncio").to_thread(_list)
    return [
        {
            "serial": d.serial,
            "state": d.state,
            "transport": d.transport,
            "model": d.model,
            "product": d.product,
            "online": d.online,
        }
        for d in devices
    ]


@router.get("/usb", dependencies=[Depends(require_auth)])
async def list_usb_devices() -> list[dict]:
    """仅返回 USB 在线设备。"""
    import asyncio

    from app.adb.connection import list_usb_devices as _list

    devices = await asyncio.to_thread(_list)
    return [
        {
            "serial": d.serial,
            "state": d.state,
            "transport": d.transport,
            "model": d.model,
            "online": d.online,
        }
        for d in devices
    ]



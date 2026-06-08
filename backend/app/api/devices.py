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


@router.get("/mode", dependencies=[Depends(require_auth)])
async def get_device_mode() -> dict:
    """返回当前 device_mode。"""
    from app.automation.device_mode import device_mode_manager

    return {"mode": device_mode_manager.mode.value}


@router.post("/mode", dependencies=[Depends(require_auth)])
async def set_device_mode(body: dict) -> dict:
    """切换 device_mode（AUTO/MANUAL/PAUSED）。"""
    from app.automation.device_mode import DeviceMode, device_mode_manager

    new_mode_str = str(body.get("mode", "")).upper()
    try:
        new_mode = DeviceMode(new_mode_str)
    except ValueError:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid mode '{new_mode_str}'. Must be AUTO, MANUAL, or PAUSED.",
        )
    reason = str(body.get("reason", ""))
    await device_mode_manager.set_mode(new_mode, reason=reason)
    return {"mode": device_mode_manager.mode.value}

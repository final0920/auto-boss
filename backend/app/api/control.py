"""control — 手动操控端点（仅 MANUAL 模式 + 鉴权，AC10/AC12）。

/control/tap    POST  {serial, x, y}
/control/swipe  POST  {serial, x1, y1, x2, y2, duration_ms?}
/control/touch  POST  {serial, events:[{x,y,action}]}  # motionevent 序列
/control/text   POST  {serial, text}
/control/key    POST  {serial, keycode}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.automation.device_mode import require_manual
from app.security.auth import require_auth

router = APIRouter(
    prefix="/control",
    tags=["control"],
    dependencies=[Depends(require_auth), Depends(require_manual)],
)


def _get_device(serial: str):
    """惰性获取 AdbDevice；无真机时抛 RuntimeError。"""
    from app.adb.device import AdbDevice  # 惰性导入

    return AdbDevice(serial)


@router.post("/tap")
async def tap(body: dict) -> dict:
    """点击指定坐标。"""
    import asyncio

    serial = str(body["serial"])
    x = int(body["x"])
    y = int(body["y"])
    device = _get_device(serial)
    await asyncio.to_thread(device.tap, x, y)
    return {"ok": True, "serial": serial, "x": x, "y": y}


@router.post("/swipe")
async def swipe(body: dict) -> dict:
    """滑动。"""
    import asyncio

    serial = str(body["serial"])
    x1, y1, x2, y2 = int(body["x1"]), int(body["y1"]), int(body["x2"]), int(body["y2"])
    duration_ms = int(body.get("duration_ms", 300))
    device = _get_device(serial)
    await asyncio.to_thread(device.swipe, x1, y1, x2, y2, duration_ms)
    return {"ok": True}


@router.post("/text")
async def send_text(body: dict) -> dict:
    """输入文本（ADBKeyboard）。"""
    import asyncio

    serial = str(body["serial"])
    text = str(body["text"])
    device = _get_device(serial)
    await asyncio.to_thread(device.send_text, text)
    return {"ok": True}


@router.post("/key")
async def send_key(body: dict) -> dict:
    """发送 keyevent。"""
    import asyncio

    serial = str(body["serial"])
    keycode = body["keycode"]
    device = _get_device(serial)
    await asyncio.to_thread(device.keyevent, keycode)
    return {"ok": True}


@router.post("/touch")
async def touch_sequence(body: dict) -> dict:
    """发送 motionevent 序列（canvas 手绘路径）。

    body.events: [{action: "DOWN"|"MOVE"|"UP", x: int, y: int}]
    """
    import asyncio

    from app.adb.device import AdbDevice

    serial = str(body["serial"])
    raw_events = list(body.get("events", []))
    device = AdbDevice(serial)

    async def _run() -> None:
        for ev in raw_events:
            action = str(ev.get("action", "")).upper()
            x, y = int(ev["x"]), int(ev["y"])
            if action == "DOWN":
                await asyncio.to_thread(device.motionevent_down, x, y)
            elif action == "MOVE":
                await asyncio.to_thread(device.motionevent_move, x, y)
            elif action == "UP":
                await asyncio.to_thread(device.motionevent_up, x, y)

    await _run()
    return {"ok": True, "count": len(raw_events)}

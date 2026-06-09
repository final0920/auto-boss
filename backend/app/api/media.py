"""media — 截图端点（鉴权 AC12）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.security.auth import require_auth

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/screenshot/{serial}", dependencies=[Depends(require_auth)])
async def screenshot(serial: str) -> Response:
    """返回 PNG 截图（adb exec-out screencap -p）。"""
    import asyncio

    from app.adb.screencap import screencap_png_bytes  # 惰性导入

    png = await asyncio.to_thread(screencap_png_bytes, serial)
    return Response(content=png, media_type="image/png")

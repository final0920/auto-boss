"""
FastAPI + python-socketio ASGI 组合入口（AC12/AC14）

lifespan:
  - 初始化 DB（建表）
  - 启动自检 scan_sending（AC8）
  - 启动 APScheduler（inbox_watcher / dispatcher 定时任务）
  - 注册 scrcpy Socket.IO 命名空间
  - shutdown：停止调度器 + 清理 terminal sessions

BIND_HOST 由 uvicorn 启动命令读取（见 __main__ 块）。
无真机也应能 import 启动（设备相关惰性导入）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Socket.IO server（默认命名空间鉴权；/scrcpy 命名空间在 lifespan 注册）
# ---------------------------------------------------------------------------

sio = socketio.AsyncServer(
    async_mode="asgi",
    # transport 层放行（含经 vite 代理的跨端口 Origin）；真正的 Origin/token 校验
    # 在 connect 事件的 sio_auth_ok 中完成。空列表会在握手层直接 403，sio_auth_ok
    # 根本跑不到。localhost-bind + sio_auth_ok(Origin+token) 已是纵深防御。
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> bool:
    """默认命名空间 connect：鉴权 (AC12)。"""
    from app.security.auth import sio_auth_ok

    if not sio_auth_ok(environ):
        logger.warning("Socket.IO 连接已拒绝 sid=%s", sid)
        return False
    logger.debug("Socket.IO 已连接 sid=%s", sid)
    return True


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("Socket.IO 已断开 sid=%s", sid)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1. 配置验证已在 pydantic model_validator 完成；再次触发以便日志明确
    logger.info("boss-autoapply 后端启动 bind_host=%s", settings.bind_host)

    # L2: 空 token 安全提示（AC12）
    if not settings.terminal_token:
        logger.warning(
            "TERMINAL_TOKEN 未设置：控制端点当前仅靠 localhost-bind + Origin 保护。"
            "建议设置高熵 TERMINAL_TOKEN 以启用 Bearer token 鉴权。"
        )

    # 2. 初始化 DB
    from app.db import init_db
    init_db()
    logger.info("数据库初始化完成")

    # 3. 启动自检：SENDING 记录推人工确认（AC8）
    try:
        from app.pipeline.dispatcher import scan_sending
        stuck = scan_sending()
        if stuck:
            logger.warning("scan_sending: 发现 %d 条 SENDING 记录需人工确认: %s", len(stuck), stuck)
    except Exception as exc:
        logger.warning("scan_sending 出错: %s", exc)

    # 4. APScheduler
    from app.scheduler import build_scheduler, register_jobs
    scheduler = build_scheduler()
    register_jobs(scheduler)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("APScheduler 已启动")

    # 5. 注册 scrcpy Socket.IO 命名空间
    try:
        from app.scrcpy.sio import register_scrcpy_namespace
        register_scrcpy_namespace(sio)
    except Exception as exc:
        logger.warning("scrcpy 命名空间注册失败（非致命）: %s", exc)

    yield

    # --- shutdown ---
    logger.info("boss-autoapply 后端正在关闭")

    # 停止调度器
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.debug("调度器关闭出错: %s", exc)

    # 清理所有 terminal sessions
    try:
        from app.api.terminal import get_terminal_service
        await get_terminal_service().close_all()
    except Exception as exc:
        logger.debug("terminal close_all 出错: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="boss-autoapply",
    description="真机端自动筛选 + 半自动投递 Boss 直聘",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: localhost origins only（主防线是 require_auth，CORS 仅辅助）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API 路由注册（全部带写/设备副作用端点均统一 require_auth，AC12）
# ---------------------------------------------------------------------------

from app.api import (  # noqa: E402
    applications,
    config_api,
    control,
    devices,
    jobs,
    logs,
    media,
    messages,
    scheduled,
)
from app.api import terminal  # noqa: E402

_API_PREFIX = "/api"

app.include_router(devices.router, prefix=_API_PREFIX)
app.include_router(control.router, prefix=_API_PREFIX)
app.include_router(media.router, prefix=_API_PREFIX)
app.include_router(jobs.router, prefix=_API_PREFIX)
app.include_router(applications.router, prefix=_API_PREFIX)
app.include_router(messages.router, prefix=_API_PREFIX)
app.include_router(config_api.router, prefix=_API_PREFIX)
app.include_router(scheduled.router, prefix=_API_PREFIX)
app.include_router(logs.router, prefix=_API_PREFIX)
app.include_router(terminal.router, prefix=_API_PREFIX)  # WS /api/terminal/ws


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """无鉴权健康检查 — 仅 localhost bind 访问。"""
    from app.automation.device_mode import device_mode_manager

    return {
        "status": "ok",
        "bind_host": settings.bind_host,
        "device_mode": device_mode_manager.mode.value,
    }


# ---------------------------------------------------------------------------
# ASGI 组合：Socket.IO 包裹 FastAPI
# ---------------------------------------------------------------------------

asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:asgi_app",
        host=settings.bind_host,
        port=8000,
        reload=False,
        log_level="info",
    )

"""
端点鉴权主防线（AC12 / P0-B）

主防线 = localhost-bind + Bearer token + Origin 校验，统一套到所有带写/设备副作用端点：
  /control/*  /terminal (WS)  /devices  /config
  scrcpy Socket.IO  SSE 事件流

用法（FastAPI 依赖注入）：
    from app.security.auth import require_auth
    @router.post("/control/tap")
    async def tap(req: Request, _: None = Depends(require_auth)):
        ...

Socket.IO / WebSocket 端点不走 Depends，需手动调用：
    await verify_ws_request(request, token=query_token)
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_localhost_origin(origin: str) -> bool:
    """Return True when origin host resolves to loopback."""
    after_scheme = origin.split("://", 1)[-1]
    # IPv6 literal: http://[::1]:8080 — extract bracketed address first
    if after_scheme.startswith("["):
        bracket_end = after_scheme.find("]")
        host = after_scheme[1:bracket_end] if bracket_end != -1 else after_scheme
    else:
        host = after_scheme.rsplit(":", 1)[0].strip("/")
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    except ValueError:
        host_only = after_scheme.split(":")[0].strip("/")
        return host_only in ("localhost",)


def _token_ok(provided: str) -> bool:
    """Constant-time comparison against configured token."""
    expected = settings.terminal_token
    if not expected:
        # No token configured — only safe when binding to localhost (validated at startup)
        return True
    return hmac.compare_digest(
        hashlib.sha256(provided.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def _check_origin(request: Request) -> None:
    """Reject cross-origin requests (AC12)."""
    origin = request.headers.get("origin", "")
    if not origin:
        # No Origin header — direct/same-origin call; allow.
        return
    if _is_localhost_origin(origin):
        return
    logger.warning(
        "Rejected cross-origin request origin=%s path=%s", origin, request.url.path
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cross-origin request rejected",
    )


def _check_peer_ip(request: Request) -> None:
    """L2: when TERMINAL_TOKEN is empty, verify TCP peer is loopback (AC12 depth).

    Adds a second guard in no-token mode: even if Origin spoofing somehow
    passed _check_origin, the TCP peer must be loopback.
    ASGI scope['client'] is (host, port); absent in some test/proxy stacks
    — skipped silently in that case to avoid breaking valid setups.
    """
    if settings.terminal_token:
        return  # token is the primary guard; peer check not needed
    try:
        client = request.scope.get("client")
        if client is None:
            return  # not available (e.g. TestClient) — skip
        peer_ip = client[0]
        addr = ipaddress.ip_address(peer_ip)
        if not addr.is_loopback:
            logger.warning(
                "Rejected non-loopback peer ip=%s path=%s (no token configured)",
                peer_ip, request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Remote access requires TERMINAL_TOKEN to be configured",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # unexpected — fail open rather than break valid requests


def _check_token(credentials: HTTPAuthorizationCredentials | None) -> None:
    """Reject requests with invalid/missing Bearer token when token is configured."""
    if not settings.terminal_token:
        return  # localhost-only mode, no token required
    if credentials is None or not _token_ok(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency — raises 401/403 on auth failure.

    Apply to every endpoint with write or device side-effects:
    /control/*, /devices, /config, SSE event stream.

    Check order: Origin → peer IP (no-token mode) → token.
    """
    _check_origin(request)
    _check_peer_ip(request)
    _check_token(credentials)


# ---------------------------------------------------------------------------
# Manual check for WebSocket / Socket.IO handshake
# ---------------------------------------------------------------------------


async def verify_ws_request(request: Request, token: str | None = None) -> None:
    """Call during WS/Socket.IO connection handshake.

    WS upgrade doesn't carry an HTTP Authorization header; token arrives
    via query param `?token=...`.
    """
    _check_origin(request)
    _check_peer_ip(request)
    if settings.terminal_token:
        if token is None or not _token_ok(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token for WebSocket connection",
            )


# ---------------------------------------------------------------------------
# Socket.IO connect-event auth helper (no exceptions — returns bool)
# ---------------------------------------------------------------------------


def sio_auth_ok(environ: dict) -> bool:
    """Check auth for a Socket.IO connect event.

    Called from the socketio server's connect handler.
    `environ` is the ASGI scope dict passed by python-socketio.
    """
    # Origin check
    origin = ""
    for k, v in environ.get("headers", []):
        key = k.decode() if isinstance(k, bytes) else k
        if key.lower() == "origin":
            origin = v.decode() if isinstance(v, bytes) else v
            break
    if origin and not _is_localhost_origin(origin):
        logger.warning("Socket.IO rejected cross-origin connect from %s", origin)
        return False

    # Token check
    if settings.terminal_token:
        query_string = environ.get("QUERY_STRING", "")
        if isinstance(query_string, bytes):
            query_string = query_string.decode()
        token = ""
        for part in query_string.split("&"):
            if part.startswith("token="):
                token = part[len("token="):]
                break
        if not _token_ok(token):
            logger.warning("Socket.IO rejected missing/invalid token")
            return False

    return True

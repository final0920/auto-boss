"""
test_auth — 端点鉴权主防线（AC12）。

覆盖：
  - 未鉴权请求被拒（401）
  - 跨 Origin 请求被拒（403）
  - localhost Origin 放行
  - token 正确放行 / token 错误拒绝
  - 无 Origin 头（直接调用）放行
  - WebSocket / Socket.IO 路径
  - sio_auth_ok 辅助函数

Patching strategy:
  auth.py binds `settings` at import time via `from app.config import settings`.
  test_rate_limiter.py replaces sys.modules["app.config"] entirely, so
  `import app.config as cfg` in later tests returns a different object than
  what auth.py holds. All overrides here patch `app.security.auth.settings`
  directly — the name actually used inside auth.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.security.auth import (
    require_auth,
    verify_ws_request,
    sio_auth_ok,
    _is_localhost_origin,
    _token_ok,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(origin: str = "") -> MagicMock:
    req = MagicMock()
    req.headers = {"origin": origin} if origin else {}
    req.url.path = "/control/tap"
    return req


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _settings(terminal_token: str = "") -> MagicMock:
    s = MagicMock()
    s.terminal_token = terminal_token
    return s


# ---------------------------------------------------------------------------
# _is_localhost_origin
# ---------------------------------------------------------------------------

class TestIsLocalhostOrigin:
    def test_localhost_string(self):
        assert _is_localhost_origin("http://localhost:3000") is True

    def test_127_0_0_1(self):
        assert _is_localhost_origin("http://127.0.0.1:8000") is True

    def test_ipv6_loopback(self):
        assert _is_localhost_origin("http://[::1]:8080") is True

    def test_external_ip(self):
        assert _is_localhost_origin("http://192.168.1.5:3000") is False

    def test_external_domain(self):
        assert _is_localhost_origin("https://evil.example.com") is False


# ---------------------------------------------------------------------------
# _token_ok
# ---------------------------------------------------------------------------

class TestTokenOk:
    def test_no_token_configured_always_ok(self):
        with patch("app.security.auth.settings", _settings("")):
            assert _token_ok("anything") is True
            assert _token_ok("") is True

    def test_correct_token_ok(self):
        with patch("app.security.auth.settings", _settings("secret-token-123")):
            assert _token_ok("secret-token-123") is True

    def test_wrong_token_rejected(self):
        with patch("app.security.auth.settings", _settings("secret-token-123")):
            assert _token_ok("wrong-token") is False
            assert _token_ok("") is False


# ---------------------------------------------------------------------------
# require_auth — FastAPI dependency
# ---------------------------------------------------------------------------

class TestRequireAuth:
    @pytest.mark.anyio
    async def test_no_origin_no_token_required_passes(self):
        with patch("app.security.auth.settings", _settings("")):
            await require_auth(_make_request(), credentials=None)

    @pytest.mark.anyio
    async def test_localhost_origin_passes(self):
        with patch("app.security.auth.settings", _settings("")):
            await require_auth(_make_request("http://localhost:5173"), credentials=None)

    @pytest.mark.anyio
    async def test_cross_origin_rejected_403(self):
        with patch("app.security.auth.settings", _settings("")):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(_make_request("https://evil.example.com"), credentials=None)
        assert exc_info.value.status_code == 403

    @pytest.mark.anyio
    async def test_missing_token_rejected_401(self):
        with patch("app.security.auth.settings", _settings("required-token")):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(_make_request(), credentials=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_wrong_token_rejected_401(self):
        with patch("app.security.auth.settings", _settings("required-token")):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(_make_request(), credentials=_bearer("wrong"))
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_correct_token_passes(self):
        with patch("app.security.auth.settings", _settings("required-token")):
            await require_auth(_make_request(), credentials=_bearer("required-token"))

    @pytest.mark.anyio
    async def test_cross_origin_rejected_even_with_correct_token(self):
        """Origin check fires before token check."""
        with patch("app.security.auth.settings", _settings("tok")):
            with pytest.raises(HTTPException) as exc_info:
                await require_auth(
                    _make_request("https://attacker.example.com"),
                    credentials=_bearer("tok"),
                )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# verify_ws_request — WebSocket handshake
# ---------------------------------------------------------------------------

class TestVerifyWsRequest:
    @pytest.mark.anyio
    async def test_no_token_configured_passes(self):
        with patch("app.security.auth.settings", _settings("")):
            await verify_ws_request(_make_request(), token=None)

    @pytest.mark.anyio
    async def test_cross_origin_ws_rejected(self):
        with patch("app.security.auth.settings", _settings("")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_ws_request(_make_request("http://remote.host:3000"), token=None)
        assert exc_info.value.status_code == 403

    @pytest.mark.anyio
    async def test_missing_ws_token_rejected(self):
        with patch("app.security.auth.settings", _settings("ws-token")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_ws_request(_make_request(), token=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_correct_ws_token_passes(self):
        with patch("app.security.auth.settings", _settings("ws-token")):
            await verify_ws_request(_make_request(), token="ws-token")

    @pytest.mark.anyio
    async def test_wrong_ws_token_rejected(self):
        with patch("app.security.auth.settings", _settings("ws-token")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_ws_request(_make_request(), token="bad")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# sio_auth_ok — Socket.IO connect event
# ---------------------------------------------------------------------------

class TestSioAuthOk:
    def _environ(self, origin: str = "", token: str = "") -> dict:
        headers = []
        if origin:
            headers.append((b"origin", origin.encode()))
        qs = f"token={token}" if token else ""
        return {"headers": headers, "QUERY_STRING": qs}

    def test_no_token_configured_localhost_origin_ok(self):
        with patch("app.security.auth.settings", _settings("")):
            assert sio_auth_ok(self._environ(origin="http://localhost:5173")) is True

    def test_no_token_no_origin_ok(self):
        with patch("app.security.auth.settings", _settings("")):
            assert sio_auth_ok({}) is True

    def test_cross_origin_rejected(self):
        with patch("app.security.auth.settings", _settings("")):
            assert sio_auth_ok(self._environ(origin="http://evil.example.com")) is False

    def test_missing_token_rejected(self):
        with patch("app.security.auth.settings", _settings("sio-tok")):
            assert sio_auth_ok(self._environ(origin="http://localhost:5173", token="")) is False

    def test_correct_token_ok(self):
        with patch("app.security.auth.settings", _settings("sio-tok")):
            assert sio_auth_ok(self._environ(origin="http://localhost:5173", token="sio-tok")) is True

    def test_wrong_token_rejected(self):
        with patch("app.security.auth.settings", _settings("sio-tok")):
            assert sio_auth_ok(self._environ(origin="http://localhost:5173", token="wrong")) is False

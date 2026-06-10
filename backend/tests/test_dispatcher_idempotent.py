"""test_dispatcher_idempotent.py — 幂等投递：崩溃恢复不二次发送、只取 CLAIMED。"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 最小 stub 层（避免触发 pydantic-settings / SQLite）
# ---------------------------------------------------------------------------

def _install_stubs():
    # config
    if "app.config" not in sys.modules:
        stub = types.ModuleType("app.config")
        s = MagicMock()
        s.daily_apply_limit = 150
        s.apply_interval_min = 0
        s.apply_interval_max = 0
        stub.settings = s
        sys.modules["app.config"] = stub

    # db
    if "app.db" not in sys.modules:
        stub = types.ModuleType("app.db")
        stub.engine = MagicMock()
        sys.modules["app.db"] = stub


_install_stubs()


# ---------------------------------------------------------------------------
# In-memory Application store
# ---------------------------------------------------------------------------

from app.models import ApplicationStatus


class _App:
    _next_id = 1

    def __init__(self, status: ApplicationStatus, **kw):
        self.id = _App._next_id
        _App._next_id += 1
        self.status = status
        self.greeting = kw.get("greeting", "")
        self.fail_reason = ""
        self.sent_at = None
        self.updated_at = None
        self.account_id = kw.get("account_id", "default")
        self.device_id = kw.get("device_id", "default")


class _InMemoryStore:
    def __init__(self):
        self._apps: dict[int, _App] = {}

    def add(self, app: _App) -> _App:
        self._apps[app.id] = app
        return app

    def get(self, app_id: int) -> _App | None:
        return self._apps.get(app_id)

    def list_by_status(self, status: ApplicationStatus) -> list[_App]:
        return [a for a in self._apps.values() if a.status == status]

    def reset(self):
        self._apps.clear()
        _App._next_id = 1


_store = _InMemoryStore()


# ---------------------------------------------------------------------------
# Session context-manager stub
# ---------------------------------------------------------------------------

class _FakeSession:
    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get(self, model, pk):
        return _store.get(pk)

    def exec(self, stmt):
        # 返回 CLAIMED 列表
        result = MagicMock()
        result.all.return_value = _store.list_by_status(ApplicationStatus.CLAIMED)
        result.first.return_value = None
        return result

    def add(self, obj):
        if isinstance(obj, _App):
            _store._apps[obj.id] = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset():
    _store.reset()
    yield
    _store.reset()


def _patch_dispatcher(monkeypatch):
    import app.pipeline.dispatcher as disp

    # Patch Session
    monkeypatch.setattr(disp, "Session", lambda engine: _FakeSession())

    # Patch rate_limiter — 默认允许
    mock_rl = MagicMock()
    mock_rl.check_and_consume_apply = AsyncMock(return_value=True)
    monkeypatch.setattr(disp, "rate_limiter", mock_rl)

    # Patch _is_night_stop
    monkeypatch.setattr(disp, "_is_night_stop", lambda: False)

    # Patch _execute_apply — 默认成功
    monkeypatch.setattr(disp, "_execute_apply", AsyncMock(return_value=(True, "", False)))

    return disp


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestDispatcherIdempotent:
    @pytest.mark.anyio
    async def test_only_takes_claimed(self, monkeypatch):
        """dispatcher 只处理 CLAIMED，其他状态跳过。"""
        disp = _patch_dispatcher(monkeypatch)

        # 各状态各一条
        pending = _store.add(_App(ApplicationStatus.PENDING))
        sending = _store.add(_App(ApplicationStatus.SENDING))
        sent = _store.add(_App(ApplicationStatus.SENT))
        failed = _store.add(_App(ApplicationStatus.FAILED))
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))

        result = await disp.dispatch_one(pending.id)
        assert result == "SKIP"

        result = await disp.dispatch_one(sending.id)
        assert result == "SKIP"

        result = await disp.dispatch_one(sent.id)
        assert result == "SKIP"

        result = await disp.dispatch_one(failed.id)
        assert result == "SKIP"

        result = await disp.dispatch_one(claimed.id)
        assert result == "SENT"

    @pytest.mark.anyio
    async def test_crash_recovery_sending_not_retaken(self, monkeypatch):
        """崩溃后遗留 SENDING 记录不应被 dispatch_one 自动重拾。"""
        disp = _patch_dispatcher(monkeypatch)
        # 模拟崩溃残留
        stuck = _store.add(_App(ApplicationStatus.SENDING))

        result = await disp.dispatch_one(stuck.id)
        assert result == "SKIP", "SENDING 状态不应被 dispatch_one 重拾"

    @pytest.mark.anyio
    async def test_scan_sending_returns_stuck_ids(self, monkeypatch):
        """scan_sending 应返回 SENDING 状态记录的 id 列表。"""
        disp = _patch_dispatcher(monkeypatch)
        a1 = _store.add(_App(ApplicationStatus.SENDING))
        a2 = _store.add(_App(ApplicationStatus.SENDING))
        _store.add(_App(ApplicationStatus.CLAIMED))

        # patch Session.exec to return SENDING list for scan_sending
        class _ScanSession(_FakeSession):
            def exec(self, stmt):
                r = MagicMock()
                r.all.return_value = _store.list_by_status(ApplicationStatus.SENDING)
                return r

        monkeypatch.setattr(disp, "Session", lambda engine: _ScanSession())
        stuck_ids = disp.scan_sending()
        assert set(stuck_ids) == {a1.id, a2.id}

    @pytest.mark.anyio
    async def test_rate_limit_blocks_apply(self, monkeypatch):
        """配额耗尽时 dispatch_one 返回 SKIP。"""
        disp = _patch_dispatcher(monkeypatch)
        disp.rate_limiter.check_and_consume_apply = AsyncMock(return_value=False)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(claimed.id)
        assert result == "SKIP"

    @pytest.mark.anyio
    async def test_execute_failure_marks_failed(self, monkeypatch):
        """执行失败时 Application 转为 FAILED。"""
        disp = _patch_dispatcher(monkeypatch)
        monkeypatch.setattr(disp, "_execute_apply", AsyncMock(return_value=(False, "network error", False)))
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(claimed.id)
        assert result == "FAILED"
        app = _store.get(claimed.id)
        assert app.status == ApplicationStatus.FAILED
        assert "network error" in app.fail_reason

    @pytest.mark.anyio
    async def test_geetest_marks_failed(self, monkeypatch):
        """检测到 geetest 时标记 FAILED 并记录原因。"""
        disp = _patch_dispatcher(monkeypatch)
        monkeypatch.setattr(disp, "_execute_apply", AsyncMock(return_value=(False, "", True)))
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(claimed.id)
        assert result == "FAILED"
        app = _store.get(claimed.id)
        assert "geetest" in app.fail_reason

    @pytest.mark.anyio
    async def test_night_stop_skips(self, monkeypatch):
        """夜停时段 dispatch_one 返回 SKIP。"""
        disp = _patch_dispatcher(monkeypatch)
        monkeypatch.setattr(disp, "_is_night_stop", lambda: True)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(claimed.id)
        assert result == "SKIP"

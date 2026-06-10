"""test_dispatcher_idempotent.py — 幂等投递：只取 CLAIMED、崩溃不二次发送、DUP 不计配额。

适配 slim-v3 M3 契约：
  dispatch_one(application_id, driver, rules) — driver.tap_chat_and_capture 为设备动作；
  夜停 is_night_stop(rules)；geetest 检测在 runner 层（不在本模块）；
  mark_dup 由 PENDING 直接置 DUP，不扣配额、不写 SENDING（A5）。
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

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

from app.models import ApplicationStatus  # noqa: E402
from app.rules import RulesConfig  # noqa: E402


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


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get(self, model, pk):
        return _store.get(pk)

    def exec(self, stmt):
        result = MagicMock()
        result.all.return_value = _store.list_by_status(ApplicationStatus.SENDING)
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


def _mk_driver(ok: bool = True, greeting: str = "您好！6年开发经验…", reason: str = ""):
    """MagicMock BossDriver：tap_chat_and_capture 同步返回三元组（经 to_thread 调用）。"""
    driver = MagicMock()
    driver.tap_chat_and_capture = MagicMock(
        return_value=(ok, greeting if ok else "", reason if not ok else "")
    )
    return driver


def _patch_dispatcher(monkeypatch):
    import app.pipeline.dispatcher as disp

    monkeypatch.setattr(disp, "Session", lambda engine: _FakeSession())

    mock_rl = MagicMock()
    mock_rl.check_and_consume_apply = AsyncMock(return_value=True)
    monkeypatch.setattr(disp, "rate_limiter", mock_rl)

    # 夜停默认关（具体用例自行覆盖）
    monkeypatch.setattr(disp, "is_night_stop", lambda rules: False)

    return disp


RULES = RulesConfig()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

class TestDispatcherIdempotent:
    @pytest.mark.anyio
    async def test_only_takes_claimed(self, monkeypatch):
        """dispatch_one 只处理 CLAIMED，其他状态（含 DUP）一律 SKIP。"""
        disp = _patch_dispatcher(monkeypatch)
        driver = _mk_driver(ok=True)

        for st in (ApplicationStatus.PENDING, ApplicationStatus.SENDING,
                   ApplicationStatus.SENT, ApplicationStatus.FAILED,
                   ApplicationStatus.DUP):
            app = _store.add(_App(st))
            assert await disp.dispatch_one(app.id, driver, RULES) == "SKIP"

        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        assert await disp.dispatch_one(claimed.id, driver, RULES) == "SENT"

    @pytest.mark.anyio
    async def test_crash_recovery_sending_not_retaken(self, monkeypatch):
        """崩溃后遗留 SENDING 记录不应被 dispatch_one 自动重拾（A10）。"""
        disp = _patch_dispatcher(monkeypatch)
        stuck = _store.add(_App(ApplicationStatus.SENDING))
        result = await disp.dispatch_one(stuck.id, _mk_driver(), RULES)
        assert result == "SKIP", "SENDING 状态不应被 dispatch_one 重拾"

    @pytest.mark.anyio
    async def test_scan_sending_returns_stuck_ids(self, monkeypatch):
        """scan_sending 返回 SENDING 残留 id 列表。"""
        disp = _patch_dispatcher(monkeypatch)
        a1 = _store.add(_App(ApplicationStatus.SENDING))
        a2 = _store.add(_App(ApplicationStatus.SENDING))
        _store.add(_App(ApplicationStatus.CLAIMED))
        stuck_ids = disp.scan_sending()
        assert set(stuck_ids) == {a1.id, a2.id}

    @pytest.mark.anyio
    async def test_rate_limit_blocks_apply(self, monkeypatch):
        """配额耗尽时 dispatch_one 返回 SKIP，且不发生设备动作。"""
        disp = _patch_dispatcher(monkeypatch)
        disp.rate_limiter.check_and_consume_apply = AsyncMock(return_value=False)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        driver = _mk_driver()
        result = await disp.dispatch_one(claimed.id, driver, RULES)
        assert result == "SKIP"
        driver.tap_chat_and_capture.assert_not_called()

    @pytest.mark.anyio
    async def test_execute_failure_marks_failed(self, monkeypatch):
        """设备动作失败 → FAILED + 原因落库。"""
        disp = _patch_dispatcher(monkeypatch)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(
            claimed.id, _mk_driver(ok=False, reason="未跳转聊天页"), RULES)
        assert result == "FAILED"
        app = _store.get(claimed.id)
        assert app.status == ApplicationStatus.FAILED
        assert "未跳转聊天页" in app.fail_reason

    @pytest.mark.anyio
    async def test_success_persists_greeting(self, monkeypatch):
        """投递成功 → SENT + 实发招呼语存证（A6）。"""
        disp = _patch_dispatcher(monkeypatch)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        result = await disp.dispatch_one(
            claimed.id, _mk_driver(ok=True, greeting="您好！我拥有6年经验"), RULES)
        assert result == "SENT"
        app = _store.get(claimed.id)
        assert app.status == ApplicationStatus.SENT
        assert app.greeting == "您好！我拥有6年经验"
        assert app.sent_at is not None

    @pytest.mark.anyio
    async def test_night_stop_skips(self, monkeypatch):
        """夜停时段 dispatch_one 返回 SKIP（夜停读 rules，单一真值源）。"""
        disp = _patch_dispatcher(monkeypatch)
        monkeypatch.setattr(disp, "is_night_stop", lambda rules: True)
        claimed = _store.add(_App(ApplicationStatus.CLAIMED))
        driver = _mk_driver()
        result = await disp.dispatch_one(claimed.id, driver, RULES)
        assert result == "SKIP"
        driver.tap_chat_and_capture.assert_not_called()

    @pytest.mark.anyio
    async def test_mark_dup_no_quota_no_sending(self, monkeypatch):
        """DUP：PENDING 直接置 DUP，不扣配额、不写 SENDING（A5）。"""
        disp = _patch_dispatcher(monkeypatch)
        pending = _store.add(_App(ApplicationStatus.PENDING))
        disp.mark_dup(pending.id)
        app = _store.get(pending.id)
        assert app.status == ApplicationStatus.DUP
        # A5 判据：配额入口从未被调用
        disp.rate_limiter.check_and_consume_apply.assert_not_called()


class TestNightStopParse:
    def test_cross_midnight_window(self):
        """跨午夜窗口解析（23:00-07:00）。"""
        from datetime import time as dtime

        from app.pipeline.dispatcher import _parse_hhmm
        assert _parse_hhmm("23:00", dtime(0, 0)) == dtime(23, 0)
        assert _parse_hhmm("07:30", dtime(0, 0)) == dtime(7, 30)
        # 损坏输入回退默认
        assert _parse_hhmm("bad", dtime(6, 0)) == dtime(6, 0)
        assert _parse_hhmm("", dtime(6, 0)) == dtime(6, 0)

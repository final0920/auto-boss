"""test_rate_limiter.py — 三路 VLM 共享预算 + 投递优先并发测试。"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# DB/config stub — 必须在 rate_limiter 导入前注入
# ---------------------------------------------------------------------------

def _make_settings():
    s = MagicMock()
    s.daily_apply_limit = 5
    s.vlm_daily_limit = 3
    return s


def _install_stubs():
    # config stub
    if "app.config" not in sys.modules:
        stub = types.ModuleType("app.config")
        stub.settings = _make_settings()
        sys.modules["app.config"] = stub
    else:
        import app.config as cfg
        cfg.settings = _make_settings()

    # db stub — engine mock
    if "app.db" not in sys.modules:
        stub = types.ModuleType("app.db")
        stub.engine = MagicMock()
        sys.modules["app.db"] = stub

    # models stub
    if "app.models" not in sys.modules:
        stub = types.ModuleType("app.models")

        class _Quota:
            def __init__(self, **kw):
                self.date = kw.get("date", "")
                self.apply_count = kw.get("apply_count", 0)
                self.vlm_count = kw.get("vlm_count", 0)

        stub.Quota = _Quota
        sys.modules["app.models"] = stub


_install_stubs()


# ---------------------------------------------------------------------------
# In-memory Quota store — replace SQLModel Session
# ---------------------------------------------------------------------------

class _InMemoryQuotaStore:
    """替换 SQLModel Session，使用内存字典存储 Quota。"""

    def __init__(self):
        self._store: dict[str, object] = {}

    def get_or_create(self, day: str):
        if day not in self._store:
            from app.models import Quota
            self._store[day] = Quota(date=day)
        return self._store[day]

    def reset(self):
        self._store.clear()


_store = _InMemoryQuotaStore()


def _patch_session(monkeypatch):
    """Patch sqlmodel.Session to use in-memory store."""
    import app.pipeline.rate_limiter as rl_mod

    def _sync_check_apply(daily_limit: int) -> bool:
        from datetime import date
        day = date.today().isoformat()
        q = _store.get_or_create(day)
        if q.apply_count >= daily_limit:
            return False
        q.apply_count += 1
        return True

    def _sync_check_vlm(consumer, vlm_limit: int) -> bool:
        from datetime import date
        day = date.today().isoformat()
        q = _store.get_or_create(day)
        if q.vlm_count >= vlm_limit:
            return False
        q.vlm_count += 1
        return True

    def _sync_get_quota() -> dict:
        from datetime import date
        day = date.today().isoformat()
        q = _store.get_or_create(day)
        import app.config as cfg
        return {
            "date": day,
            "apply_count": q.apply_count,
            "vlm_count": q.vlm_count,
            "daily_apply_limit": cfg.settings.daily_apply_limit,
            "vlm_daily_limit": cfg.settings.vlm_daily_limit,
        }

    monkeypatch.setattr(rl_mod, "_sync_check_apply", _sync_check_apply)
    monkeypatch.setattr(rl_mod, "_sync_check_vlm", _sync_check_vlm)
    monkeypatch.setattr(rl_mod, "_sync_get_quota", _sync_get_quota)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_store():
    _store.reset()
    yield
    _store.reset()


@pytest.fixture()
def rl(monkeypatch):
    _patch_session(monkeypatch)
    from app.pipeline.rate_limiter import RateLimiter
    return RateLimiter()


# ---------------------------------------------------------------------------
# 投递配额
# ---------------------------------------------------------------------------

class TestApplyQuota:
    @pytest.mark.anyio
    async def test_allows_up_to_limit(self, rl):
        import app.config as cfg
        cfg.settings.daily_apply_limit = 3
        results = [await rl.check_and_consume_apply() for _ in range(4)]
        assert results == [True, True, True, False]

    @pytest.mark.anyio
    async def test_returns_false_when_exhausted(self, rl):
        import app.config as cfg
        cfg.settings.daily_apply_limit = 1
        assert await rl.check_and_consume_apply() is True
        assert await rl.check_and_consume_apply() is False


# ---------------------------------------------------------------------------
# VLM 三路共享预算
# ---------------------------------------------------------------------------

class TestVlmQuota:
    @pytest.mark.anyio
    async def test_three_consumers_share_budget(self, rl):
        import app.config as cfg
        cfg.settings.vlm_daily_limit = 3
        # vision_backend 消耗 1
        assert await rl.check_and_consume_vlm("vision_backend") is True
        # planner 消耗 1
        assert await rl.check_and_consume_vlm("planner") is True
        # inbox_watcher 消耗 1
        assert await rl.check_and_consume_vlm("inbox_watcher") is True
        # 第4次：全部消费者均应返回 False
        assert await rl.check_and_consume_vlm("vision_backend") is False
        assert await rl.check_and_consume_vlm("planner") is False
        assert await rl.check_and_consume_vlm("inbox_watcher") is False

    @pytest.mark.anyio
    async def test_inbox_watcher_returns_false_not_raises(self, rl):
        import app.config as cfg
        cfg.settings.vlm_daily_limit = 0
        # inbox_watcher 超额时返回 False，不抛异常
        result = await rl.check_and_consume_vlm("inbox_watcher")
        assert result is False

    @pytest.mark.anyio
    async def test_high_priority_consumers_also_return_false_on_exhaustion(self, rl):
        import app.config as cfg
        cfg.settings.vlm_daily_limit = 0
        assert await rl.check_and_consume_vlm("vision_backend") is False
        assert await rl.check_and_consume_vlm("planner") is False

    @pytest.mark.anyio
    async def test_concurrent_vlm_no_overcount(self, rl):
        """并发消耗不应超过 vlm_daily_limit。"""
        import app.config as cfg
        cfg.settings.vlm_daily_limit = 5
        results = await asyncio.gather(*[
            rl.check_and_consume_vlm("vision_backend") for _ in range(10)
        ])
        assert results.count(True) == 5
        assert results.count(False) == 5

    @pytest.mark.anyio
    async def test_get_quota_reflects_consumption(self, rl):
        import app.config as cfg
        cfg.settings.vlm_daily_limit = 10
        await rl.check_and_consume_vlm("vision_backend")
        await rl.check_and_consume_vlm("planner")
        quota = await rl.get_quota()
        assert quota["vlm_count"] == 2

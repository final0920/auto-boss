"""test_rate_limiter.py — 投递配额测试（VLM 路已随精简重构删除）。"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# DB/config stub — 必须在 rate_limiter 导入前注入
# ---------------------------------------------------------------------------

def _make_settings():
    s = MagicMock()
    s.daily_apply_limit = 5
    return s


def _install_stubs():
    # config stub
    if "app.config" not in sys.modules:
        stub = types.ModuleType("app.config")
        stub.settings = _make_settings()
        sys.modules["app.config"] = stub

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
    """Patch rate_limiter 的同步核心为内存实现。"""
    import app.pipeline.rate_limiter as rl_mod

    def _sync_check_apply(daily_limit: int) -> bool:
        from datetime import date
        day = date.today().isoformat()
        q = _store.get_or_create(day)
        if q.apply_count >= daily_limit:
            return False
        q.apply_count += 1
        return True

    def _sync_get_quota(daily_limit: int) -> dict:
        from datetime import date
        day = date.today().isoformat()
        q = _store.get_or_create(day)
        return {
            "date": day,
            "apply_count": q.apply_count,
            "daily_apply_limit": daily_limit,
        }

    monkeypatch.setattr(rl_mod, "_sync_check_apply", _sync_check_apply)
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
# 投递配额（daily_limit 显式传参 — 调用方传 rules.daily_limit）
# ---------------------------------------------------------------------------

class TestApplyQuota:
    @pytest.mark.anyio
    async def test_allows_up_to_limit(self, rl):
        results = [await rl.check_and_consume_apply(daily_limit=3) for _ in range(4)]
        assert results == [True, True, True, False]

    @pytest.mark.anyio
    async def test_returns_false_when_exhausted(self, rl):
        assert await rl.check_and_consume_apply(daily_limit=1) is True
        assert await rl.check_and_consume_apply(daily_limit=1) is False

    @pytest.mark.anyio
    async def test_zero_limit_rejects_immediately(self, rl):
        assert await rl.check_and_consume_apply(daily_limit=0) is False

    @pytest.mark.anyio
    async def test_concurrent_no_overcount(self, rl):
        """并发消耗不应超过 daily_limit。"""
        results = await asyncio.gather(*[
            rl.check_and_consume_apply(daily_limit=5) for _ in range(10)
        ])
        assert results.count(True) == 5
        assert results.count(False) == 5

    @pytest.mark.anyio
    async def test_get_quota_reflects_consumption(self, rl):
        await rl.check_and_consume_apply(daily_limit=10)
        await rl.check_and_consume_apply(daily_limit=10)
        quota = await rl.get_quota(daily_limit=10)
        assert quota["apply_count"] == 2
        assert quota["daily_apply_limit"] == 10

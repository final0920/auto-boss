"""
Shared test fixtures.

The most important job here is stubbing app.config.settings before any
app.* module is imported, so validators that check GPT_API_KEY never run
during the test suite.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


def _make_fake_settings() -> MagicMock:
    s = MagicMock()
    s.gpt_api_key = "test-key"
    s.gpt_base_url = "https://gpt.pkpp.cn/v1"
    s.gpt_model = "gpt-5.5"
    s.gpt_reasoning = "high"
    s.bind_host = "127.0.0.1"
    s.terminal_token = ""
    s.daily_apply_limit = 150
    s.score_threshold = 80
    s.apply_interval_min = 0
    s.apply_interval_max = 0
    s.database_url = "sqlite://"   # in-memory SQLite for tests
    s.inbox_poll_min_sec = 120
    s.inbox_poll_max_sec = 300
    return s


def _install_config_stub() -> None:
    """
    If app.config has not been imported yet, inject a stub module so that
    `from app.config import settings` in app.llm.client (and others) gets
    the fake object instead of triggering pydantic-settings validation.
    """
    if "app.config" not in sys.modules:
        stub = types.ModuleType("app.config")
        stub.settings = _make_fake_settings()  # type: ignore[attr-defined]
        sys.modules["app.config"] = stub
    else:
        # Already imported — patch the attribute in place
        import app.config as cfg
        cfg.settings = _make_fake_settings()  # type: ignore[attr-defined]


# Run once before any collection/import of app.* modules
_install_config_stub()


@pytest.fixture(autouse=True)
def reset_test_state():
    """Reset shared mutable state between tests.

    1. Restore settings to known-good values so token/config mutations in one
       test don't bleed into the next.
    2. Reset the LLM client singleton so each test gets a fresh OpenAI instance
       constructed with the clean settings.
    """
    yield
    # Restore settings to the clean stub values
    import app.config as cfg
    cfg.settings.terminal_token = ""
    cfg.settings.gpt_api_key = "test-key"
    cfg.settings.gpt_base_url = "https://gpt.pkpp.cn/v1"
    cfg.settings.gpt_model = "gpt-5.5"
    cfg.settings.gpt_reasoning = "high"
    cfg.settings.daily_apply_limit = 150
    # Reset LLM singleton
    try:
        import app.llm.client as mod
        mod._client_instance = None
    except ImportError:
        pass


# anyio: pin to asyncio only — trio is not installed in this environment
@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param

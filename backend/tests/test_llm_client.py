"""
Unit tests for app.llm.client.
All openai calls are mocked — no real API is invoked.
conftest.py stubs app.config.settings before any import.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# LLMClient.chat — happy path
# ---------------------------------------------------------------------------

class TestLLMClientChat:
    def test_chat_returns_content(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion("hello")
        )
        assert client.chat([{"role": "user", "content": "hi"}]) == "hello"

    def test_chat_passes_json_mode(self):
        from app.llm.client import LLMClient
        payload = json.dumps({"score": 85, "reasons": ["good fit"]})
        mock_create = MagicMock(return_value=_make_completion(payload))
        client = LLMClient()
        client._client.chat.completions.create = mock_create
        result = client.chat([{"role": "user", "content": "score me"}], json_mode=True)
        assert result == payload
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_chat_passes_reasoning_effort(self):
        from app.llm.client import LLMClient
        mock_create = MagicMock(return_value=_make_completion("ok"))
        client = LLMClient()
        client._client.chat.completions.create = mock_create
        client.chat([{"role": "user", "content": "x"}])
        assert mock_create.call_args.kwargs["reasoning_effort"] == "high"

    def test_chat_strips_whitespace(self):
        from app.llm.client import LLMClient
        client = LLMClient()
        client._client.chat.completions.create = MagicMock(
            return_value=_make_completion("  trimmed  ")
        )
        assert client.chat([]) == "trimmed"


# ---------------------------------------------------------------------------
# LLMClient.chat — retry logic
# ---------------------------------------------------------------------------

class TestLLMClientRetry:
    def test_retries_on_rate_limit_then_succeeds(self):
        import openai as oai
        from app.llm.client import LLMClient

        calls = {"n": 0}

        def side_effect(**_kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise oai.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                )
            return _make_completion("ok")

        client = LLMClient()
        with patch.object(client._client.chat.completions, "create", side_effect=side_effect):
            with patch("app.llm.client.time.sleep"):
                result = client.chat([])
        assert result == "ok"
        assert calls["n"] == 3

    def test_no_retry_on_auth_error(self):
        import openai as oai
        from app.llm.client import LLMClient

        client = LLMClient()
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=oai.AuthenticationError(
                "bad key", response=MagicMock(status_code=401), body={}
            ),
        ):
            with pytest.raises(oai.AuthenticationError):
                client.chat([])

    def test_exhausts_retries_and_raises(self):
        import openai as oai
        from app.llm.client import LLMClient

        client = LLMClient()
        with patch.object(
            client._client.chat.completions,
            "create",
            side_effect=oai.RateLimitError(
                "rate limited", response=MagicMock(status_code=429), body={}
            ),
        ):
            with patch("app.llm.client.time.sleep"):
                with pytest.raises(oai.RateLimitError):
                    client.chat([])


# ---------------------------------------------------------------------------
# get_client singleton
# ---------------------------------------------------------------------------

def test_get_client_returns_singleton():
    from app.llm.client import get_client
    c1 = get_client()
    c2 = get_client()
    assert c1 is c2
